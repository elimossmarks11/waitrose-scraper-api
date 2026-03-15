# Scraper

Fetches product data from Waitrose for integration with the OpenFoodFacts API, prioritising barcodes for product matching. Secondary metadata (e.g., categories) supports potential recommendation systems.

## Usage

To scrape data, run the following command inside the `scraper` directory after activating the virtual environment:

```
scrapy crawl waitrose
```

Running this command outputs scraped data in JSONL format to `../data/scraped/products.jsonl`.

## Output

Each product record contains the following fields:

| Field       | Description                                                                 |
|-------------|-----------------------------------------------------------------------------|
| `name`      | Product name                                                                |
| `barcode`   | List of barcodes (a single product may have multiple)                       |
| `url`       | Product page URL on Waitrose                                                |
| `food_type` | Hierarchical categories for the products                 |
| `pricing`   | Price in GBP as a float                                                     |

**Important notes for the next contributor:**

1. A single product may have multiple barcodes. If two products share the same name but differ in weight, the scraper automatically aggregates their barcodes under one entry and removes the duplicate. This ensures the API can match products using any of their associated barcodes. However, not all barcodes have corresponding entries in the OpenFoodFacts API.
2. The returned categories are hierarchical — each level is more specific than the last.

## Design Decisions

- **Selenium over plain HTTP requests** — Waitrose relies heavily on client-side JavaScript rendering; standard HTTP requests cannot obtain the full HTML. Selenium fetches the pages, then hands the rendered HTML to Scrapy for parsing.
- **JSON extraction instead of HTML scraping** — Rather than parsing fragile HTML selectors, the spider extracts data from a hidden `__NEXT_DATA__` JSON script tag embedded in each product page. This is more reliable and less likely to break when the site's design changes.
- **Barcode deduplication** — The pipeline merges barcodes for products that appear more than once (e.g., same product with different weights), ensuring each item in the dataset is unique and complete.
- **Frozen category only** — The scraper currently restricts its attention to the "Frozen" category to keep run times manageable. Adding more categories is straightforward (see `start_requests` in the spider), but increases wait time significantly.

## Architecture

```
Selenium Middleware (Category Page) → Spider (Product URLs) → Selenium Middleware (Product Page) → Spider (JSON Parsing) → Pipeline (Deduplication) → Output
```

For code-level details on how each component works, see the [CONTRIBUTING.md](../CONTRIBUTING.md).