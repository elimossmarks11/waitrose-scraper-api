import click
import sys
import json
import requests
import subprocess

import pandas as pd

from pathlib import Path


#############
# CONSTANTS #
#############

DATA_DIR = Path('data')
SCRAPED_DIR = DATA_DIR / 'scraped'
ENRICHED_DIR = DATA_DIR / 'enriched'

################
# CLI COMMANDS #
################

@click.grou()
def cli():
    """Pipeline for enriching and serving Waitrose product data."""
    pass

@cli.command()
@click.option("--only-new/--all", default=True, help='Skip already-enriched products')
def enrich_open_food_facts(only_new: bool):
    """Match scraped products to a NOVA classification either using OpenFoodFacts or MUP.csv and save to data/enriched/."""

    ENRICHED_DIR.mkdir(parents=True, exist_ok=True)

    scraped_file = SCRAPED_DIR / 'products.jsonl'
    enriched_file = ENRICHED_DIR / 'products.jsonl'

    scraped = pd.read_json(scraped_file, lines=True).to_dict(orient='records')
    click.echo(f'Loaded {len(scraped)} scraped products')

    already_done: set[str] = set()
    if only_new and enriched_file.exists():
        enriched_df = pd.read_json(enriched_file, lines=True)
        for barcodes in enriched_df['barcode']:
            for bc in barcodes:
                already_done.add(bc)
        click.echo(f'Skipping {len(already_done)} already-enriched barcodes')

    off_enriched_count = 0
    no_matches = []
    with open(enriched_file, 'a') as out:
        for product in scraped:
            barcodes = product.get('barcode', [])

            if only_new and any(bc in already_done for bc in barcodes):
                continue

            nova_group = None
            for bc in barcodes:
                resp = requests.get(
                    f'https://world.openfoodfacts.org/api/v2/product/{bc}',
                    params = {'fields': 'nova_group,product_name'},
                    headers = {'User-Agent': 'DS205-LSE/1.0'}
                )
                if resp.status_code == 200:
                    off_data = resp.json().get('product', {})
                    nova_group = off_data.get('nova_group')
                    if nova_group is not None:
                        break
        
                else:
                    no_matches.append(product)

            product['nova_group'] = nova_group
            out.write(json.dumps(product) + '\n')
            off_enriched_count += 1

    click.echo(f'Enriched {off_enriched_count} new products with OpenFoodFacts NOVA scores')

    def generate_NOVA_classification(product):
        mup_file = ENRICHED_DIR / 'MUP.csv'
        product_ingredients = product['ingredients']


    for product in no_matches:
        generate_NOVA_classification(product)
        
        

