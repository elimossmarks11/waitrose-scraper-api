import json
import scrapy
import logging
from pathlib import Path
from tqdm import tqdm
from w3lib.html import remove_tags


class WaitroseSpider(scrapy.Spider):
    name = "waitrose"
    allowed_domains = ["www.waitrose.com"]

    def start_requests(self):
        categories = [
            "https://www.waitrose.com/ecom/shop/browse/groceries/frozen",
            'https://www.waitrose.com/ecom/shop/browse/groceries/fresh_and_chilled',
            'https://www.waitrose.com/ecom/shop/browse/groceries/bakery',
            'https://www.waitrose.com/ecom/shop/browse/groceries/food_cupboard',
            'https://www.waitrose.com/ecom/shop/browse/groceries/organic_shop',
            'https://www.waitrose.com/ecom/shop/browse/groceries/dietary_and_lifestyle'
        ]
        self.category_bar = tqdm(total=len(categories), desc="Categories")
        self.product_bar = None
        self.product_count = 0

        # Load already-scraped product URLs so we don't re-scrape them
        # If the `FORCE_RESCRAPE` setting is True, skip loading to force full re-scrape
        self.scraped_urls = set()
        try:
            if self.settings.get('FORCE_RESCRAPE', False):
                logging.info("FORCE_RESCRAPE enabled: skipping load of existing scraped URLs")
            else:
                output_path = self.settings.get('OUTPUT_PATH')
                path = Path(output_path) if output_path else None
                # fallback: look for data/scraped/products.jsonl relative to project root
                if not path or not path.exists():
                    path = Path(__file__).resolve().parents[4] / 'data' / 'scraped' / 'products.jsonl'

                if path.exists():
                    logging.info(f"Loading already-scraped URLs from {path}")
                    with path.open('r', encoding='utf-8') as fh:
                        for line in fh:
                            try:
                                obj = json.loads(line)
                                url = obj.get('url')
                                if url:
                                    self.scraped_urls.add(url)
                            except Exception:
                                continue
                else:
                    logging.info("No existing products.jsonl found; full scrape will run")
        except Exception as e:
            logging.info(f"Error loading existing scraped URLs: {e}")

        for category_url in categories:
            yield scrapy.Request(
               url=category_url, 
               meta={"load_more": True}
            )

    def parse(self, response):
        # display the current category's name as the progress bar's description
        products = response.css("div.content___yamWw")
        self.product_count = len(products)

        category_name = response.url.split("/")[-1]
        self.product_bar = tqdm(total=self.product_count, desc=f"Products in {category_name}")

        for product in products:
            product_url = product.css("a::attr(href)").get()
            if product_url:
                full_url = response.urljoin(product_url)
                if full_url in getattr(self, 'scraped_urls', set()):
                    logging.info(f"Skipping already-scraped product: {full_url}")
                    # update progress bar since this product is considered processed
                    if self.product_bar:
                        self.product_bar.update(1)
                    continue

                yield scrapy.Request(
                    url=full_url,
                    callback=self.parse_product
                )

        self.category_bar.update(1)

    def parse_product(self, response):
        # Update progress when product is actually scraped
        self.product_bar.update(1)

        json_text = response.css("script#__NEXT_DATA__::text").get()
        
        if json_text:
            data = json.loads(json_text)
            product = data.get('props', {}).get('pageProps', {}).get('product', {})
            categories = product.get("categories", [])
            pricing = product.get("pricing", {})
            contents = product.get('contents', {})
            
            yield {
                "name": product.get("name"),
                "barcode": product.get("barCodes") or [],
                # "main_category": categories[1].get("name") if len(categories) > 1 else None,
                # "sub_category": categories[2].get("name") if len(categories) > 2 else None,
                # "sub_2_category": categories[3].get("name") if len(categories) > 3 else None,
                # "sub_3_category": categories[4].get("name") if len(categories) > 4 else None,
                "url": response.url,
                "food_type": categories,
                # returns the float format 
                "pricing": float(pricing.get("displayPrice", "").replace("£", "")) if pricing.get("displayPrice") else None,
                'ingredients': remove_tags(contents.get("ingredients", "")).strip() if contents.get("ingredients") else None,
            }