# API

## Data Enrichment Process

## Classification Methodology

Products are classified using a multi-step fallback system. 6,490 products were classified in total.

| `nova_group` | `nova_source` | Count | Explanation |
|---|---|---|---|
| 1 | `OpenFoodFacts` | 215 | NOVA 1 from OFF barcode match. |
| 2 | `OpenFoodFacts` | 65 | NOVA 2 from OFF barcode match. |
| 3 | `OpenFoodFacts` | 550 | NOVA 3 from OFF barcode match. |
| 4 | `OpenFoodFacts` | 1,031 | NOVA 4 from OFF barcode match. |
| 4 | `MUP Present: {markers}` | 2,099 | At least one marker of ultra-processing (MUP) found in ingredients, following Neumann et al.'s approach of using one MUP as evidence of UPF. |
| Not UPF | `Category inference: {category}` | 413 | No ingredients listed; category suggests unprocessed product (see below). |
| Not UPF | `No OFF classification, no MUP present` | 2,008 | Has ingredients but no OFF match and no MUP markers found. |
| Not confirmed UPF | `No ingredients present` | 109 | No ingredients listed and category not in safe inference list. |

### Category inference for products without ingredients

413 products have no ingredients listed and fall into categories where this is expected under [UK food labelling law](https://www.gov.uk/food-labelling-and-packaging/ingredients-list) (single-ingredient or unprocessed products). These are classified as "Not UPF" based on their Waitrose category:

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

Products without ingredients in categories not listed above remain classified as "Not confirmed UPF."

### Excluded categories

Alcohol products (Wine, Beer, Cider, Spirits & Liqueurs, Champagne & Sparkling Wine, Alcohol Free and Low Alcohol Drinks) are excluded from the dataset. NOVA was developed for food and non-alcoholic beverages, and most UPF studies exclude alcohol.

### Limitations

- MUP substring matching may produce false positives where marker terms appear within longer ingredient names.
- E-number prefix ranges capture all E-numbers from e620-e640. E numbers (4 of 109 MUP entries).
- MUP markers are sourced from [Neumann et al. (2023)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10755427/).