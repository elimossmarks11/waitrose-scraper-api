import sqlite3

import requests
import json
import sys
import time
import click

import pandas as pd

from pathlib import Path

import re

#############
# CONSTANTS #
#############

DATA_DIR = Path('data')
SCRAPED_DIR = DATA_DIR / 'scraped'
ENRICHED_DIR = DATA_DIR / 'enriched'

################
# CLI COMMANDS #
################

@click.group()
def cli():
    """Pipeline for enriching and serving Waitrose product data."""
    pass

@cli.command()
@click.option("--only-new/--all", default=True, help='Skip already-enriched products')
def enrich_open_food_facts(only_new: bool):
    """Match scraped products to a NOVA classification either using OpenFoodFacts or MUP.xlsx and save to data/enriched/."""

    ENRICHED_DIR.mkdir(parents=True, exist_ok=True)

    scraped_file = SCRAPED_DIR / 'products.jsonl'
    enriched_file = ENRICHED_DIR / 'products.jsonl'

    scraped = pd.read_json(scraped_file, lines=True).to_dict(orient='records')
    click.echo(f'Loaded {len(scraped)} scraped products')

    # Load already-enriched products, skip if present

    already_done: set[str] = set()
    if only_new and enriched_file.exists():
        enriched_df = pd.read_json(enriched_file, lines=True)
        for barcodes in enriched_df['barcode']:
            for bc in barcodes:
                already_done.add(bc)
        click.echo(f'Skipping {len(already_done)} already-enriched barcodes')

    # Refine scraped products to only include food products

    from excluded_categories import EXCLUDED_CATEGORY_IDS

    excluded = set(EXCLUDED_CATEGORY_IDS)

    def is_excluded(product):
        product_categories = (product.get("food_type") or [])[:3]
        return any(cat['id'] in excluded for cat in product_categories)

    pre_filter = len(scraped)
    scraped = [product for product in scraped if not is_excluded(product)]
    dropped_products = pre_filter - len(scraped)
        
    click.echo(f'{dropped_products} non-food products dropped.')

    # Enrich food data with OpenFoodFacts API

    df_mup = pd.read_excel(ENRICHED_DIR / 'MUP.xlsx')

    def strip_asterisks(text):
        return text.replace('*', '')

    exact_terms = set(
        df_mup.loc[df_mup['match_type'] == 'exact', 'mup_name']
        .str.lower()
        .str.strip()
        .apply(strip_asterisks)
    )

    prefix_terms = tuple(
        df_mup.loc[df_mup['match_type'] == 'prefix', 'mup_name']
        .str.lower()
        .str.strip()
        .apply(strip_asterisks)
    )

    def normalize(text):
        return re.sub(r'[^a-zA-Z0-9\s]', '', text.lower())

    off_enriched_count = 0
    with open(enriched_file, 'a') as out:
        for product in scraped:
            barcodes = product.get('barcode', [])

            if only_new and any(bc in already_done for bc in barcodes):
                continue

            nova_group = None
            barcode_used = None
            for bc in barcodes:
                try:
                    resp = requests.get(
                    f'https://world.openfoodfacts.org/api/v2/product/{bc}',
                    params = {'fields': 'nova_group,product_name'},
                    headers = {'User-Agent': 'DS205-LSE/1.0'}
                )

                except requests.exceptions.ConnectionError:
                    click.echo(f'Connection error for barcode {bc}, skipping')
                    continue

                finally:
                    time.sleep(0.5)

                if resp.status_code == 200:
                    off_data = resp.json().get('product', {})
                    nova_group = off_data.get('nova_group')
                    nova_source = 'OpenFoodFacts'
                    if nova_group is not None:
                        barcode_used = off_data.get('barcode_used') or bc
                        break

            # Add NOVA Group based on MUP ingredients for no matches with OFF

            if nova_group is None:
                ingredients = product.get('ingredients', None)
                if not ingredients or not isinstance(ingredients, str):
                    nova_group = 'Not confirmed UPF'
                    nova_source = 'No ingredients present'

                else:
                    normalised = normalize(ingredients)
                    matched_mups = [term for term in exact_terms if term in normalised]
                    
                    for term in prefix_terms:
                        for word in normalised.split():
                            if word.startswith(term):
                                matched_mups.append(word)
                            
                    if matched_mups:
                        nova_group = 4
                        nova_source = f'MUP Present: {", ".join(matched_mups)}'

            if nova_group is None:
                nova_group = 'Confirmed not UPF'
                nova_source = 'No OFF classification, no MUP present'

            product['nova_group'] = nova_group
            product['nova_source'] = nova_source
            product['barcode_used'] = barcode_used

            click.echo(f'{off_enriched_count}: {product["name"]}: {nova_source}')
            out.write(json.dumps(product) + '\n')
            off_enriched_count += 1

    click.echo(f'Enriched {off_enriched_count} new products with OpenFoodFacts NOVA scores')

@cli.command()
@click.option("--db-path", default=str(DATA_DIR / 'products.db'), show_default=True, help='Output SQLite database path')
def build_db(db_path: str):
    """Build a flat SQLite table from enriched product data. Re-runs append new products and skip duplicates."""

    enriched_file = ENRICHED_DIR / 'products.jsonl'

    if not enriched_file.exists():
        click.echo('No enriched products file found. Run enrich_open_food_facts first.', err=True)
        sys.exit(1)

    df = pd.read_json(enriched_file, lines=True)
    click.echo(f'Loaded {len(df)} enriched products')

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT    NOT NULL,
            url          TEXT    UNIQUE,
            ingredients  TEXT,
            pricing      REAL,
            nova_group   TEXT,
            nova_source  TEXT,
            barcode_used TEXT,
            barcodes     TEXT,
            category_1   TEXT,
            category_2   TEXT,
            category_3   TEXT,
            category_4   TEXT,
            category_5   TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_barcode_used ON products(barcode_used);
        CREATE INDEX IF NOT EXISTS idx_barcodes     ON products(barcodes);
    """)

    def fmt_category(cat):
        """Format a food_type dict as 'id:name', or None if missing."""
        if not isinstance(cat, dict):
            return None
        cat_id   = cat.get('id', '')
        cat_name = cat.get('name', '')
        return f"{cat_id}:{cat_name}" if cat_id or cat_name else None

    inserted = skipped = 0
    nova_counts: dict[str, int] = {}
    missing_ingredients = 0

    for _, row in df.iterrows():
        categories = list(row.get('food_type') or [])
        cats = [fmt_category(categories[i]) if i < len(categories) else None for i in range(5)]

        barcodes = row.get('barcode') or []
        barcode_used = row.get('barcode_used') or None
        barcodes_str = ','.join(barcodes) if not barcode_used else None

        nova_group = row.get('nova_group')
        nova_key   = str(nova_group) if nova_group is not None else 'None'
        nova_counts[nova_key] = nova_counts.get(nova_key, 0) + 1

        if not row.get('ingredients'):
            missing_ingredients += 1

        try:
            cur.execute("""
                INSERT INTO products
                    (name, url, ingredients, pricing, nova_group, nova_source,
                     barcode_used, barcodes,
                     category_1, category_2, category_3, category_4, category_5)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row.get('name'),
                row.get('url'),
                row.get('ingredients'),
                row.get('pricing'),
                str(nova_group) if nova_group is not None else None,
                row.get('nova_source'),
                barcode_used,
                barcodes_str,
                *cats,
            ))
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1

    con.commit()
    con.close()

    # Summary
    click.echo(f'\n--- build_db summary ---')
    click.echo(f'Inserted : {inserted}')
    click.echo(f'Skipped  : {skipped} (already present)')
    click.echo(f'Missing ingredients: {missing_ingredients}')
    click.echo(f'\n NOVA group breakdown:')
    for nova_key in sorted(nova_counts):
        click.echo(f'{nova_key:>30s} : {nova_counts[nova_key]}')
    click.echo(f'\nDatabase written to {db_path}')

if __name__ == "__main__":
    cli()