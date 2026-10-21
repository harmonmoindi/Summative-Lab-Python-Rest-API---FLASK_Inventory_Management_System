import copy
#clients can update this field.
ALLOWED_FIELDS = {
    "barcode", "product_name", "brands", "ingredients_text", "price", "stock",
}

# Starting data or mock data.
_SEED = [
    {
        "id": 1,
        "barcode": "3017620422003",
        "product_name": "Nutella",
        "brands": "Ferrero",
        "ingredients_text": "Sugar, palm oil, hazelnuts, skimmed milk powder, cocoa, lecithin, vanillin",
        "price": 650.0,
        "stock": 24,
    },
    {
        "id": 2,
        "barcode": "5449000000996",
        "product_name": "Coca-Cola",
        "brands": "Coca-Cola",
        "ingredients_text": "Carbonated water, sugar, colour (caramel E150d), phosphoric acid, natural flavourings, caffeine",
        "price": 120.0,
        "stock": 80,
    },
    {
        "id": 3,
        "barcode": "0000000000001",  
        "product_name": "Organic Almond Milk",
        "brands": "Silk",
        "ingredients_text": "Filtered water, almonds, cane sugar, sea salt",
        "price": 480.0,
        "stock": 15,
    },
]

# The live "database". We change it in place for consistency with other modules that have imported it.
inventory = copy.deepcopy(_SEED)
_next_id = max(item["id"] for item in inventory) + 1


def reset_inventory():
    """Restore the starting data (used by tests)."""
    global _next_id
    inventory[:] = copy.deepcopy(_SEED)
    _next_id = max(item["id"] for item in inventory) + 1


def get_all():
    return inventory


def get_by_id(item_id):
    for item in inventory:
        if item["id"] == item_id:
            return item
    return None


def add_item(fields):
    """Create an item from the allowed fields and append it."""
    global _next_id
    item = {key: value for key, value in fields.items() if key in ALLOWED_FIELDS}
    item.setdefault("price", 0.0)   # sensible defaults for our own fields
    item.setdefault("stock", 0)
    item["id"] = _next_id
    _next_id += 1                   # ids are never reused, even after a delete
    inventory.append(item)
    return item


def update_item(item_id, fields):
    item = get_by_id(item_id)
    if item is None:
        return None
    for key, value in fields.items():
        if key in ALLOWED_FIELDS:
            item[key] = value
    return item


def delete_item(item_id):
    item = get_by_id(item_id)
    if item is None:
        return False
    inventory.remove(item)
    return True