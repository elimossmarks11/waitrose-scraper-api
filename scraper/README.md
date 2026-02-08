# Scraper 

Fetches product data from Waitrose for integration with the OpenFoodFacts API, prioritizing barcodes for product matching. Secondary metadata (e.g., categories) supports potential recommendation systems.

## Structure 
In this code, Selenium handles page fetching as requests cannot obtain HTML from the Waitrose website. Therefore, Selenium fetches the web pages and hands them to request to parse the content to return the data.

```
Selenium Middleware (Category Page) -> Spider (Product URLs) -> Selenium Middleware (Product Page) -> Spider (JSON Parsing) -> Pipeline (Deduplication) -> Output
```
Currently restricted to the "Frozen" category.

## Fetching Pages

`SeleniumMiddleware` handle the dynamic parts of the website that regular Scrapy cannot handle.

### Rejecting Cookie Banners
The scraper clicks "Reject All" on the cookie banner so we can see the page content. It waits for the button to appear before clicking.

```py
# scraper/supermarkets/middlewares.py

# handle the cookie banner if it exists
if request.meta.get("load_more", False):
    while True:
        try:
            element = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='reject-all']"))
            )
            element.click()
            logging.info("Cookie banner closed")
            break
        except:
            logging.info("No cookie banner found")
            break
```

### Infinite Scroll Handling 
To get all products, the code keeps clicking the "Load More" button until it disappears. This ensures we load everything on the page.

```py
# scraper/supermarkets/middlewares.py

        # if the meta information from callback contains "load_more" set to True, we will click on the Load more... buttons
        if request.meta.get("load_more", False):
            while True:
                try:
                    # Wait until the 'Load More' button is clickable
                    element = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-shortdescription='Load more products']"))
                    )
                    element.click()
                    logging.info("Clicked 'Load More' button.")
                    # wait a bit for the new products to load
                    time.sleep(1)
            
                except Exception as e:
                    logging.info("No more 'Load More' button found or an error occurred: %s", e)
                    break
```

## Parsing

`WaitroseSpider` manages the crawling lifecycle, from starting the requests to extracting the final data.

### Request Generation
The `start_requests` function kicks off the process for the categories we want, and tells the middleware to handle the "Load More" clicking. In this code, we only scrape the frozen category, but more can be added. 

```py
# scraper/supermarkets/spiders/waitrose.py

def start_requests(self):
    categories = [
        "https://www.waitrose.com/ecom/shop/browse/groceries/frozen"
    ]
    # ... progress bar initialization ...

    for category_url in categories:
    yield scrapy.Request(
        url=category_url, 
        meta={"load_more": True}
    )
```

### Data Extraction
Instead of reading the unorganised HTML, the spider grabs the clean data directly from a hidden JSON script on the page (`__NEXT_DATA__`). This is much more reliable and less likely to break if the website design changes.

```py
# scraper/supermarkets/spiders/waitrose.py

def parse_product(self, response):
    # ...
    json_text = response.css("script#__NEXT_DATA__::text").get()
    
    if json_text:
        data = json.loads(json_text)
        product = data.get('props', {}).get('pageProps', {}).get('product', {})
        # ... field extraction ...
        
        yield {
            "name": product.get("name"),
            "barcode": product.get("barCodes") or [],
            # ...
        }
```

## Pipeline

We check for duplicates. If a product appears more than once, we combine their barcodes so we don't lose any information. This ensures every item in our dataset is unique and complete.

```py
# scraper/supermarkets/pipelines.py

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

        raise DropItem(f"Duplicate item found: {item}")
    
    self.seen_items[name] = item
    return item
```