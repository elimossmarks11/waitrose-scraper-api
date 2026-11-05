# Eli Moss-Marks Waitrose NOVA API

A FastAPI application serving NOVA food processing classifications for 6,490 Waitrose grocery products. Built to answer: **What proportion of groceries on a UK supermarket website is ultra-processed?**

## Data Storage

Large data files are not stored on git. Find them on [OneDrive](https://1drv.ms/f/c/fc22bcd7c8c6f08b/IgDQ1Bc-CFTSTZAR-XiqGq5UAfoDWk9jjBbEod2lvLEV81g?e=hpAI7S)

## Setup

### On Nuvolos

```bash
conda env create -f environment.yml
conda activate food
python run_pipeline.py serve
```

Docs available at `https://<your-nuvolos-url>/proxy/8000/docs`.

### Locally

```bash
conda env create -f environment.yml
conda activate food
python run_pipeline.py serve
```

Docs available at `http://127.0.0.1:8000/docs`.

If the environment already exists, update it with:

```bash
conda env update -f environment.yml --prune
```

The serve command detects the environment automatically and configures the host, port, and proxy settings accordingly.

## Data Pipeline

The API serves data produced by a three-stage pipeline:

```
data/scraped/products.jsonl  →  data/enriched/products.jsonl  →  data/enriched/products.db
        (scraper)                    (enrichment)                     (build-db)
```

After scraping (see scraper documentation) run the full enrichment and api building pipeline from the project root:

```bash
python run_pipeline.py enrich-open-food-facts --all
python run_pipeline.py build-db
python run_pipeline.py serve
```

The `--only-new` flag (default) skips products already enriched, allowing incremental runs.

## Technical Details

### Environment detection

The app detects Nuvolos by checking whether the HOSTNAME environment variable starts with nv-. On Nuvolos, it sets `root_path="/proxy/8000/"` so Swagger UI loads correctly through the proxy. Locally, no proxy configuration is needed. The same codebase runs on both platforms without manual changes.

### Database connection

On startup, the app opens a single persistent SQLite connection and creates the flags table if it doesn't exist. The connection closes automatically on shutdown. All endpoints query the database per request rather than loading data into memory, which keeps filtered queries fast on the 6,490 product dataset.

### Nearest non-UPF matching

The `/products/{id}/nearest_non_upf` endpoint finds the closest non-UPF alternative to a given UPF product using a three-step process:

1. Category narrowing

Starting from the deepest category level (5), the algorithm looks for non-UPF products sharing the same category. It uses the deepest level where at least one candidate exists. For example, if a UPF pizza shares category_5 with no non-UPF products but shares category_4 with several, matching happens at level 4.

2. Name similarity ranking

Within the matched category, candidates are sorted by fuzzy name similarity using difflib.SequenceMatcher. This favours products with similar names (e.g. a UPF chicken pie ranks closest to a non-UPF chicken pie rather than a non-UPF vegetable pie).

3. Ingredient validation 

The top candidates are checked for ingredient overlap using Jaccard similarity on tokenised ingredient lists. A threshold of 0.15 confirms the match is meaningful rather than coincidental. If either product lacks ingredients, or no candidate exceeds the threshold, the match is returned as unvalidated.

The response includes `matched_category_level, name_similarity, ingredient_overlap`, and a `validated` flag so researchers can assess match quality.

### Product flagging

The `POST /products/{id}/flag` endpoint allows researchers to flag products for review (e.g. suspected misclassification). Flags are stored in a separate flags table with a reason, optional identifier, and timestamp. This supports iterative data quality improvement without modifying the core product data.

### Field masking
All list and detail endpoints accept a fields parameter for returning a subset of product fields. This reduces response size when only specific data is needed (e.g. `fields=name,nova_group,pricing`). Invalid field names return a 422 error listing valid options.

## Classification Methodology

Products are classified using a multi-step fallback system. 6,490 products were classified in total.

| `nova_group` | `nova_source` | Count | Explanation |
|---|---|---|---|
| 1 | `OpenFoodFacts` | 215 | NOVA 1 from OFF barcode match. |
| 2 | `OpenFoodFacts` | 65 | NOVA 2 from OFF barcode match. |
| 3 | `OpenFoodFacts` | 550 | NOVA 3 from OFF barcode match. |
| 4 | `OpenFoodFacts` | 1,031 | NOVA 4 from OFF barcode match. |
| 4 | `MUP Present: {markers}` | 2,099 | At least one marker of ultra-processing found in ingredients, following Neumann et al.'s approach of using one MUP as evidence of UPF. |
| Not UPF | `Category inference: {category}` | 413 | No ingredients listed; category suggests unprocessed product. |
| Not UPF | `No OFF classification, no MUP present` | 2,008 | Has ingredients but no OFF match and no MUP markers found. |
| Not confirmed UPF | `No ingredients present` | 109 | No ingredients listed and category not in safe inference list. |

### Enrichment fallback order

1. **OpenFoodFacts barcode lookup.** Each product's barcodes are queried against the OFF API. If OFF returns a NOVA group, it is used directly.
2. **MUP ingredient analysis.** If OFF has no classification, the product's ingredients are checked for markers of ultra-processing from [Neumann et al. (2023)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10755427/). Any match classifies the product as NOVA 4. All matched markers are recorded.
3. **Category inference.** If no ingredients are listed and the product belongs to a category where this is expected (fresh fruit, vegetables, meat, cheese, etc.), it is classified as "Not UPF."
4. **Default.** Products with ingredients but no OFF match and no MUP markers are "Not UPF." Products with no ingredients and no safe category inference are "Not confirmed UPF."

### Category inference for products without ingredients

413 products have no ingredients listed and fall into categories where this is expected under [UK food labelling law](https://www.gov.uk/food-labelling-and-packaging/ingredients-list) (single-ingredient or unprocessed products):

| Category | Count |
|---|---|
| Fresh Vegetables | 136 |
| Fresh Fruit | 104 |
| Fresh Salad & Herbs | 75 |
| Milk, Butter & Eggs | 23 |
| Cheese | 19 |
| Coffee | 17 |
| Fresh Chicken & Poultry | 13 |
| Dried Herbs, Oils & Vinegar | 8 |
| Tea | 8 |
| Water | 7 |
| Fresh Meat | 3 |

### Excluded categories

Alcohol products (Wine, Beer, Cider, Spirits & Liqueurs, Champagne & Sparkling Wine, Alcohol Free and Low Alcohol Drinks) are excluded. NOVA was developed for food and non-alcoholic beverages, and most UPF studies exclude alcohol.

### Limitations / Acknowledgments

- **MUP substring matching** may produce false positives where marker terms appear within longer ingredient names (e.g. "starch" matching inside "cornstarch").
- **OFF data quality.** OFF classifications are community-contributed and may contain errors. Manual spot-checking identified at least one case (fresh apples classified as NOVA 4) where the OFF data appears incorrect.
- **MUP markers** are sourced from [Neumann et al. (2023)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10755427/).