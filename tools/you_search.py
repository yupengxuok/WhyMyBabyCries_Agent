#!/usr/bin/env python3
"""
You.com Search integration.
Docs: https://docs.you.com/api-reference/search/v1-search
"""
import os
import requests


YOU_SEARCH_URL = "https://ydc-index.io/v1/search"


def you_search(query: str, count: int = 5, timeout_s: int = 15) -> list[dict]:
    """
    Execute a You.com search and return a list of results.
    Requires YOU_API_KEY in environment.
    """
    api_key = os.getenv("YOU_API_KEY")
    if not api_key:
        raise RuntimeError("Missing YOU_API_KEY env var")

    params = {
        "query": query,
        "count": count,
    }
    headers = {
        "X-API-Key": api_key,
    }

    resp = requests.get(YOU_SEARCH_URL, params=params, headers=headers, timeout=timeout_s)
    resp.raise_for_status()
    data = resp.json()

    results = []
    web_items = data.get("results", {}).get("web", [])
    for item in web_items:
        snippets = item.get("snippets") or []
        snippet = snippets[0] if snippets else item.get("description")
        results.append(
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "snippet": snippet,
                "source": item.get("favicon_url"),
            }
        )
    return results
