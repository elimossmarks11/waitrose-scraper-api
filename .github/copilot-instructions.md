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

## API Architecture (Part B)

### Key Files

| File | Purpose |
|------|---------|
| [api/main.py](../api/main.py) | FastAPI app, all endpoints, helpers, CLI serve command |
| [api/models.py](../api/models.py) | Pydantic models: WaitroseProduct, PaginatedResponse, FlagRequest/Response, NearestNonUPFResponse |
| [run_pipeline.py](../run_pipeline.py) | CLI: enrich-open-food-facts, build-db, serve |
| [excluded_categories.py](../excluded_categories.py) | Category IDs filtered out (household items, alcohol) |
| [data/enriched/MUP.xlsx](../data/enriched/MUP.xlsx) | Markers of ultra-processing lookup table (Neumann et al. 2023) |

### Enrichment Pipeline

The `enrich-open-food-facts` command classifies each product through a fallback chain:

1. Query OpenFoodFacts API by barcode (0.5s rate limit, try/except for connection errors)
2. If no OFF match: substring-match ingredients against MUP markers (exact and prefix)
3. If no ingredients: infer from category (fresh fruit, vegetables, etc. are "Not UPF")
4. Default: products with ingredients but no markers are "Not UPF"

All classifications are stored as `nova_group` and `nova_source` in the enriched JSONL.

### Database

`build-db` reads the enriched JSONL and creates a flat SQLite table. Product IDs are extracted from Waitrose URLs (e.g. `.../489078-779911-779912` becomes `489078`). The API queries this database per request rather than loading into memory.

### Endpoints

- `GET /products` - Browse and filter with pagination, category filtering, price range, field masking
- `GET /products/{id}` - Single product by Waitrose ID
- `GET /products/{id}/nearest_non_upf` - Nearest non-UPF alternative (category narrowing → name similarity → Jaccard ingredient validation)
- `POST /products/{id}/flag` - Flag product for researcher review
- `GET /categories` - Distinct category values with counts
- `GET /stats` - Dataset summary (UPF proportion, NOVA breakdown, average prices)

### Development Patterns

**Database queries** - Always use parameterised queries (`?` placeholders):

```python
row = con.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
```

**Pydantic models** - All response models use `Field(description=...)`. New models go in `models.py`.

**Nuvolos detection** - `_is_running_on_nuvolos()` checks `HOSTNAME` env var. Affects `root_path` and default host/port.

**Field masking** - `apply_fields()` filters response dicts to requested fields. Returns 422 for invalid field names.

**Category matching** - Categories stored as `id:name` strings. `category_name()` extracts the name portion for fuzzy substring matching.

## Code Standards for This Project

1. **No type hints** - Not used in this codebase; keep consistency
2. **Logging over print** - Use `logging.info()` for spider operations (helps with Scrapy log aggregation)
3. **CSS selectors** - Keep descriptive; add comments explaining why non-obvious selectors are chosen
4. **Docstrings** - Required for complex middleware/pipeline methods; explain *why* not just *what*
5. **Markdown in code** - Use for clarity (e.g., explaining step-by-step scraping logic)
