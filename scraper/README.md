# Scraper 

The scraper scrapes the Waitrose e-commerce website to fetch various information about each food product. The single most important information it returns is a barcode of each product as it is used in the openfoodfacts API to match products. Other inforamtion (i.e. categories) are fetched in case a recommendation system will be implemented in the API part. 

## Strtucture 
Simplified structure of the project is illustrated as follows: 
```
fetch a category page with selenium (middlewares.py) -> fetch each prodcut's url (waitrose.py) -> fetch each product page (middlewears.py) -> parse each product's name, price and barocdes (waitrose.py) -> remove duplicates (pipeline.py) -> output
```
This process is repeated for each category. For this project, we only use the "Frozen" category due to time constraints. 

?Gemini explain the key strucutre that selenium fetches pages for scrapy. Explain concisely. 

## Fetching pages

### Rejecting cookie banners
The code below rejects requests for cookies to proceed to next steps. 

?Gemini explain in one line what requests.meta.get("load_more" ...) does

In the code below, EC.element_to_be_clickable detects the button to rejrect cookies, and clicks on the reject button. The program waits for 3 seconds for the button to appear. If it doesn't it proceeds to the next step. 

?Gemini expalin in one line why logging is used.
```{python}
        # handle the cookie barner if it exists
if request.meta.get("load_more", False):
    while True:
        try:
            element = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid="reject-all"])
            )
            element.click()
            logging.info("Cookie banner closed")
            break
        except:
            logging.info("No cookie banner found")
            break
```

### 
```
        # if the meta information from callback contains "load_more" set to True, we will click on the Load more... buttons
        if request.meta.get("load_more", False):
            while True:
                try:
                    # Wait until the 'Load More' button is clickable
                    # https://selenium-python.readthedocs.io/waits.html

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

        body = self.driver.page_source

        return HtmlResponse(
            url=request.url,
            body=body,
            encoding='utf-8',
            request=request
        )
```



## Parsing
Waitrose.py

?Gemini explain the class structure of waitrose.py concisely


The following function starts request for 
```
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
```