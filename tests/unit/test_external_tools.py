import importlib
from unittest.mock import MagicMock

import pytest
import requests

from jarvis.tools import scraper, search


def _tool_unavailable_error():
    return importlib.import_module(
        "jarvis.tools.errors"
    ).ToolUnavailableError


@pytest.mark.parametrize(
    ("status_code", "category"),
    [
        (401, "credential"),
        (403, "credential"),
        (500, "provider"),
        (503, "provider"),
    ],
)
def test_web_search_normalizes_supported_http_failures(
    monkeypatch,
    status_code,
    category,
):
    monkeypatch.setattr(search, "TAVILY_API_KEY", "configured")
    response = MagicMock(status_code=status_code)
    monkeypatch.setattr(
        search.requests,
        "post",
        MagicMock(return_value=response),
    )

    with pytest.raises(_tool_unavailable_error()) as raised:
        search.web_search("query")

    assert raised.value.tool_name == "web_search"
    assert raised.value.category == category


@pytest.mark.parametrize(
    ("exception", "category"),
    [
        (requests.Timeout("secret-response"), "timeout"),
        (requests.ConnectionError("secret-response"), "connectivity"),
    ],
)
def test_web_search_normalizes_request_failures(
    monkeypatch,
    exception,
    category,
):
    monkeypatch.setattr(search, "TAVILY_API_KEY", "configured")
    monkeypatch.setattr(
        search.requests,
        "post",
        MagicMock(side_effect=exception),
    )

    with pytest.raises(_tool_unavailable_error()) as raised:
        search.web_search("query")

    assert raised.value.category == category
    assert "secret-response" not in str(raised.value)


def test_web_scrape_normalizes_timeout(monkeypatch):
    monkeypatch.setattr(
        scraper.requests,
        "get",
        MagicMock(side_effect=requests.Timeout("secret-response")),
    )

    with pytest.raises(_tool_unavailable_error()) as raised:
        scraper.web_scrape("https://example.com")

    assert raised.value.tool_name == "web_scrape"
    assert raised.value.category == "timeout"
    assert "secret-response" not in str(raised.value)


def test_web_search_rejects_direct_call_without_credential(monkeypatch):
    monkeypatch.setattr(search, "TAVILY_API_KEY", "")
    post = MagicMock()
    monkeypatch.setattr(search.requests, "post", post)

    with pytest.raises(_tool_unavailable_error()) as raised:
        search.web_search("query")

    assert raised.value.category == "configuration"
    post.assert_not_called()


def test_web_search_preserves_unsupported_400(monkeypatch):
    monkeypatch.setattr(search, "TAVILY_API_KEY", "configured")
    response = MagicMock(status_code=400)
    response.raise_for_status.side_effect = requests.HTTPError(
        "bad request"
    )
    monkeypatch.setattr(
        search.requests,
        "post",
        MagicMock(return_value=response),
    )

    with pytest.raises(requests.HTTPError, match="bad request"):
        search.web_search("query")
