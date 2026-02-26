import os
import re
import sqlite3
import difflib
from contextlib import asynccontextmanager
from pathlib import Path

import click
import uvicorn
from fastapi import FastAPI, HTTPException, Query

from models import (
    WaitroseProduct,
    PaginatedResponse,
    FlagRequest,
    FlagResponse,
    NearestNonUPFResponse,
)

#############
# CONSTANTS #
#############

DB_PATH = Path(__file__).parent.parent / 'data' / 'enriched' / 'products.db'
VALID_NOVA_GROUPS = {'1', '2', '3', '4', 'Not UPF', 'Not confirmed UPF'}
UPF_GROUPS        = {'4', 'Not confirmed UPF'}
NON_UPF_GROUPS    = {'1', '2', '3', 'Not UPF'}
JACCARD_THRESHOLD = 0.15

VALID_FIELDS = {
    'id', 'name', 'url', 'ingredients', 'pricing',
    'nova_group', 'nova_source', 'barcode_used', 'barcodes',
    'category_1', 'category_2', 'category_3', 'category_4', 'category_5',
}

#####################
# NUVOLOS DETECTION #
#####################

def _is_running_on_nuvolos() -> bool:
    """Running on Nuvolos Cloud iff HOSTNAME starts with 'nv-'."""
    hostname = os.getenv('HOSTNAME')
    return hostname is not None and hostname.startswith('nv-')

###########
# STARTUP #
###########

con: sqlite3.Connection

@asynccontextmanager
async def lifespan(app: FastAPI):
    global con
    con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE IF NOT EXISTS flags (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id  TEXT    NOT NULL,
            reason      TEXT    NOT NULL,
            flagged_by  TEXT,
            created_at  TEXT    DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_flags_product ON flags(product_id);
    """)
    con.commit()
    yield
    con.close()

#######
# APP #
#######

if _is_running_on_nuvolos():
    app = FastAPI(root_path='/proxy/8000/', title='Waitrose NOVA API', lifespan=lifespan)
else:
    app = FastAPI(title='Waitrose NOVA API', lifespan=lifespan)

###########
# HELPERS #
###########

def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)

def apply_fields(records: list[dict], fields: str | None) -> list[dict]:
    if not fields:
        return records
    field_set = {f.strip() for f in fields.split(',')}
    invalid = field_set - VALID_FIELDS
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid fields: {sorted(invalid)}. Valid fields: {sorted(VALID_FIELDS)}"
        )
    return [{k: v for k, v in r.items() if k in field_set} for r in records]

def category_name(cat_str: str | None) -> str:
    """Extract the human-readable portion after ':' for fuzzy matching."""
    if not cat_str:
        return ''
    return cat_str.split(':', 1)[-1].lower()

def fuzzy_category_match(query: str, cat_str: str | None) -> bool:
    return query.lower() in category_name(cat_str)

def normalise_tokens(text: str) -> set[str]:
    return set(re.sub(r'[^a-zA-Z0-9\s]', '', text.lower()).split())

def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

def name_sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()

##########
# ROUTES #
##########

FIELDS_DESCRIPTION = (
    f'Comma-separated subset of fields to return (FieldMask). '
    f'Valid values: {", ".join(sorted(VALID_FIELDS))}. '
    f'Defaults to all fields. Note: the response schema shown below reflects all possible '
    f'fields — only the requested subset will be present in each result when this parameter is used.'
)

@app.get(
    '/products',
    summary='Browse and filter products',
    response_model=PaginatedResponse,
)
def get_products(
    category_1:    str | None   = Query(default=None, description='Fuzzy filter on top-level category name (matches substring after ":")'),
    category_2:    str | None   = Query(default=None, description='Fuzzy filter on second-level category name'),
    category_3:    str | None   = Query(default=None, description='Fuzzy filter on third-level category name'),
    category_4:    str | None   = Query(default=None, description='Fuzzy filter on fourth-level category name'),
    category_5:    str | None   = Query(default=None, description='Fuzzy filter on fifth-level category name'),
    name_contains: str | None   = Query(default=None, description='Case-insensitive substring search on product name'),
    nova_group:    str | None   = Query(default=None, description="Filter by NOVA group: 1, 2, 3, 4, 'Not UPF', 'Not confirmed UPF'"),
    nova_source:   str | None   = Query(default=None, description='Case-insensitive substring search on nova_source'),
    min_price:     float | None = Query(default=None, ge=0, description='Minimum price in GBP (inclusive)'),
    max_price:     float | None = Query(default=None, ge=0, description='Maximum price in GBP (inclusive)'),
    fields:        str | None   = Query(default=None, description=FIELDS_DESCRIPTION),
    limit:         int | None   = Query(default=20, ge=1, le=None, description='Max results to return. Large results may be slow to process'),
    offset:        int          = Query(default=0, ge=0, description='Number of results to skip'),
):
    if nova_group and nova_group not in VALID_NOVA_GROUPS:
        raise HTTPException(
            status_code=422,
            detail=f"nova_group must be one of: {sorted(VALID_NOVA_GROUPS)}"
        )

    # SQL handles all scalar filters; category fuzzy matching happens in Python below
    conditions, params = [], []
    if name_contains:
        conditions.append("name LIKE ?")
        params.append(f'%{name_contains}%')
    if nova_group:
        conditions.append("nova_group = ?")
        params.append(nova_group)
    if nova_source:
        conditions.append("nova_source LIKE ?")
        params.append(f'%{nova_source}%')
    if min_price is not None:
        conditions.append("pricing >= ?")
        params.append(min_price)
    if max_price is not None:
        conditions.append("pricing <= ?")
        params.append(max_price)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ''
    rows = [row_to_dict(r) for r in con.execute(f"SELECT * FROM products {where}", params).fetchall()]

    # Fuzzy category filtering — substring match on name portion of each category field
    for level, val in enumerate([category_1, category_2, category_3, category_4, category_5], start=1):
        if val is not None:
            rows = [r for r in rows if fuzzy_category_match(val, r.get(f'category_{level}'))]

    total = len(rows)
    paged = rows[offset: offset + limit] if limit else rows[offset:]

    return PaginatedResponse(
        total=total,
        offset=offset,
        limit=limit,
        results=apply_fields(paged, fields),
    )

@app.get(
    '/products/{product_id}',
    summary='Retrieve a single product by ID',
    response_model=WaitroseProduct,
)
def get_product(
    product_id: str,
    fields: str | None = Query(default=None, description=FIELDS_DESCRIPTION),
):
    row = con.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f'Product {product_id} not found')
    return apply_fields([row_to_dict(row)], fields)[0]


@app.get(
    '/products/{product_id}/nearest_non_upf',
    summary='Find the nearest non-UPF product to a given UPF product',
    response_model=NearestNonUPFResponse,
)
def nearest_non_upf(product_id: str):
    row = con.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f'Product {product_id} not found')

    product = row_to_dict(row)
    if product.get('nova_group') not in UPF_GROUPS:
        raise HTTPException(status_code=400, detail='Product is not classified as UPF or Not confirmed UPF')

    candidates = [
        row_to_dict(r)
        for r in con.execute(
            f"SELECT * FROM products WHERE nova_group IN ({','.join('?'*len(NON_UPF_GROUPS))})",
            list(NON_UPF_GROUPS),
        ).fetchall()
    ]
    if not candidates:
        raise HTTPException(status_code=404, detail='No non-UPF candidates found in dataset')

    # Step 1 — narrow to deepest shared category level
    matched_level = 0
    for level in range(5, 0, -1):
        field  = f'category_{level}'
        target = product.get(field)
        if not target:
            continue
        level_candidates = [c for c in candidates if c.get(field) == target]
        if level_candidates:
            candidates    = level_candidates
            matched_level = level
            break

    # Step 2 — sort by fuzzy name similarity
    target_name = product.get('name', '')
    candidates.sort(key=lambda c: name_sim(target_name, c.get('name', '')), reverse=True)

    # Step 3 — ingredient validation (Jaccard, Option A disqualification filter)
    # If target has no ingredients we cannot validate; return best name match flagged unvalidated
    target_ingredients = product.get('ingredients')
    target_tokens      = normalise_tokens(target_ingredients) if target_ingredients else set()

    if not target_tokens:
        best = candidates[0]
        return NearestNonUPFResponse(
            product=best,
            matched_category_level=matched_level,
            name_similarity=round(name_sim(target_name, best.get('name', '')), 3),
            ingredient_overlap=None,
            validated=False,
        )

    # Walk candidates (already sorted by name sim) and return first that passes Jaccard threshold
    best_unvalidated     = candidates[0]
    best_unvalidated_sim = name_sim(target_name, best_unvalidated.get('name', ''))

    for candidate in candidates:
        cand_ingredients = candidate.get('ingredients')
        if not cand_ingredients:
            continue
        overlap = jaccard(target_tokens, normalise_tokens(cand_ingredients))
        if overlap >= JACCARD_THRESHOLD:
            return NearestNonUPFResponse(
                product=candidate,
                matched_category_level=matched_level,
                name_similarity=round(name_sim(target_name, candidate.get('name', '')), 3),
                ingredient_overlap=round(overlap, 3),
                validated=True,
            )

    # No validated match — return best name-similarity match, flagged unvalidated
    return NearestNonUPFResponse(
        product=best_unvalidated,
        matched_category_level=matched_level,
        name_similarity=round(best_unvalidated_sim, 3),
        ingredient_overlap=None,
        validated=False,
    )


@app.post(
    '/products/{product_id}/flag',
    summary='Flag a product for researcher review',
    response_model=FlagResponse,
)
def flag_product(product_id: str, body: FlagRequest):
    if not con.execute("SELECT 1 FROM products WHERE id = ?", (product_id,)).fetchone():
        raise HTTPException(status_code=404, detail=f'Product {product_id} not found')
    cur = con.execute(
        "INSERT INTO flags (product_id, reason, flagged_by) VALUES (?, ?, ?)",
        (product_id, body.reason, body.flagged_by),
    )
    con.commit()
    flag = con.execute("SELECT * FROM flags WHERE id = ?", (cur.lastrowid,)).fetchone()
    return FlagResponse(**dict(flag))


@app.get(
    '/categories',
    summary='List all distinct category values with product counts',
)
def get_categories(
    level: int | None = Query(default=None, ge=1, le=5, description='Return a specific level only (1–5). Defaults to all levels.'),
):
    levels = [level] if level else range(1, 6)
    result = {}
    for lvl in levels:
        field = f'category_{lvl}'
        rows  = con.execute(
            f"SELECT {field}, COUNT(*) as count FROM products WHERE {field} IS NOT NULL GROUP BY {field} ORDER BY {field}"
        ).fetchall()
        result[field] = {r[field]: r['count'] for r in rows}
    return result


@app.get(
    '/stats',
    summary='Summary statistics for the dataset',
)
def get_stats():
    total = con.execute("SELECT COUNT(*) FROM products").fetchone()[0]

    nova_rows = con.execute(
        "SELECT nova_group, COUNT(*) as count FROM products GROUP BY nova_group ORDER BY nova_group"
    ).fetchall()
    nova_breakdown = {(r['nova_group'] or 'None'): r['count'] for r in nova_rows}

    price_rows = con.execute(
        "SELECT nova_group, ROUND(AVG(pricing), 2) as avg FROM products WHERE pricing IS NOT NULL GROUP BY nova_group"
    ).fetchall()
    avg_price_by_nova = {(r['nova_group'] or 'None'): r['avg'] for r in price_rows}

    upf_count     = nova_breakdown.get('4', 0)
    non_upf_count = sum(nova_breakdown.get(k, 0) for k in ['1', '2', '3', 'Not UPF'])
    unconfirmed   = nova_breakdown.get('Not confirmed UPF', 0)
    missing_ingr  = con.execute("SELECT COUNT(*) FROM products WHERE ingredients IS NULL").fetchone()[0]

    return {
        'total_products':      total,
        'upf_count':           upf_count,
        'non_upf_count':       non_upf_count,
        'unconfirmed_count':   unconfirmed,
        'upf_proportion':      round(upf_count / total, 4) if total else None,
        'nova_breakdown':      nova_breakdown,
        'avg_price_by_nova':   avg_price_by_nova,
        'missing_ingredients': missing_ingr,
    }

#######
# CLI #
#######

@click.group()
def cli():
    """Pipeline for enriching and serving Waitrose product data."""
    pass

@cli.command()
@click.option('--host', default=None, help='Bind host. Defaults to 0.0.0.0 on Nuvolos, 127.0.0.1 locally.')
@click.option('--port', default=None, type=int, help='Bind port. Defaults to 8080 on Nuvolos, 8000 locally.')
@click.option('--reload', is_flag=True, default=False, help='Enable auto-reload (local dev only).')
def serve(host: str | None, port: int | None, reload: bool):
    """Start the FastAPI server. Detects Nuvolos automatically."""
    on_nuvolos = _is_running_on_nuvolos()
    host = host or ('0.0.0.0' if on_nuvolos else '127.0.0.1')
    port = port or (8080 if on_nuvolos else 8000)
    click.echo(f'Starting server at http://{host}:{port} ({"Nuvolos" if on_nuvolos else "local"})')
    uvicorn.run('main:app', host=host, port=port, reload=reload)

if __name__ == '__main__':
    cli()