import json
import scrapy
from tqdm import tqdm


class WaitroseSpider(scrapy.Spider):
    name = "waitrose"
    allowed_domains = ["www.waitrose.com"]

    def start_requests(self):
        categories = [
            "https://www.waitrose.com/ecom/shop/browse/groceries/frozen"
        ]
        self.category_bar = tqdm(total=len(categories), desc="Categories")
        self.product_bar = None
        self.product_count = 0

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
                yield scrapy.Request(
                    url=response.urljoin(product_url),
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
            }