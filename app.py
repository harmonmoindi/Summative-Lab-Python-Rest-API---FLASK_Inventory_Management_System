from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/")
def home():
    # Simple health check so we know the server is running
    return jsonify({"message": "Inventory API is running"})


if __name__ == "__main__":
    # debug=True auto-reloads on changes and shows errors in the browser
    app.run(debug=True)
    