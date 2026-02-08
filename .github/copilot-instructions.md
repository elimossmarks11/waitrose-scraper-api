# AI Agent Instructions for Food Project (DS205 Problem Set 1)

## Project Overview

This is a **two-part web scraping and data enrichment project**:

- **Part A (Scraper)**: Scrapy spider that crawls Waitrose frozen foods using Selenium for JS-heavy pages
- **Part B (API)**: FastAPI service to serve scraped product data (planned)

### Architecture Flow
```
Selenium (load pages) → Scrapy spider (parse) → Pipeline (deduplicate) → JSONL output
```

Key data flow: `scraper/` → `data/scraped/products.json` → `api/` (enrichment planned)

## Environment Setup

**Always activate the `food` conda environment before running any commands:**
```bash
conda activate food
```

Key dependencies from [environment.yml](../environment.yml):
- `scrapy=2.14.1` - Spider framework
- `selenium=4.38.0` - Browser automation for JS rendering
- `fastapi=0.128.0` + `uvicorn=0.40.0` - API server
- `pandas=2.3.3` - Data processing
- `pytest=8.4.2` - Testing

## Scraper Architecture (Part A)

### Multi-Step Data Pipeline

The scraper follows this exact sequence (see [scraper/README.md](../scraper/README.md)):

1. **Selenium middleware** fetches category pages and handles cookie banners
2. **Spider parser** extracts product URLs from category listings
3. **Selenium middleware** loads individual product pages  
4. **Product parser** extracts name, price, barcodes from JSON embedded in HTML (`script#__NEXT_DATA__`)
5. **DuplicatePipeline** deduplicates by product name, merging barcodes across duplicates
6. **Output** as JSONL (one product per line) to `data/scraped/products.json`

### Key Files & Patterns

| File | Purpose |
|------|---------|
| [scraper/supermarkets/spiders/waitrose.py](../scraper/supermarkets/spiders/waitrose.py) | Main spider with `start_requests()`, `parse()`, and `parse_product()` callbacks |
| [scraper/supermarkets/middlewares.py](../scraper/supermarkets/middlewares.py) | SeleniumMiddleware: handles cookie rejection, "Load More" clicks |
| [scraper/supermarkets/pipelines.py](../scraper/supermarkets/pipelines.py) | DuplicatePipeline: deduplicates by name, merges barcodes |
| [scraper/supermarkets/settings.py](../scraper/supermarkets/settings.py) | Scrapy config (USER_AGENT, ROBOTSTXT_OBEY, ITEM_PIPELINES) |

### Development Patterns

**Selenium wait handling** - Always wrap WebDriver waits in try-except:
```python
try:
    element = WebDriverWait(self.driver, 3).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='reject-all']"))
    )
    element.click()
    logging.info("Cookie banner closed")
except:
    logging.info("No cookie banner found")
```

**Callback flow** - Use `meta` dict to pass state between requests:
```python
# In start_requests:
yield scrapy.Request(url=category_url, meta={"load_more": True})

# In middleware:
if request.meta.get("load_more", False):
    # Handle pagination
```

**CSS selectors** - Prefer stable selectors using data attributes:
- Good: `div.content___yamWw` (class from CSS module), `script#__NEXT_DATA__`
- Avoid: positional selectors (fragile with layout changes)

**Data extraction** - Products are embedded in Next.js HTML:
```python
json_text = response.css("script#__NEXT_DATA__::text").get()
data = json.loads(json_text)
product = data.get('props', {}).get('pageProps', {}).get('product', {})
```

## Testing & Debugging

**Run the scraper** (from `scraper/` directory):
```bash
scrapy crawl waitrose
```

**Check logs** - Scraper logs to stdout with LOG_LEVEL="INFO" in settings.py

**Test duplicate handling** - The DuplicatePipeline drops duplicates with warning; barcodes are merged into the first occurrence

## Common Issues & Troubleshooting

- **`scrapy crawl waitrose` fails with command not found**: Environment not activated. Run `conda activate food` first
- **Selenium timeout**: Cookie banner or "Load More" button didn't appear - check CSS selector in middlewares.py against current Waitrose HTML
- **Empty product data**: Verify `script#__NEXT_DATA__` selector matches current Waitrose page structure
- **Duplicates not being dropped**: Check DuplicatePipeline is enabled in `ITEM_PIPELINES` in settings.py

## API Development (Part B - Future)

When implementing the API:
- Use Pydantic models for request/response validation
- Reference enriched product data from `data/processed/` (to be created)
- FastAPI will run on `localhost:8000` with auto-generated docs at `/docs`
- Use `uvicorn` to run: `uvicorn api.main:app --reload`

## Code Standards for This Project

1. **No type hints** - Not used in this codebase; keep consistency
2. **Logging over print** - Use `logging.info()` for spider operations (helps with Scrapy log aggregation)
3. **CSS selectors** - Keep descriptive; add comments explaining why non-obvious selectors are chosen
4. **Docstrings** - Required for complex middleware/pipeline methods; explain *why* not just *what*
5. **Markdown in code** - Use for clarity (e.g., explaining step-by-step scraping logic)
