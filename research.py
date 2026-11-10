"""Search providers. Results are evidence candidates, never truth."""
from __future__ import annotations

import settings

MAX_CONTENT_CHARS = 1500


class TavilySearcher:
    def __init__(self, api_key: str | None = None, max_results: int = 5):
        from tavily import TavilyClient

        self.client = TavilyClient(api_key=api_key or settings.TAVILY_API_KEY)
        self.max_results = max_results

    def search(self, query: str) -> list[dict]:
        resp = self.client.search(query=query, search_depth="basic", max_results=self.max_results)
        return [
            {
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "content": (r.get("content") or "")[:MAX_CONTENT_CHARS],
                "published_date": r.get("published_date") or "",
            }
            for r in resp.get("results", [])
        ]


class FakeSearcher:
    """Returns fixed results; used by tests."""

    def __init__(self, results: list[dict] | None = None):
        self.results = results or []
        self.queries: list[str] = []

    def search(self, query: str) -> list[dict]:
        self.queries.append(query)
        return [dict(r) for r in self.results]


def get_searcher():
    return TavilySearcher() if settings.TAVILY_API_KEY else None
