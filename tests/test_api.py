"""Tests for the Flask API endpoints. External OpenFoodFacts calls are mocked."""
from unittest.mock import patch

import pytest

import data
from app import app as flask_app
from off_client import OpenFoodFactsError


@pytest.fixture(autouse=True)
def reset_data():
    """Every test starts (and ends) with the original three seed items."""
    data.reset_inventory()
    yield
    data.reset_inventory()


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


NUTELLA = {
    "barcode": "3017620422003",
    "product_name": "Nutella",
    "brands": "Ferrero",
    "ingredients_text": "Sugar, palm oil, hazelnuts",
}


# --- Home -------------------------------------------------------------------
def test_home_returns_running_message(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.get_json() == {"message": "Inventory API is running"}


# --- GET --------------------------------------------------------------------
def test_get_all_items(client):
    response = client.get("/inventory")
    assert response.status_code == 200
    items = response.get_json()
    assert len(items) == 3
    assert items[0]["product_name"] == "Nutella"


def test_get_single_item(client):
    response = client.get("/inventory/2")
    assert response.status_code == 200
    assert response.get_json()["product_name"] == "Coca-Cola"


def test_get_missing_item_returns_404(client):
    response = client.get("/inventory/99")
    assert response.status_code == 404
    assert "not found" in response.get_json()["error"]


# --- POST -------------------------------------------------------------------
def test_post_creates_item(client):
    payload = {"product_name": "Milk", "price": 90, "stock": 10}
    response = client.post("/inventory", json=payload)
    assert response.status_code == 201
    created = response.get_json()
    assert created["id"] == 4
    assert created["product_name"] == "Milk"
    # It is really stored, not just echoed back
    assert client.get("/inventory/4").status_code == 200


def test_post_applies_defaults_for_price_and_stock(client):
    created = client.post("/inventory", json={"product_name": "Bread"}).get_json()
    assert created["price"] == 0.0
    assert created["stock"] == 0


def test_post_ignores_client_supplied_id_and_unknown_fields(client):
    created = client.post(
        "/inventory", json={"product_name": "Tea", "id": 500, "hacker": "x"}
    ).get_json()
    assert created["id"] == 4
    assert "hacker" not in created


def test_post_without_name_returns_400(client):
    response = client.post("/inventory", json={"price": 90})
    assert response.status_code == 400
    assert "product_name is required" in response.get_json()["error"]


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"product_name": "X", "price": "free"}, "price"),
        ({"product_name": "X", "price": -5}, "price"),
        ({"product_name": "X", "price": True}, "price"),
        ({"product_name": "X", "stock": 1.5}, "stock"),
        ({"product_name": "X", "stock": -1}, "stock"),
        ({"product_name": "X", "barcode": 12345678}, "barcode"),
    ],
)
def test_post_rejects_invalid_values(client, payload, message):
    response = client.post("/inventory", json=payload)
    assert response.status_code == 400
    assert message in response.get_json()["error"]


def test_post_invalid_json_returns_400(client):
    response = client.post("/inventory", data="not json", content_type="application/json")
    assert response.status_code == 400


def test_post_json_list_returns_400(client):
    response = client.post("/inventory", json=[1, 2, 3])
    assert response.status_code == 400


# --- POST with barcode enrichment (OpenFoodFacts mocked) ---------------------
def test_post_with_barcode_fills_details_from_api(client):
    with patch("app.fetch_by_barcode", return_value=dict(NUTELLA)) as mock_fetch:
        response = client.post(
            "/inventory", json={"barcode": "3017620422003", "price": 650, "stock": 10}
        )
    assert response.status_code == 201
    created = response.get_json()
    assert created["product_name"] == "Nutella"
    assert created["brands"] == "Ferrero"
    assert created["price"] == 650
    mock_fetch.assert_called_once_with("3017620422003")


def test_post_user_values_override_api_values(client):
    with patch("app.fetch_by_barcode", return_value=dict(NUTELLA)):
        created = client.post(
            "/inventory",
            json={"barcode": "3017620422003", "brands": "My Brand"},
        ).get_json()
    assert created["brands"] == "My Brand"
    assert created["product_name"] == "Nutella"


def test_post_with_name_does_not_call_api(client):
    with patch("app.fetch_by_barcode") as mock_fetch:
        response = client.post(
            "/inventory", json={"barcode": "1234567890123", "product_name": "Manual"}
        )
    assert response.status_code == 201
    mock_fetch.assert_not_called()


def test_post_barcode_not_found_returns_404(client):
    with patch("app.fetch_by_barcode", return_value=None):
        response = client.post("/inventory", json={"barcode": "1234567890123"})
    assert response.status_code == 404
    assert "not found" in response.get_json()["error"].lower()


def test_post_barcode_api_failure_returns_502(client):
    with patch("app.fetch_by_barcode", side_effect=OpenFoodFactsError("down")):
        response = client.post("/inventory", json={"barcode": "3017620422003"})
    assert response.status_code == 502
    assert response.get_json()["error"] == "down"


def test_post_invalid_barcode_returns_400(client):
    with patch("app.fetch_by_barcode") as mock_fetch:
        response = client.post("/inventory", json={"barcode": "abc"})
    assert response.status_code == 400
    mock_fetch.assert_not_called()


# --- PATCH ------------------------------------------------------------------
def test_patch_updates_only_sent_fields(client):
    response = client.patch("/inventory/1", json={"stock": 20})
    assert response.status_code == 200
    updated = response.get_json()
    assert updated["stock"] == 20
    assert updated["price"] == 650.0  # untouched
    assert updated["product_name"] == "Nutella"  # untouched


def test_patch_missing_item_returns_404(client):
    response = client.patch("/inventory/99", json={"stock": 5})
    assert response.status_code == 404


def test_patch_cannot_change_id(client):
    response = client.patch("/inventory/1", json={"id": 50})
    assert response.status_code == 400
    assert client.get("/inventory/1").status_code == 200


def test_patch_invalid_value_returns_400(client):
    response = client.patch("/inventory/1", json={"stock": -1})
    assert response.status_code == 400
    assert client.get("/inventory/1").get_json()["stock"] == 24  # unchanged


def test_patch_invalid_json_returns_400(client):
    response = client.patch("/inventory/1", data="oops", content_type="application/json")
    assert response.status_code == 400


# --- DELETE -----------------------------------------------------------------
def test_delete_removes_item(client):
    response = client.delete("/inventory/2")
    assert response.status_code == 200
    assert client.get("/inventory/2").status_code == 404
    assert len(client.get("/inventory").get_json()) == 2


def test_delete_missing_item_returns_404(client):
    assert client.delete("/inventory/99").status_code == 404


def test_ids_are_not_reused_after_delete(client):
    client.delete("/inventory/3")
    created = client.post("/inventory", json={"product_name": "New"}).get_json()
    assert created["id"] == 4


# --- /lookup (OpenFoodFacts mocked) ------------------------------------------
def test_lookup_by_barcode(client):
    with patch("app.fetch_by_barcode", return_value=dict(NUTELLA)):
        response = client.get("/lookup?barcode=3017620422003")
    assert response.status_code == 200
    assert response.get_json()["results"][0]["product_name"] == "Nutella"


def test_lookup_by_name(client):
    with patch("app.search_by_name", return_value=[dict(NUTELLA)]) as mock_search:
        response = client.get("/lookup?name=nutella")
    assert response.status_code == 200
    assert len(response.get_json()["results"]) == 1
    mock_search.assert_called_once_with("nutella")


def test_lookup_without_parameters_returns_400(client):
    assert client.get("/lookup").status_code == 400


def test_lookup_invalid_barcode_returns_400(client):
    assert client.get("/lookup?barcode=abc").status_code == 400


def test_lookup_barcode_not_found_returns_404(client):
    with patch("app.fetch_by_barcode", return_value=None):
        assert client.get("/lookup?barcode=1234567890123").status_code == 404


def test_lookup_name_with_no_results_returns_404(client):
    with patch("app.search_by_name", return_value=[]):
        assert client.get("/lookup?name=zzzz").status_code == 404


def test_lookup_api_failure_returns_502(client):
    with patch("app.search_by_name", side_effect=OpenFoodFactsError("503")):
        response = client.get("/lookup?name=nutella")
    assert response.status_code == 502


# --- Error handlers ---------------------------------------------------------
def test_unknown_url_returns_json_404(client):
    response = client.get("/nope")
    assert response.status_code == 404
    assert response.get_json() == {"error": "Not found"}


def test_wrong_method_returns_json_405(client):
    response = client.put("/inventory")
    assert response.status_code == 405
    assert response.get_json() == {"error": "Method not allowed"}