from scrapy.exceptions import DropItem 

class DuplicatePipeline:
    def __init__(self):
        # Store items by name to handle duplicates
        self.seen_items = {}

    def process_item(self, item, spider):
        name = item.get('name')
        new_barcodes = item.get('barcode')

        # Check if the product name has been seen before
        if name in self.seen_items:
            existing_item = self.seen_items[name]
            existing_barcodes = existing_item.get('barcode')

            # Add new barcodes to the original item's barcode list
            for barcode in new_barcodes:
                if barcode not in existing_barcodes:
                    existing_barcodes.append(barcode)
                    # print(f"Added new barcode {barcode} to existing item {name}")

            raise DropItem(f"Duplicate item found: {item}")
        
        self.seen_items[name] = item
        return item