from scrapy.http import HtmlResponse
from selenium import webdriver
from scrapy import signals
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
import time
import logging

# chromium issue on nuvolos: solves it 
import shutil
from selenium.webdriver.chrome.service import Service

# Add logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SeleniumMiddleware:
    """Middleware that uses Selenium to render JavaScript-heavy pages."""

    def __init__(self):
        self.driver = None

    # Explain
    @classmethod
    def from_crawler(cls, crawler):
        """This method is called by Scrapy to create the middleware instance."""
        middleware = cls()
        
        crawler.signals.connect(middleware.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(middleware.spider_closed, signal=signals.spider_closed)
        
        return middleware

    def spider_opened(self, spider):
        """Create the browser when the spider starts."""
        options = Options()
        # options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0")

        chromium_path = shutil.which("chromium") or shutil.which("google-chrome")
        if chromium_path:
            options.binary_location = chromium_path

        chromedriver_path = shutil.which("chromedriver")
        service = Service(chromedriver_path) if chromedriver_path else Service()

        self.driver = webdriver.Chrome(service=service, options=options)

    def spider_closed(self, spider):
        """Close the browser when the spider finishes."""
        if self.driver:
            self.driver.quit()

    def process_request(self, request, spider):    
        """Intercept requests and load them in Selenium."""
        self.driver.get(request.url)
        
        # handle the cookie barner if it exists
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

        # if the meta information from callback contains "load_more" set to True, we will click on the Load more... buttons
        if request.meta.get("load_more", False):
            while True:
                try:
                    # Wait until the 'Load More' button is clickable
                    # https://selenium-python.readthedocs.io/waits.html

                    element = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-shortdescription='Load more products']"))
                    )

                    # Scroll to the button and click it using JavaScript to ensure it works even if the button is not fully in view
                    # arguments[0] refers to the element we want to interact with, and block: 'center' scrolls it to the center of the view
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                    self.driver.execute_script("arguments[0].click();", element)
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