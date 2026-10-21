from flask import Flask, jsonify, request

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
    """Add a new item."""
    fields = request.get_json(silent=True)  # None if body isn't valid JSON
    if fields is None:
        return jsonify({"error": "Request body must be valid JSON"}), 400

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


# Return JSON error if not.
@app.errorhandler(404)
def not_found(_error):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(405)
def method_not_allowed(_error):
    return jsonify({"error": "Method not allowed"}), 405


if __name__ == "__main__":
    app.run(debug=True)