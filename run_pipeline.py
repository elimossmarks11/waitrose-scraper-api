import sqlite3
import requests
import json
import sys
import time
import click
import pandas as pd
import re

from pathlib import Path

#############
# CONSTANTS #
#############

DATA_DIR     = Path('data')
SCRAPED_DIR  = DATA_DIR / 'scraped'
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

    scraped_file  = SCRAPED_DIR  / 'products.jsonl'
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
    scraped = [p for p in scraped if not is_excluded(p)]
    click.echo(f'{pre_filter - len(scraped)} non-food products dropped.')

    # Enrich food data with OpenFoodFacts API
    df_mup = pd.read_excel(ENRICHED_DIR / 'MUP.xlsx')

    def strip_asterisks(text):
        return text.replace('*', '')

    exact_terms = set(
        df_mup.loc[df_mup['match_type'] == 'exact', 'mup_name']
        .str.lower().str.strip().apply(strip_asterisks)
    )
    prefix_terms = tuple(
        df_mup.loc[df_mup['match_type'] == 'prefix', 'mup_name']
        .str.lower().str.strip().apply(strip_asterisks)
    )

    def normalize(text):
        return re.sub(r'[^a-zA-Z0-9\s]', '', text.lower())

    NOT_UPF_CATEGORY_IDS = {
        '301142', '303349', '300645', '301139', '301135', '301138',
        '301137', '301136', '301141', '303348', '303357'
    }

    off_enriched_count = 0
    with open(enriched_file, 'a') as out:
        for product in scraped:
            barcodes = product.get('barcode', [])

            if only_new and any(bc in already_done for bc in barcodes):
                continue

            nova_group   = None
            nova_source  = None
            barcode_used = None

            for bc in barcodes:
                try:
                    resp = requests.get(
                        f'https://world.openfoodfacts.org/api/v2/product/{bc}',
                        params={'fields': 'nova_group,product_name'},
                        headers={'User-Agent': 'DS205-LSE/1.0'}
                    )
                except requests.exceptions.ConnectionError:
                    click.echo(f'Connection error for barcode {bc}, skipping')
                    continue
                finally:
                    time.sleep(0.5)

                if resp.status_code == 200:
                    off_data   = resp.json().get('product', {})
                    nova_group = off_data.get('nova_group')
                    if nova_group is not None:
                        nova_group   = str(nova_group)   # ensure string, never int
                        nova_source  = 'OpenFoodFacts'
                        barcode_used = off_data.get('barcode_used') or bc
                        break

            # Add NOVA Group based on MUP ingredients for no matches with OFF
            if nova_group is None:
                ingredients = product.get('ingredients', None)
                if not ingredients or not isinstance(ingredients, str):
                    food_type      = product.get('food_type') or []
                    category_match = None
                    for cat in food_type:
                        if cat['id'] in NOT_UPF_CATEGORY_IDS:
                            category_match = cat['name']
                            break

                    if category_match:
                        nova_group  = 'Not UPF'
                        nova_source = f'Category inference: {category_match}'
                    else:
                        nova_group  = 'Not confirmed UPF'
                        nova_source = 'No ingredients present'
                else:
                    normalised   = normalize(ingredients)
                    matched_mups = [term for term in exact_terms if term in normalised]

                    for term in prefix_terms:
                        for word in normalised.split():
                            if word.startswith(term):
                                matched_mups.append(word)

                    if matched_mups:
                        nova_group  = '4'
                        nova_source = f'MUP Present: {", ".join(matched_mups)}'

            if nova_group is None:
                nova_group  = 'Not UPF'
                nova_source = 'No OFF classification, no MUP present'

            product['nova_group']   = nova_group
            product['nova_source']  = nova_source
            product['barcode_used'] = barcode_used

            click.echo(f'{off_enriched_count}: {product["name"]}: {nova_source}')
            out.write(json.dumps(product) + '\n')
            off_enriched_count += 1

    click.echo(f'Enriched {off_enriched_count} new products with OpenFoodFacts NOVA scores')


@cli.command()
@click.option("--db-path", default=str(ENRICHED_DIR / 'products.db'), show_default=True, help='Output SQLite database path')
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
            id           TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            url          TEXT UNIQUE,
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

    def extract_waitrose_id(url: str | None) -> str | None:
        """Extract the Waitrose product ID from a product URL.

        e.g. '.../bonne-maman-pear-chocolate-mousse-dessert/489078-779911-779912' → '489078'
        Returned as a string to preserve any leading zeros (e.g. '070399').
        Returns None if the URL is missing or doesn't match the expected pattern.
        """
        if not url:
            return None
        match = re.search(r'/(\d+)-\d+-\d+$', url)
        return match.group(1) if match else None

    def fmt_category(cat):
        """Format a food_type dict as 'id:name', or None if missing."""
        if not isinstance(cat, dict):
            return None
        cat_id   = cat.get('id', '')
        cat_name = cat.get('name', '')
        return f"{cat_id}:{cat_name}" if cat_id or cat_name else None

    inserted = skipped = skipped_no_id = 0
    nova_counts: dict[str, int] = {}
    missing_ingredients = 0

    for _, row in df.iterrows():
        waitrose_id = extract_waitrose_id(row.get('url'))

        if waitrose_id is None:
            click.echo(f'Warning: could not extract Waitrose ID for "{row.get("name")}" — skipping', err=True)
            skipped_no_id += 1
            continue

        categories   = list(row.get('food_type') or [])
        cats         = [fmt_category(categories[i]) if i < len(categories) else None for i in range(5)]
        barcodes     = row.get('barcode') or []
        barcodes_str = ','.join(barcodes) if barcodes else None

        barcode_used = row.get('barcode_used')
        barcode_used = str(int(barcode_used)) if pd.notna(barcode_used) else None

        nova_group = row.get('nova_group')
        nova_key   = str(nova_group) if nova_group is not None else 'None'
        nova_counts[nova_key] = nova_counts.get(nova_key, 0) + 1

        if not row.get('ingredients'):
            missing_ingredients += 1

        try:
            cur.execute("""
                INSERT INTO products
                    (id, name, url, ingredients, pricing, nova_group, nova_source,
                     barcode_used, barcodes,
                     category_1, category_2, category_3, category_4, category_5)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                waitrose_id,
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

    click.echo(f'\n--- build_db summary ---')
    click.echo(f'Inserted:            {inserted}')
    click.echo(f'Skipped (duplicate): {skipped}')
    click.echo(f'Skipped (no ID):     {skipped_no_id}')
    click.echo(f'Missing ingredients: {missing_ingredients}')
    click.echo(f'\nNOVA group breakdown:')
    for nova_key in sorted(nova_counts):
        click.echo(f'  {nova_key:>30s} : {nova_counts[nova_key]}')
    click.echo(f'\nDatabase written to {db_path}')

if __name__ == '__main__':
    sys.path.insert(0, 'api')
    from main import cli as main_cli
    cli.add_command(main_cli.commands['serve'], name='serve')
    cli()