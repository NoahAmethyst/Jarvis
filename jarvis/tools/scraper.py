import requests
from bs4 import BeautifulSoup
from jarvis.tools.registry import register_tool


@register_tool(name="web_scrape", description="Fetch and extract text content from a URL. Input: full URL string.")
def web_scrape(url: str) -> str:
    resp = requests.get(
        url,
        timeout=10,
        headers={"User-Agent": "Mozilla/5.0 (compatible; Jarvis/1.0)"},
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    return text[:5000]
