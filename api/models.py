from pydantic import BaseModel, Field
from typing import Any, Literal, Optional


class WaitroseProduct(BaseModel):
    """Full products details for a product scraped from Waitrose, optionally enriched with NOVA classification"""

    model_config = {
        'json_schema_extra': {
            'examples': [
                {
                    'id': '489078',
                    'name': 'Bonne Maman Pear & Chocolate Mousse Dessert',
                    'url': 'https://www.waitrose.com/ecom/products/bonne-maman-pear-chocolate-mousse-dessert/489078-779911-779912',
                    'ingredients': 'Pears (27%), Cream (Milk) (26%), Whole Milk (26%), Sugar, Dark Chocolate (1.5%) ^Cocoa Mass, Cane Sugar, Cocoa Butter], Cornflour, Milk Chocolate (1.0%) ^Sugar, Whole Milk Powder, Cocoa Butter, Cocoa Mass, Emulsifier (Sunflower Lecithins), Natural Vanilla Flavouring], Pork Gelatine, Concentrated Lemon Juice, Fat-Reduced Cocoa Powder, Cocoa Powder, Gelling Agent (Fruit Pectin), Natural Vanilla Flavouring, Sea Salt',
                    'pricing': 2.3,
                    'nova_group': '4',
                    'nova_source': 'MUP Present: flavour, gelling, emulsif',
                    'barcode_used': None,
                    'barcodes': '3608580098966,3608580140771',
                    'category_1': '10051:Groceries',
                    'category_2': '301134:Fresh & Chilled',
                    'category_3': '301144:Desserts',
                    'category_4': '301277:Single Pots & Multipacks',
                    'category_5': '411065:Desserts for Two'
                }
            ]
        }
    }

    id: Optional[str] = Field(
        default=None,
        description='Waitrose product ID, extracted from the product URL (e.g. for ".../489078-779911-779912", the ID is 489078). Use this to retrieve a single product via GET /products/{id} or to cross-reference directly with the Waitrose website'
    )
    name: str = Field(
        description='Product name as displayed on the Waitrose website'
    )
    url: Optional[str] = Field(
        default=None,
        description='Waitrose product URL (unique per product)'
    )
    ingredients: Optional[str] = Field(
        default=None,
        description='Raw ingredients text as listed on the product page'
    )
    pricing: Optional[float] = Field(
        default=None,
        gt=0,
        description='Product price in GBP'
    )
    nova_group: Optional[Literal['1', '2', '3', '4', 'Not UPF', 'Not confirmed UPF']] = Field(
        default=None,
        description=(
        'NOVA food processing group classification.' 
        '1 = Unprocessed or minimally processed foods;'
        '2 = Processed culinary ingredients;'
        '3 = Processed foods;'
        '4 = Ultra-processed foods (UPF);'
        'Not UPF = Confirmed non-UPF by category inference or absence of MUP;'
        'Not confirmed UPF = Classification not possible due to missing ingredients and OFF data'
        )
    )
    nova_source: Optional[str] = Field(
        default=None,
        description=(
            'Source from which the NOVA group was assigned. One of:'
            '1. OpenFoodFacts;'
            '2. MUP present;'
            '3. No ingredients present;'
            '4. No OFF classification, no MUP present;' 
            '5. Category inference'
        )
    )
    barcode_used: Optional[str] = Field(
        default=None,
        description='The specific barcode used to query OFF API. None if product was classified via MUP or category inference'
    )
    barcodes: Optional[str] = Field(
        default=None,
        description='All barcodes associated with the product, stored as a delimited string'
    )
    category_1: Optional[str] = Field(
        default=None,
        description='Top-level product category including unique Waitrose category ID and category name (e.g. 10051:Groceries)'
    )
    category_2: Optional[str] = Field(
        default=None,
        description='Second-level product category including unique Waitrose category ID and category name (e.g. 301134:Fresh and Chilled)'
    )
    category_3: Optional[str] = Field(
        default=None,
        description='Third-level product category including unique Waitrose category ID and category name (e.g. 301141:Milk, Butter & Eggs)'
    )
    category_4: Optional[str] = Field(
        default=None,
        description='Fourth-level product category including unique Waitrose category ID and category name (e.g. 301241:Milk)'
    )
    category_5: Optional[str] = Field(
        default=None,
        description='Fifth-level product category for granular classification including unique Waitrose category ID and category name (e.g. 301631:Soya & Milk Alternatives)'
    )

class PaginatedResponse(BaseModel):
    """Paginated list of products. The schema for each result reflects all available fields;
    if the `fields` FieldMask parameter was used, only the requested subset of fields will
    be present in each result object."""

    total: int = Field(
        description='Total number of products matching the applied filters, before pagination'
    )
    offset: int = Field(
        description='Number of results skipped (as supplied in the request)'
    )
    limit: Optional[int] = Field(
        default=None,
        description='Maximum number of results returned (as supplied in the request). NULL if no limit was applied'
    )
    results: list[WaitroseProduct] = Field(
        description='Page of matching products. Field presence per product depends on the `fields` FieldMask parameter'
    )

class FlagRequest(BaseModel):
    """Request body for flagging a product for researcher review."""

    reason: str = Field(
        max_length=500,
        description='Reason for flagging this product (e.g. "NOVA classification appears incorrect — product contains additives not detected by MUP matching"). Max 500 characters'
    )
    flagged_by: Optional[str] = Field(
        default=None,
        max_length=100,
        description='Optional identifier for the researcher or team submitting the flag (e.g. name or institution). Max 100 characters'
    )

class FlagResponse(BaseModel):
    """A flag submitted against a product for researcher review."""

    id: int = Field(
        description='Unique flag identifier, auto-assigned by the database'
    )
    product_id: str = Field(
        description='ID of the flagged product'
    )
    reason: str = Field(
        description='Reason provided for the flag'
    )
    flagged_by: Optional[str] = Field(
        default=None,
        description='Researcher or team who submitted the flag, if provided'
    )
    created_at: str = Field(
        description='UTC timestamp at which the flag was created (ISO 8601 format)'
    )

class NearestNonUPFResponse(BaseModel):
    """The closest non-UPF product to a given UPF product, identified by category matching,
    fuzzy name similarity, and ingredient overlap validation."""

    product: WaitroseProduct = Field(
        description='The nearest non-UPF product. Field presence depends on the `fields` FieldMask parameter'
    )
    matched_category_level: int = Field(
        ge=0, le=5,
        description=(
            'The deepest category level at which the source and nearest product share a category '
            '(1 = top-level only, 5 = matched at the most granular level). '
            '0 indicates no category overlap was found and the match is based on name similarity alone'
        )
    )

    name_similarity: float = Field(
        ge=0, le=1,
        description='SequenceMatcher ratio (0–1) between the source product name and the nearest match. 1.0 = identical names'
    )

    ingredient_overlap: Optional[float] = Field(
        default=None,
        ge=0, le=1,
        description=(
            'Jaccard similarity (0–1) between the tokenised ingredient lists of the source product and the nearest match. '
            'NULL if either product has no ingredients list — see `validated`'
        )
    )

    validated: bool = Field(
        description=(
            'Whether the match was confirmed by ingredient overlap (Jaccard ≥ 0.15). '
            'False if either product lacks an ingredients list, or if no candidate exceeded the threshold. '
            'Although researchers should treat unvalidated matches with caution, in most cases this reflects '
            'fresh or loose products where no ingredients list is present on the Waitrose website'
        )
    )