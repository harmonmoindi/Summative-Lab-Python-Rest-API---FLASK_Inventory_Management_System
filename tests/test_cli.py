"""Tests for the CLI. input() and the HTTP layer are mocked, so no server is needed."""
from unittest.mock import Mock, patch

import pytest
import requests

import cli
from cli import APIError

ITEM = {
    "id": 4,
    "barcode": "3017620422003",
    "product_name": "Nutella",
    "brands": "Ferrero",
    "ingredients_text": "Sugar, palm oil",
    "price": 650.0,
    "stock": 10,
}


def fake_response(status=200, body=None, bad_json=False):
    response = Mock()
    response.status_code = status
    if bad_json:
        response.json.side_effect = ValueError("not json")
    else:
        response.json.return_value = body
    return response


def run_with_inputs(command, inputs):
    """Run a CLI command with scripted keyboard input."""
    with patch("builtins.input", side_effect=inputs):
        command()


# --- api_request --------------------------------------------------------------
def test_api_request_returns_json_and_builds_url():
    with patch("cli.requests.request", return_value=fake_response(200, [ITEM])) as mock_req:
        result = cli.api_request("GET", "/inventory")
    assert result == [ITEM]
    assert mock_req.call_args.args == ("GET", f"{cli.API_URL}/inventory")
    assert mock_req.call_args.kwargs["timeout"] == cli.TIMEOUT


def test_api_request_connection_error_gives_friendly_message():
    with patch("cli.requests.request", side_effect=requests.exceptions.ConnectionError()):
        with pytest.raises(APIError, match="Is the server running"):
            cli.api_request("GET", "/inventory")


def test_api_request_timeout_gives_friendly_message():
    with patch("cli.requests.request", side_effect=requests.exceptions.Timeout()):
        with pytest.raises(APIError, match="too long"):
            cli.api_request("GET", "/inventory")


def test_api_request_other_request_error():
    with patch("cli.requests.request", side_effect=requests.exceptions.RequestException("boom")):
        with pytest.raises(APIError, match="boom"):
            cli.api_request("GET", "/inventory")


def test_api_request_error_status_uses_server_message():
    response = fake_response(404, {"error": "Item 9 not found"})
    with patch("cli.requests.request", return_value=response):
        with pytest.raises(APIError, match=r"Item 9 not found \(HTTP 404\)"):
            cli.api_request("GET", "/inventory/9")


def test_api_request_non_json_response():
    with patch("cli.requests.request", return_value=fake_response(500, bad_json=True)):
        with pytest.raises(APIError, match="unexpected response"):
            cli.api_request("GET", "/inventory")


# --- ask_number ---------------------------------------------------------------
def test_ask_number_reprompts_until_valid(capsys):
    with patch("builtins.input", side_effect=["abc", "-5", "", "12.5"]):
        value = cli.ask_number("Price: ")
    assert value == 12.5
    output = capsys.readouterr().out
    assert "not a valid number" in output
    assert "cannot be negative" in output
    assert "required" in output


def test_ask_number_int_rejects_decimals(capsys):
    with patch("builtins.input", side_effect=["1.5", "7"]):
        assert cli.ask_number("Stock: ", cast=int) == 7
    assert "not a valid whole number" in capsys.readouterr().out


def test_ask_number_rejects_nan_and_infinity(capsys):
    with patch("builtins.input", side_effect=["nan", "inf", "3"]):
        assert cli.ask_number("Price: ") == 3.0


def test_ask_number_blank_allowed_returns_none():
    with patch("builtins.input", side_effect=[""]):
        assert cli.ask_number("Price: ", allow_blank=True) is None


# --- view commands ------------------------------------------------------------
def test_view_all_prints_items(capsys):
    with patch("cli.api_request", return_value=[ITEM]):
        cli.view_all()
    output = capsys.readouterr().out
    assert "Nutella" in output
    assert "650.00" in output
    assert "1 item(s)" in output


def test_view_all_empty_inventory(capsys):
    with patch("cli.api_request", return_value=[]):
        cli.view_all()
    assert "empty" in capsys.readouterr().out


def test_view_one_prints_details(capsys):
    with patch("cli.api_request", return_value=ITEM) as mock_api:
        run_with_inputs(cli.view_one, ["4"])
    mock_api.assert_called_once_with("GET", "/inventory/4")
    output = capsys.readouterr().out
    assert "Ferrero" in output
    assert "Sugar, palm oil" in output


# --- add_item -----------------------------------------------------------------
def test_add_item_by_barcode_sends_only_barcode_price_stock(capsys):
    with patch("cli.api_request", return_value=ITEM) as mock_api:
        run_with_inputs(cli.add_item, ["3017620422003", "650", "10"])
    mock_api.assert_called_once_with(
        "POST", "/inventory", json={"barcode": "3017620422003", "price": 650.0, "stock": 10}
    )
    assert "Item added" in capsys.readouterr().out


def test_add_item_manually_sends_all_details():
    # Blank barcode -> manual entry. The empty name is rejected once, then "Tea" is accepted.
    inputs = ["", "", "Tea", "Lipton", "Tea leaves", "100", "5"]
    with patch("cli.api_request", return_value=ITEM) as mock_api:
        run_with_inputs(cli.add_item, inputs)
    mock_api.assert_called_once_with(
        "POST",
        "/inventory",
        json={
            "product_name": "Tea",
            "brands": "Lipton",
            "ingredients_text": "Tea leaves",
            "price": 100.0,
            "stock": 5,
        },
    )


def test_add_item_invalid_numbers_are_reprompted():
    inputs = ["3017620422003", "abc", "650", "1.5", "10"]
    with patch("cli.api_request", return_value=ITEM) as mock_api:
        run_with_inputs(cli.add_item, inputs)
    payload = mock_api.call_args.kwargs["json"]
    assert payload["price"] == 650.0
    assert payload["stock"] == 10


# --- update_item --------------------------------------------------------------
def test_update_item_sends_only_changed_fields():
    with patch("cli.api_request", return_value=ITEM) as mock_api:
        run_with_inputs(cli.update_item, ["4", "", "25"])  # keep price, change stock
    mock_api.assert_called_once_with("PATCH", "/inventory/4", json={"stock": 25})


def test_update_item_both_fields():
    with patch("cli.api_request", return_value=ITEM) as mock_api:
        run_with_inputs(cli.update_item, ["4", "700.5", "3"])
    assert mock_api.call_args.kwargs["json"] == {"price": 700.5, "stock": 3}


def test_update_item_with_nothing_to_change_makes_no_request(capsys):
    with patch("cli.api_request") as mock_api:
        run_with_inputs(cli.update_item, ["4", "", ""])
    mock_api.assert_not_called()
    assert "Nothing to update" in capsys.readouterr().out


# --- delete_item --------------------------------------------------------------
def test_delete_item_confirmed(capsys):
    with patch("cli.api_request", return_value={"message": "Item 4 deleted"}) as mock_api:
        run_with_inputs(cli.delete_item, ["4", "y"])
    mock_api.assert_called_once_with("DELETE", "/inventory/4")
    assert "Item 4 deleted" in capsys.readouterr().out


@pytest.mark.parametrize("answer", ["n", "", "no", "maybe"])
def test_delete_item_not_confirmed_makes_no_request(answer, capsys):
    with patch("cli.api_request") as mock_api:
        run_with_inputs(cli.delete_item, ["4", answer])
    mock_api.assert_not_called()
    assert "Cancelled" in capsys.readouterr().out


# --- find_on_api --------------------------------------------------------------
LOOKUP_BODY = {"results": [{"barcode": "111", "product_name": "Nutella", "brands": "Ferrero", "ingredients_text": ""}]}


def test_find_by_barcode_prints_results_and_skips_adding(capsys):
    with patch("cli.api_request", return_value=LOOKUP_BODY) as mock_api:
        run_with_inputs(cli.find_on_api, ["1", "3017620422003", ""])
    mock_api.assert_called_once_with("GET", "/lookup", params={"barcode": "3017620422003"})
    assert "1. Nutella" in capsys.readouterr().out


def test_find_by_name_uses_name_parameter():
    with patch("cli.api_request", return_value=LOOKUP_BODY) as mock_api:
        run_with_inputs(cli.find_on_api, ["2", "nutella", ""])
    mock_api.assert_called_once_with("GET", "/lookup", params={"name": "nutella"})


def test_find_then_add_result_to_inventory():
    responses = [LOOKUP_BODY, ITEM]
    with patch("cli.api_request", side_effect=responses) as mock_api:
        run_with_inputs(cli.find_on_api, ["2", "nutella", "1", "650", "10"])
    post_call = mock_api.call_args_list[1]
    assert post_call.args == ("POST", "/inventory")
    assert post_call.kwargs["json"]["product_name"] == "Nutella"
    assert post_call.kwargs["json"]["price"] == 650.0
    assert post_call.kwargs["json"]["stock"] == 10


def test_find_invalid_selection_does_not_add(capsys):
    with patch("cli.api_request", return_value=LOOKUP_BODY) as mock_api:
        run_with_inputs(cli.find_on_api, ["2", "nutella", "9"])
    assert mock_api.call_count == 1  # only the lookup, no POST
    assert "Invalid selection" in capsys.readouterr().out


def test_find_invalid_search_type(capsys):
    with patch("cli.api_request") as mock_api:
        run_with_inputs(cli.find_on_api, ["7"])
    mock_api.assert_not_called()
    assert "enter 1 or 2" in capsys.readouterr().out


def test_find_empty_search_term(capsys):
    with patch("cli.api_request") as mock_api:
        run_with_inputs(cli.find_on_api, ["2", "   "])
    mock_api.assert_not_called()
    assert "cannot be empty" in capsys.readouterr().out


# --- run_command and main -----------------------------------------------------
def test_run_command_prints_api_errors_instead_of_crashing(capsys):
    def failing():
        raise APIError("Cannot reach the API")

    cli.run_command(failing)
    assert "Error: Cannot reach the API" in capsys.readouterr().out


def test_run_command_handles_ctrl_c(capsys):
    def interrupted():
        raise KeyboardInterrupt

    cli.run_command(interrupted)
    assert "Cancelled" in capsys.readouterr().out


def test_main_runs_a_command_then_exits(capsys):
    with patch("builtins.input", side_effect=["1", "0"]), patch(
        "cli.api_request", return_value=[ITEM]
    ):
        cli.main()
    output = capsys.readouterr().out
    assert "Nutella" in output
    assert "Goodbye!" in output


def test_main_rejects_invalid_menu_choice(capsys):
    with patch("builtins.input", side_effect=["99", "abc", "0"]):
        cli.main()
    assert capsys.readouterr().out.count("Invalid option") == 2


def test_main_survives_api_failure(capsys):
    with patch("builtins.input", side_effect=["1", "0"]), patch(
        "cli.requests.request", side_effect=requests.exceptions.ConnectionError()
    ):
        cli.main()
    output = capsys.readouterr().out
    assert "Is the server running" in output
    assert "Goodbye!" in output


def test_main_exits_cleanly_on_eof(capsys):
    with patch("builtins.input", side_effect=EOFError):
        cli.main()
    assert "Goodbye!" in capsys.readouterr().out