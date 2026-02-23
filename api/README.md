# API

## Data Enrichment Process

### Classification Methodology

Products are classified using a multi-step fallback system:

| `nova_group` | `nova_source` | Explanation |
|---|---|---|
| 1, 2, 3, or 4 | `OpenFoodFacts` | NOVA group provided directly by OpenFoodFacts via barcode match. |
| 4 | `MUP_present: {ingredient}` | At least one marker of ultra-processing (MUP) found in ingredients, following Neumann et al.'s approach of using one MUP as evidence of UPF. |
| Not confirmed UPF | `No ingredients present` | Product has no ingredients listed. [UK law](https://www.gov.uk/food-labelling-and-packaging/ingredients-list) only requires ingredients lists for products with two or more ingredients, so these are likely unprocessed foods. Classified conservatively to account for possible inconsistencies in Waitrose product data. |
| Confirmed not UPF | `No OFF classification, no MUP present` | Product has ingredients but no MUP markers were found and OFF had no classification. |

### Limitations

- MUP substring matching may produce false positives where marker terms appear within longer ingredient names. 
- MUP prefix matches are approximate. These account for only 4 of 109 MUP entries.
- MUP markers are sourced from [Neumann et al. (2023)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10755427/).