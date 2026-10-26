# Inventory Management System

A small retail admin tool built with **Flask**. It has a REST API for managing inventory (add, view, edit, delete), enriches products with real data from the [OpenFoodFacts API](https://openfoodfacts.github.io/openfoodfacts-server/api/), and comes with a command-line interface and a pytest test suite.

## Features

* **REST API** with full CRUD for inventory items (`GET`, `POST`, `PATCH`, `DELETE`)
* **OpenFoodFacts integration:** look up products by barcode or name, and auto-fill product details when adding an item by barcode
* **CLI** to add, view, update, and delete items and to search OpenFoodFacts
* **Input validation and error handling** for bad data, missing items, and external API failures
* **Unit tests** (pytest + `unittest.mock`) covering the API, the CLI, and the external API client. No test touches the real network.

> **Storage note:** inventory data lives in a Python list (`data.py`), as the lab specifies. It is reset to three sample items every time the server restarts.

## Project Structure

```
.
├── app.py              # Flask app: routes, validation, error handlers
├── data.py             # In-memory inventory (mock database) and helper functions
├── off_client.py       # OpenFoodFacts client (barcode lookup, name search)
├── cli.py              # Command-line interface
├── conftest.py         # Empty; lets pytest import modules from the project root
├── tests/
│   ├── test_api.py         # Flask endpoint tests
│   ├── test_cli.py         # CLI command tests
│   └── test_off_client.py  # OpenFoodFacts client tests (mocked HTTP)
├── Pipfile / Pipfile.lock
└── README.md
```

## Installation and Setup

**Requirements:** Python 3.10 and [pipenv](https://pipenv.pypa.io/).

git clone repo

pipenv install            # installs Flask and requests
pipenv install --dev      # also installs pytest
pipenv shell              # activates the virtual environment
```

**Before you run it:** open `off_client.py` and set `USER_AGENT` to include your own contact email, for example `InventoryManager/1.0 (you@example.com)`. OpenFoodFacts asks every app to identify itself with a custom User-Agent.

## Running the Project

Use two terminals, both inside the project folder and the pipenv shell.

**Terminal 1: start the API**

```bash
python app.py
```

The API runs at `http://127.0.0.1:5000` in Flask debug mode (auto-reload and detailed errors).

**Terminal 2: start the CLI**

```bash
python cli.py
```

To point the CLI at a different server address, set an environment variable:

```bash
INVENTORY_API_URL=http://127.0.0.1:8000 python cli.py
```

## API Endpoints

All requests and responses use JSON. Item fields: `id`, `barcode`, `product_name`, `brands`, `ingredients_text`, `price`, `stock`.

| Method | Endpoint | Description | Success | Errors |
| --- | --- | --- | --- | --- |
| GET | `/` | Health check | `200` | none |
| GET | `/inventory` | List all items | `200` | none |
| GET | `/inventory/<id>` | Get one item | `200` | `404` not found |
| POST | `/inventory` | Add an item | `201` | `400` invalid input, `404` barcode not on OpenFoodFacts, `502` OpenFoodFacts unreachable |
| PATCH | `/inventory/<id>` | Update fields of an item | `200` | `400` invalid input, `404` not found |
| DELETE | `/inventory/<id>` | Remove an item | `200` | `404` not found |
| GET | `/lookup?barcode=...` or `/lookup?name=...` | Search OpenFoodFacts (does not change inventory) | `200` | `400` bad or missing query, `404` no results, `502` OpenFoodFacts unreachable |

Errors always come back as JSON in the form `{"error": "message"}`.

### Validation rules

* `product_name` is required when creating an item (unless a `barcode` is sent, see below)
* `price` must be a non-negative number
* `stock` must be a non-negative whole number
* `barcode` must be a string of 8 to 14 digits
* `id` is assigned by the server and cannot be set or changed. IDs are never reused after a delete.
* Unknown fields are ignored

### Examples

**Add an item manually**

```http
POST /inventory
{"product_name": "Milk", "brands": "Brookside", "price": 90, "stock": 10}
```

```json
{"id": 4, "product_name": "Milk", "brands": "Brookside", "price": 90, "stock": 10}
```

**Add an item by barcode.** The server fetches the name, brand, and ingredients from OpenFoodFacts. Values you send yourself take priority over the API's.

```http
POST /inventory
{"barcode": "3017620422003", "price": 650, "stock": 10}
```

```json
{
  "id": 4,
  "barcode": "3017620422003",
  "product_name": "Nutella",
  "brands": "Ferrero",
  "ingredients_text": "Sugar, palm oil, ...",
  "price": 650,
  "stock": 10
}
```

**Update stock** (only the fields you send are changed)

```http
PATCH /inventory/1
{"stock": 20}
```

**Delete an item**

```http
DELETE /inventory/2
```

```json
{"message": "Item 2 deleted"}
```

**Search OpenFoodFacts**

```http
GET /lookup?name=nutella
```

```json
{"results": [{"barcode": "0098008952506", "product_name": "Nutella", "brands": "Nutella", "ingredients_text": ""}]}
```

## Using the CLI

`python cli.py` shows a menu. Type the number of an option and follow the prompts.

```
=== Inventory Management ===
1. View all items
2. View one item
3. Add an item
4. Update price or stock
5. Delete an item
6. Find a product on OpenFoodFacts
0. Exit
```

**Example session: add a product by barcode**

```
Choose an option: 3
Barcode (leave blank to enter the details manually): 3017620422003
Price: 650
Stock quantity: 10
Item added:
[4] Nutella | brand: Ferrero | barcode: 3017620422003 | price: 650.00 | stock: 10
```

**Example session: update stock only** (leave a field blank to keep its current value)

```
Choose an option: 4
Item ID to update: 4
New price (leave blank to keep current):
New stock (leave blank to keep current): 25
Item updated:
[4] Nutella | brand: Ferrero | barcode: 3017620422003 | price: 650.00 | stock: 25
```

**Example session: search OpenFoodFacts and add a result**

```
Choose an option: 6
Search OpenFoodFacts by (1) barcode or (2) name: 2
Product name: nutella
1. Nutella & go! hazelnut spread + breadsticks | brand: Nutella | barcode: 0009800800049
2. Nutella | brand: Nutella | barcode: 0098008952506
Enter a number to add it to your inventory (leave blank to skip): 2
Price: 700
Stock quantity: 5
```

**Error handling.** The CLI keeps running when something goes wrong:

* Invalid numbers are re-prompted (`'abc' is not a valid number.`)
* Deleting asks for confirmation first
* If the API server is not running: `Error: Cannot reach the API at http://127.0.0.1:5000. Is the server running?`
* If OpenFoodFacts is down or rate-limiting: the API's message is shown, for example `Error: OpenFoodFacts returned HTTP 503 (HTTP 502)`

## OpenFoodFacts Notes

* **Barcode lookup** uses the v3 product endpoint, requesting only the fields we store.
* **Name search** tries the newer Search-a-licious service first and falls back to the legacy `/cgi/search.pl` endpoint if that fails. The legacy endpoint often returns `503` to anonymous users.
* **Rate limits:** OpenFoodFacts allows about 15 product lookups per minute and 10 searches per minute per IP. Space out manual testing, and never use name search for search-as-you-type.
* **Data quality:** OpenFoodFacts data is contributed by volunteers, so some products have blank names or ingredients. If a barcode lookup returns no name, add the item manually and supply `product_name`.

## Running the Tests

```bash
pytest          # run everything
pytest -v       # verbose, one line per test
pytest tests/test_api.py   # one file
```

* `tests/test_api.py`: every endpoint, including validation errors, missing items, and the JSON 404/405 handlers. OpenFoodFacts calls are replaced with `unittest.mock.patch`.
* `tests/test_off_client.py`: the client's parsing and error paths (404, 503, timeouts, invalid JSON, list-valued fields, search fallback). `requests.get` is mocked, so no network is used.
* `tests/test_cli.py`: each CLI command with scripted keyboard input and a mocked HTTP layer, plus input validation and error messages.

You can also test the API manually with Postman or curl while the server is running:

```bash
curl http://127.0.0.1:5000/inventory
curl -X POST http://127.0.0.1:5000/inventory \
  -H "Content-Type: application/json" \
  -d '{"product_name": "Milk", "price": 90, "stock": 10}'
```

## Design Decisions

* **Thin routes:** `app.py` handles HTTP only (parsing, status codes). Data changes live in `data.py` and external calls live in `off_client.py`, so each piece can be tested on its own.
* **Normalized API data:** `off_client.py` trims OpenFoodFacts responses to the four fields we store, so the rest of the app never depends on the API's raw shape.
* **Clear error separation:** "not found" returns `None` while a network or server failure raises an error. This is why the API can return `404` and `502` correctly.
* **Defensive validation:** booleans are rejected for numeric fields, clients cannot set `id`, and `PATCH` rejects requests with no updatable fields.

## Limitations and Possible Improvements

* Data is stored in memory and is lost on restart. A database (SQLite or PostgreSQL) would be the next step.
* The API has no authentication. It is meant as a local admin tool.
* Name search returns only the top 5 matches.