from flask import Flask, jsonify, request
from off_client import OpenFoodFactsError, fetch_by_barcode, is_valid_barcode, search_by_name

import data

app = Flask(__name__)


def validate_fields(fields, partial=False):
    if not isinstance(fields, dict):
        return "Request body must be a JSON object"

    # A product must have a name
    if not partial and not fields.get("product_name"):
        return "product_name is required"

    # excluding bool.
    if "price" in fields:
        price = fields["price"]
        if isinstance(price, bool) or not isinstance(price, (int, float)) or price < 0:
            return "price must be a non-negative number"

    if "stock" in fields:
        stock = fields["stock"]
        if isinstance(stock, bool) or not isinstance(stock, int) or stock < 0:
            return "stock must be a non-negative whole number"
        
    if "barcode" in fields and not isinstance(fields["barcode"], str):
        return "barcode must be a string"

    return None


@app.route("/")
def home():
    return jsonify({"message": "Inventory API is running"})


@app.route("/inventory", methods=["GET"])
def get_inventory():
    """Fetch all items."""
    return jsonify(data.get_all()), 200


@app.route("/inventory/<int:item_id>", methods=["GET"])
def get_item(item_id):
    """Fetch a single item."""
    item = data.get_by_id(item_id)
    if item is None:
        return jsonify({"error": f"Item {item_id} not found"}), 404
    return jsonify(item), 200


@app.route("/inventory", methods=["POST"])
def create_item():
    """Add a new item. Fetch the details from OpenFoodFacts."""
    fields = request.get_json(silent=True)
    if fields is None:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    barcode = fields.get("barcode") if isinstance(fields, dict) else None
    if isinstance(barcode, str) and barcode and not fields.get("product_name"):
        if not is_valid_barcode(barcode):
            return jsonify({"error": "barcode must be 8-14 digits"}), 400
        try:
            product = fetch_by_barcode(barcode)
        except OpenFoodFactsError as exc:
            return jsonify({"error": str(exc)}), 502  # 502 = upstream API failed
        if product is None:
            return jsonify({
                "error": "Product not found on OpenFoodFacts. Provide product_name to add it manually."
            }), 404
        # Our own values (price, stock...) win over the API's
        fields = {**product, **fields}

    error = validate_fields(fields)
    if error:
        return jsonify({"error": error}), 400

    item = data.add_item(fields)
    return jsonify(item), 201


@app.route("/inventory/<int:item_id>", methods=["PATCH"])
def update_item(item_id):
    """Update only the fields that were sent."""
    fields = request.get_json(silent=True)
    if fields is None:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    error = validate_fields(fields, partial=True)
    if error:
        return jsonify({"error": error}), 400

    # Check existence first so a missing item gives 404, not 400
    if data.get_by_id(item_id) is None:
        return jsonify({"error": f"Item {item_id} not found"}), 404

    if not any(key in data.ALLOWED_FIELDS for key in fields):
        return jsonify({"error": "No updatable fields provided"}), 400

    item = data.update_item(item_id, fields)
    return jsonify(item), 200


@app.route("/inventory/<int:item_id>", methods=["DELETE"])
def delete_item(item_id):
    """Remove an item."""
    if not data.delete_item(item_id):
        return jsonify({"error": f"Item {item_id} not found"}), 404
    return jsonify({"message": f"Item {item_id} deleted"}), 200

@app.route("/lookup", methods=["GET"])
def lookup():
    """Search OpenFoodFacts by barcode or name"""
    barcode = request.args.get("barcode", "").strip()
    name = request.args.get("name", "").strip()

    if not barcode and not name:
        return jsonify({"error": "Provide a barcode or name query parameter"}), 400

    try:
        if barcode:
            if not is_valid_barcode(barcode):
                return jsonify({"error": "barcode must be 8-14 digits"}), 400
            product = fetch_by_barcode(barcode)
            results = [product] if product else []
        else:
            results = search_by_name(name)
    except OpenFoodFactsError as exc:
        return jsonify({"error": str(exc)}), 502

    if not results:
        return jsonify({"error": "No matching products found"}), 404
    return jsonify({"results": results}), 200


# Return JSON error if not.
@app.errorhandler(404)
def not_found(_error):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(405)
def method_not_allowed(_error):
    return jsonify({"error": "Method not allowed"}), 405


if __name__ == "__main__":
    app.run(debug=True)