# Contributing Guidelines

## Environment Setup

```bash
conda env create -f environment.yml
conda activate food
```

If the environment already exists:

```bash
conda env update -f environment.yml --prune
```

## Repository Structure

```
problem-set-1-grayusan/
├── run_pipeline.py              # CLI: enrich, build-db, serve
├── excluded_categories.py       # Category IDs to exclude (household, alcohol)
├── environment.yml
├── scraper/                     # Scrapy spider
│   └── supermarkets/
│       └── spiders/
├── api/                         # FastAPI application
│   ├── main.py                  # Endpoints, helpers, serve command
│   └── models.py                # Pydantic models
├── data/
│   ├── scraped/
│   │   └── products.jsonl       # Raw spider output (gitignored)
│   └── enriched/
│       ├── products.jsonl       # Enriched product data (gitignored)
│       ├── products.db          # SQLite database (gitignored)
│       └── MUP.xlsx             # Markers of ultra-processing lookup table
```

Data files are gitignored. Download them from the OneDrive link in the README and place the `data/` folder in the project root. Alternatively, regenerate from scratch.

The enrichment step takes 3-4 hours due to OFF API rate limiting (0.5s per request across ~6,500 products).

## Running the API

```bash
python run_pipeline.py serve
```

For development with auto-reload:

```bash
cd api
uvicorn main:app --reload
```

Interactive docs at `http://127.0.0.1:8000/docs`.

## Git Workflow

Work on `feature/api` for API development. Never commit Part B work directly to `main`.

```bash
git checkout feature/api
git add .
git commit -m "description of change"
git push origin feature/api
```

## Adding a New Endpoint

1. Define any new response models in `api/models.py` using Pydantic `BaseModel` with `Field` descriptions.
2. Add the route in `api/main.py`. Use parameterised SQL queries (`?` placeholders) to prevent injection.
3. Follow existing patterns: use `get_db()` for database access if refactored, or the global `con` connection. Use `apply_fields()` if the endpoint should support field masking.
4. Add a summary and `response_model` to the decorator for Swagger documentation.

## Adding New MUP Markers

The MUP lookup table (`data/enriched/MUP.xlsx`) contains 109 markers from Neumann et al. (2023). To add or modify markers:

1. Edit `MUP.xlsx`. Each row needs `category`, `mup_id`, `mup_name`, `individual_compound`, `match_type` (either `exact` or `prefix`), and `is_extended`.
2. Re-run enrichment: `python run_pipeline.py enrich-open-food-facts --all`
3. Rebuild the database: `python run_pipeline.py build-db`

Substring matching is used for `exact` terms and `str.startswith()` for `prefix` terms. Be aware that short marker terms may produce false positives (see Limitations in README).

## Adding Excluded Categories

To exclude a new product category (e.g. pet food, household items):

1. Find the Waitrose category ID from the product data or the `/categories` endpoint.
2. Add the ID to `excluded_categories.py` with a comment.
3. Re-run the pipeline to regenerate enriched data and the database.

## Improving Classification Accuracy

Known areas for improvement:

- **OFF barcode mismatches.** Some OFF entries appear to be for different products sharing the same barcode. The `/products/{id}/flag` endpoint supports flagging these for review.
- **MUP false positives.** Substring matching means "starch" matches inside "cornstarch." A word-boundary approach would reduce this but may miss compound terms like "whey protein isolate."
- **Category inference gaps.** 109 products remain "Not confirmed UPF" because they have no ingredients and fall outside the safe category list. Manual review of these categories could reduce this number.

## Code Style

- Type hints on all function signatures.
- Comments explain why, not what.
- Pydantic models include `Field(description=...)` for every field.

This document will be populated with collaboration guidelines developed during DS205 lectures (W03-W04).


## AI tool usage guidelines 

I did not use github copilot for this project, preferring to use dedicated course bot running on Claude Opus 4.6. I made sure it referenced the `copilot-instructions.md` worked on by myself and my partner. If using AI, consult the `copilot-instructions.md`.
