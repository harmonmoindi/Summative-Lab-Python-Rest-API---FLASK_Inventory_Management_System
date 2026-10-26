"""Tests for the OpenFoodFacts client. No real network calls: requests.get is mocked."""
from unittest.mock import Mock, patch

import pytest
import requests

import off_client
from off_client import (
    OpenFoodFactsError,
    fetch_by_barcode,
    is_valid_barcode,
    search_by_name,
)


def fake_response(status=200, body=None, bad_json=False):
    """Build a stand-in for a requests.Response."""
    response = Mock()
    response.status_code = status
    if bad_json:
        response.json.side_effect = ValueError("not json")
    else:
        response.json.return_value = body
    return response


# --- is_valid_barcode ---------------------------------------------------------
@pytest.mark.parametrize("barcode", ["3017620422003", "12345678", "12345678901234"])
def test_valid_barcodes(barcode):
    assert is_valid_barcode(barcode)


@pytest.mark.parametrize("barcode", ["abc", "1234567", "123456789012345", "", None, 12345678])
def test_invalid_barcodes(barcode):
    assert not is_valid_barcode(barcode)


# --- fetch_by_barcode ---------------------------------------------------------
def test_fetch_by_barcode_returns_normalized_product():
    body = {
        "status": "success",
        "product": {
            "code": "3017620422003",
            "product_name": "Nutella",
            "brands": "Ferrero",
            "ingredients_text": "Sugar, palm oil",
            "extra_field": "ignored",
        },
    }
    with patch("off_client.requests.get", return_value=fake_response(200, body)):
        product = fetch_by_barcode("3017620422003")
    assert product == {
        "barcode": "3017620422003",
        "product_name": "Nutella",
        "brands": "Ferrero",
        "ingredients_text": "Sugar, palm oil",
    }


def test_fetch_by_barcode_handles_null_values():
    body = {"status": "success", "product": {"product_name": None, "brands": None}}
    with patch("off_client.requests.get", return_value=fake_response(200, body)):
        product = fetch_by_barcode("3017620422003")
    assert product["product_name"] == ""
    assert product["brands"] == ""
    assert product["barcode"] == "3017620422003"  # falls back to the barcode we asked for


def test_fetch_by_barcode_404_returns_none():
    with patch("off_client.requests.get", return_value=fake_response(404, {})):
        assert fetch_by_barcode("1234567890123") is None


def test_fetch_by_barcode_failure_status_returns_none():
    body = {"status": "failure", "product": None}
    with patch("off_client.requests.get", return_value=fake_response(200, body)):
        assert fetch_by_barcode("1234567890123") is None


@pytest.mark.parametrize("status", [429, 500, 503])
def test_fetch_by_barcode_server_errors_raise(status):
    with patch("off_client.requests.get", return_value=fake_response(status, {})):
        with pytest.raises(OpenFoodFactsError, match=str(status)):
            fetch_by_barcode("3017620422003")


def test_fetch_by_barcode_network_error_raises():
    with patch(
        "off_client.requests.get", side_effect=requests.exceptions.ConnectionError("offline")
    ):
        with pytest.raises(OpenFoodFactsError, match="Could not reach"):
            fetch_by_barcode("3017620422003")


def test_fetch_by_barcode_timeout_raises():
    with patch("off_client.requests.get", side_effect=requests.exceptions.Timeout()):
        with pytest.raises(OpenFoodFactsError):
            fetch_by_barcode("3017620422003")


def test_fetch_by_barcode_invalid_json_raises():
    with patch("off_client.requests.get", return_value=fake_response(200, bad_json=True)):
        with pytest.raises(OpenFoodFactsError, match="invalid JSON"):
            fetch_by_barcode("3017620422003")


def test_requests_send_user_agent_and_timeout():
    with patch("off_client.requests.get", return_value=fake_response(404, {})) as mock_get:
        fetch_by_barcode("3017620422003")
    kwargs = mock_get.call_args.kwargs
    assert kwargs["headers"]["User-Agent"] == off_client.USER_AGENT
    assert kwargs["timeout"] == off_client.TIMEOUT
    assert "3017620422003" in mock_get.call_args.args[0]


# --- search_by_name -----------------------------------------------------------
def test_search_by_name_uses_search_a_licious_and_flattens_lists():
    body = {
        "hits": [
            {"code": "0098008952506", "product_name": "Nutella", "brands": ["Nutella", "Ferrero"]},
        ]
    }
    with patch("off_client.requests.get", return_value=fake_response(200, body)) as mock_get:
        results = search_by_name("nutella", limit=3)
    assert results == [
        {
            "barcode": "0098008952506",
            "product_name": "Nutella",
            "brands": "Nutella, Ferrero",  # list turned into one string
            "ingredients_text": "",
        }
    ]
    assert mock_get.call_count == 1
    assert mock_get.call_args.args[0] == off_client.SEARCH_ALICIOUS_URL
    assert mock_get.call_args.kwargs["params"]["page_size"] == 3


def test_search_by_name_empty_hits_returns_empty_list():
    with patch("off_client.requests.get", return_value=fake_response(200, {"hits": []})):
        assert search_by_name("zzzz") == []


def test_search_falls_back_to_legacy_when_new_service_fails():
    legacy_body = {"products": [{"code": "111", "product_name": "Legacy Nutella", "brands": "Ferrero"}]}
    responses = [fake_response(503, {}), fake_response(200, legacy_body)]
    with patch("off_client.requests.get", side_effect=responses) as mock_get:
        results = search_by_name("nutella")
    assert results[0]["product_name"] == "Legacy Nutella"
    assert mock_get.call_count == 2
    assert "cgi/search.pl" in mock_get.call_args_list[1].args[0]


def test_search_falls_back_when_new_service_unreachable():
    legacy_body = {"products": []}
    side_effects = [requests.exceptions.ConnectionError("down"), fake_response(200, legacy_body)]
    with patch("off_client.requests.get", side_effect=side_effects):
        assert search_by_name("nutella") == []


def test_search_raises_when_both_services_fail():
    with patch("off_client.requests.get", return_value=fake_response(503, {})):
        with pytest.raises(OpenFoodFactsError, match="503"):
            search_by_name("nutella")