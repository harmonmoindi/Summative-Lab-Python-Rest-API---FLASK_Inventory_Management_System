"""
Command-line interface for the Inventory Management API.
Start the Flask server first (python app.py), then run:  python cli.py
"""
import math
import os

import requests

# Where the Flask API is running. Override with the INVENTORY_API_URL environment variable.
API_URL = os.environ.get("INVENTORY_API_URL", "http://127.0.0.1:5000")
# Lookups call OpenFoodFacts behind the scenes, so allow more time than a local call needs.
TIMEOUT = 15


class APIError(Exception):
    """Raised when a request to the inventory API fails (network problem or HTTP error)."""


# Talking to the API
def api_request(method, path, **kwargs):
    """Send a request to the inventory API and return the parsed JSON body.

    Raises APIError with a friendly message for network failures, unreadable
    responses, and any error status (4xx/5xx) returned by the API.
    """
    url = f"{API_URL}{path}"
    try:
        response = requests.request(method, url, timeout=TIMEOUT, **kwargs)
    except requests.exceptions.ConnectionError as exc:
        raise APIError(f"Cannot reach the API at {API_URL}. Is the server running?") from exc
    except requests.exceptions.Timeout as exc:
        raise APIError("The API took too long to respond. Please try again.") from exc
    except requests.exceptions.RequestException as exc:
        raise APIError(f"Request failed: {exc}") from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise APIError(
            f"The API returned an unexpected response (HTTP {response.status_code})."
        ) from exc

    if response.status_code >= 400:
        message = body.get("error", "Unknown error") if isinstance(body, dict) else "Unknown error"
        raise APIError(f"{message} (HTTP {response.status_code})")
    return body


# Input helpers
def ask_number(prompt, cast=float, allow_blank=False):
    """Keep asking until the user enters a valid non-negative number.

    cast is float (prices) or int (ids, stock). If allow_blank is True, an empty
    answer returns None, which the update command uses to mean "keep current value".
    """
    kind = "whole number" if cast is int else "number"
    while True:
        raw = input(prompt).strip()
        if raw == "":
            if allow_blank:
                return None
            print("A value is required.")
            continue
        try:
            value = cast(raw)
        except ValueError:
            print(f"'{raw}' is not a valid {kind}.")
            continue
        if not math.isfinite(value):
            print(f"'{raw}' is not a valid {kind}.")
            continue
        if value < 0:
            print("The value cannot be negative.")
            continue
        return value


# Display helpers
def format_item(item):
    """One-line summary of an inventory item."""
    return (
        f"[{item.get('id')}] {item.get('product_name') or '(no name)'} "
        f"| brand: {item.get('brands') or '-'} "
        f"| barcode: {item.get('barcode') or '-'} "
        f"| price: {float(item.get('price', 0)):.2f} "
        f"| stock: {item.get('stock', 0)}"
    )


def print_item_details(item):
    """Multi-line view of a single item, including ingredients."""
    print(f"ID:          {item.get('id')}")
    print(f"Name:        {item.get('product_name') or '(no name)'}")
    print(f"Brand:       {item.get('brands') or '-'}")
    print(f"Barcode:     {item.get('barcode') or '-'}")
    print(f"Price:       {float(item.get('price', 0)):.2f}")
    print(f"Stock:       {item.get('stock', 0)}")
    print(f"Ingredients: {item.get('ingredients_text') or '-'}")


# ---------------------------------------------------------------------------
# Commands (one per menu option)
# ---------------------------------------------------------------------------
def view_all():
    items = api_request("GET", "/inventory")
    if not items:
        print("The inventory is empty.")
        return
    for item in items:
        print(format_item(item))
    print(f"\n{len(items)} item(s) in inventory.")


def view_one():
    item_id = ask_number("Item ID: ", cast=int)
    item = api_request("GET", f"/inventory/{item_id}")
    print_item_details(item)


def add_item():
    barcode = input("Barcode (leave blank to enter the details manually): ").strip()
    if barcode:
        # The API fills in name, brand, and ingredients from OpenFoodFacts.
        payload = {"barcode": barcode}
    else:
        name = ""
        while not name:
            name = input("Product name: ").strip()
            if not name:
                print("Product name is required.")
        payload = {
            "product_name": name,
            "brands": input("Brand (optional): ").strip(),
            "ingredients_text": input("Ingredients (optional): ").strip(),
        }
    payload["price"] = ask_number("Price: ")
    payload["stock"] = ask_number("Stock quantity: ", cast=int)

    item = api_request("POST", "/inventory", json=payload)
    print("Item added:")
    print(format_item(item))


def update_item():
    item_id = ask_number("Item ID to update: ", cast=int)
    price = ask_number("New price (leave blank to keep current): ", allow_blank=True)
    stock = ask_number("New stock (leave blank to keep current): ", cast=int, allow_blank=True)

    changes = {}
    if price is not None:
        changes["price"] = price
    if stock is not None:
        changes["stock"] = stock
    if not changes:
        print("Nothing to update.")
        return

    item = api_request("PATCH", f"/inventory/{item_id}", json=changes)
    print("Item updated:")
    print(format_item(item))


def delete_item():
    item_id = ask_number("Item ID to delete: ", cast=int)
    confirm = input(f"Delete item {item_id}? This cannot be undone (y/N): ").strip().lower()
    if confirm != "y":
        print("Cancelled. Nothing was deleted.")
        return
    result = api_request("DELETE", f"/inventory/{item_id}")
    print(result.get("message", "Item deleted."))


def find_on_api():
    choice = input("Search OpenFoodFacts by (1) barcode or (2) name: ").strip()
    if choice == "1":
        params = {"barcode": input("Barcode: ").strip()}
    elif choice == "2":
        params = {"name": input("Product name: ").strip()}
    else:
        print("Please enter 1 or 2.")
        return
    if not any(params.values()):
        print("The search term cannot be empty.")
        return

    results = api_request("GET", "/lookup", params=params).get("results", [])
    for number, product in enumerate(results, start=1):
        print(
            f"{number}. {product.get('product_name') or '(no name)'} "
            f"| brand: {product.get('brands') or '-'} "
            f"| barcode: {product.get('barcode') or '-'}"
        )

    pick = input("Enter a number to add it to your inventory (leave blank to skip): ").strip()
    if not pick:
        return
    if not pick.isdigit() or not 1 <= int(pick) <= len(results):
        print("Invalid selection.")
        return

    payload = dict(results[int(pick) - 1])
    payload["price"] = ask_number("Price: ")
    payload["stock"] = ask_number("Stock quantity: ", cast=int)
    item = api_request("POST", "/inventory", json=payload)
    print("Item added:")
    print(format_item(item))


# Menu
MENU = [
    ("View all items", view_all),
    ("View one item", view_one),
    ("Add an item", add_item),
    ("Update price or stock", update_item),
    ("Delete an item", delete_item),
    ("Find a product on OpenFoodFacts", find_on_api),
]


def run_command(command):
    """Run one menu command, turning expected failures into friendly messages."""
    try:
        command()
    except APIError as exc:
        print(f"Error: {exc}")
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")


def print_menu():
    print("\n=== Inventory Management ===")
    for number, (label, _command) in enumerate(MENU, start=1):
        print(f"{number}. {label}")
    print("0. Exit")


def main():
    while True:
        print_menu()
        try:
            choice = input("Choose an option: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if choice == "0":
            print("Goodbye!")
            break
        if choice.isdigit() and 1 <= int(choice) <= len(MENU):
            run_command(MENU[int(choice) - 1][1])
        else:
            print(f"Invalid option. Enter a number from 0 to {len(MENU)}.")


if __name__ == "__main__":
    main()