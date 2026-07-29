import requests
from jarvis.config import TAVILY_API_KEY
from jarvis.tools.errors import (
    ToolUnavailableError,
    raise_for_tool_status,
)
from jarvis.tools.registry import register_tool


@register_tool(
    name="web_search",
    description=(
        "Search the web for up-to-date information. "
        "Input: search query string."
    ),
    required_env_vars=("TAVILY_API_KEY",),
)
def web_search(query: str) -> str:
    if not TAVILY_API_KEY:
        raise ToolUnavailableError("web_search", "configuration")
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "max_results": 5,
            },
            timeout=10,
        )
    except requests.Timeout:
        raise ToolUnavailableError("web_search", "timeout") from None
    except requests.ConnectionError:
        raise ToolUnavailableError(
            "web_search",
            "connectivity",
        ) from None
    raise_for_tool_status(resp, "web_search")
    results = resp.json().get("results", [])
    return "\n\n".join(
        f"Title: {r['title']}\nURL: {r['url']}\n{r['content']}" for r in results
    )
