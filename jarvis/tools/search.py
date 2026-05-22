import requests
from jarvis.config import TAVILY_API_KEY
from jarvis.tools.registry import register_tool


@register_tool(name="web_search", description="Search the web for up-to-date information. Input: search query string.")
def web_search(query: str) -> str:
    resp = requests.post(
        "https://api.tavily.com/search",
        json={"api_key": TAVILY_API_KEY, "query": query, "max_results": 5},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return "\n\n".join(
        f"Title: {r['title']}\nURL: {r['url']}\n{r['content']}" for r in results
    )
