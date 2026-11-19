import logging
import requests
from jarvis.config import TAVILY_API_KEY
from jarvis.tools.errors import (
    ToolUnavailableError,
    raise_for_tool_status,
)
from jarvis.tools.registry import register_tool
from jarvis.logging_config import format_log_tags


logger = logging.getLogger(__name__)


@register_tool(
    name="web_search",
    description=(
        "Search the web for up-to-date information. "
        "Input: search query string."
    ),
    required_env_vars=("TAVILY_API_KEY",),
    response_format="content_and_artifact",
)
def _web_search_tool(query: str) -> tuple[str, dict]:
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
    logger.info("%s", format_log_tags(
        ("动作", "网络搜索结果"), ("工具", "web_search"), ("结果条数", len(results)),
    ))
    sources = [
        {"title": result["title"], "url": result["url"], "text": result["content"]}
        for result in results
    ]
    content = "\n\n".join(f"Title: {r['title']}\nURL: {r['url']}\n{r['text']}" for r in sources)
    return content, {"sources": sources}


def web_search(query: str) -> str:
    return _web_search_tool(query)[0]
