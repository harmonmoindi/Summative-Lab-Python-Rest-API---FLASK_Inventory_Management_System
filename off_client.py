import requests

BASE_URL = "https://world.openfoodfacts.org"
USER_AGENT = "InventoryManager/1.0 (harmonmoindi@gmail.com)" 
TIMEOUT = 10  # A slow API can't hang the server
FIELDS = "code,product_name,brands,ingredients_text"  # only fetch what is stored
SEARCH_ALICIOUS_URL = "https://search.openfoodfacts.org/search"


class OpenFoodFactsError(Exception):
    """Raised when the API can't be reached or returns something unusable."""


def is_valid_barcode(barcode):
    return isinstance(barcode, str) and barcode.isdigit() and 8 <= len(barcode) <= 14


def _as_text(value):
    """Some APIs return a list for fields like brands; make everything a string."""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return value or ""


def _normalize(product, barcode=None):
    """Keep only our fields. The API can return None for missing values."""
    return {
        "barcode": product.get("code") or barcode or "",
        "product_name": _as_text(product.get("product_name")),
        "brands": _as_text(product.get("brands")),
        "ingredients_text": _as_text(product.get("ingredients_text")),
    }


def _get(url, params):
    """One place for the HTTP call, so errors are handled consistently."""
    try:
        response = requests.get(
            url,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
    except requests.exceptions.RequestException as exc:
        raise OpenFoodFactsError(f"Could not reach OpenFoodFacts: {exc}") from exc
    return response


def fetch_by_barcode(barcode):
    """Return a normalized product dict, or None if the barcode isn't found."""
    response = _get(f"{BASE_URL}/api/v3/product/{barcode}", {"fields": FIELDS})

    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise OpenFoodFactsError(f"OpenFoodFacts returned HTTP {response.status_code}")

    try:
        body = response.json()
    except ValueError as exc:
        raise OpenFoodFactsError("OpenFoodFacts returned invalid JSON") from exc

    product = body.get("product")
    if not product or body.get("status") == "failure":
        return None
    return _normalize(product, barcode)


def _search_alicious(name, limit):
    """Name search using Search-a-licious (the newer full-text search service)."""
    response = _get(
        SEARCH_ALICIOUS_URL,
        {"q": name, "page_size": limit, "fields": FIELDS},
    )
    if response.status_code != 200:
        raise OpenFoodFactsError(f"Search service returned HTTP {response.status_code}")
    try:
        body = response.json()
    except ValueError as exc:
        raise OpenFoodFactsError("Search service returned invalid JSON") from exc
    return [_normalize(hit) for hit in body.get("hits", [])]


def _search_legacy(name, limit):
    """Name search using the legacy /cgi/search.pl endpoint."""
    response = _get(
        f"{BASE_URL}/cgi/search.pl",
        {
            "search_terms": name,
            "search_simple": 1,
            "action": "process",
            "json": 1,
            "page_size": limit,
            "fields": FIELDS,
        },
    )
    if response.status_code != 200:
        raise OpenFoodFactsError(f"OpenFoodFacts returned HTTP {response.status_code}")
    try:
        body = response.json()
    except ValueError as exc:
        raise OpenFoodFactsError("OpenFoodFacts returned invalid JSON") from exc
    return [_normalize(p) for p in body.get("products", [])]


def search_by_name(name, limit=5):
    """Try Search-a-licious first; fall back to the legacy search if it fails."""
    try:
        return _search_alicious(name, limit)
    except OpenFoodFactsError:
        return _search_legacy(name, limit)