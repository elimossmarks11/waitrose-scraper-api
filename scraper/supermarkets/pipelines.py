import json
import logging
from pathlib import Path
from scrapy.exceptions import DropItem


class DuplicatePipeline:
    def __init__(self):
        # Store items by name to handle duplicates
        self.seen_items = {}

    @classmethod
    def from_crawler(cls, crawler):
        """Create pipeline and preload any existing products from the feed file.

        This prevents appending duplicate items when the feed is opened in
        append mode across multiple runs.
        """
        pipeline = cls()
        try:
            output_path = crawler.settings.get('OUTPUT_PATH')
            path = Path(output_path) if output_path else None
            # fallback relative to project root
            if not path or not path.exists():
                path = Path(__file__).resolve().parents[2] / 'data' / 'scraped' / 'products.jsonl'

            if path.exists():
                logging.info("Loading existing products into DuplicatePipeline from %s", path)
                with path.open('r', encoding='utf-8') as fh:
                    for line in fh:
                        try:
                            obj = json.loads(line)
                            name = obj.get('name')
                            if name:
                                pipeline.seen_items[name] = obj
                        except Exception:
                            continue
            else:
                logging.info("No existing products.jsonl found for DuplicatePipeline; starting fresh")
        except Exception as e:
            logging.info("Error loading existing products for DuplicatePipeline: %s", e)

        return pipeline

    def process_item(self, item, spider):
        name = item.get('name')
        new_barcodes = item.get('barcode') or []

        # Check if the product name has been seen before
        if name in self.seen_items:
            existing_item = self.seen_items[name]
            existing_barcodes = existing_item.get('barcode') or []

            # Add new barcodes to the original item's barcode list
            for barcode in new_barcodes:
                if barcode not in existing_barcodes:
                    existing_barcodes.append(barcode)

            raise DropItem(f"Duplicate item found: {item}")

        self.seen_items[name] = item
        return item