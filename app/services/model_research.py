from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


def search_model_references(model_name: str, max_results: int = 6) -> list[dict[str, Any]]:
    """Search public academic APIs for model/algorithm references.

    The search is best-effort and never blocks the modeling workflow. Results are
    used as context for the LLM report, not as automatically verified citations.
    """
    query = model_name.strip()
    if not query:
        return []
    results: list[dict[str, Any]] = []
    results.extend(search_semantic_scholar(query, max_results=max_results))
    if len(results) < max_results:
        results.extend(search_crossref(query, max_results=max_results - len(results)))
    return rank_results(dedupe_results(results), query)[:max_results]


def search_semantic_scholar(query: str, max_results: int) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "query": f"{query} algorithm model mathematical modeling",
            "limit": max_results,
            "fields": "title,year,authors,url,abstract,venue,citationCount",
        }
    )
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?{params}"
    try:
        payload = fetch_json(url)
    except Exception:
        return []
    items = payload.get("data") or []
    results = []
    for item in items:
        title = item.get("title") or ""
        if not title:
            continue
        authors = [author.get("name", "") for author in item.get("authors", []) if author.get("name")]
        results.append(
            {
                "source": "Semantic Scholar",
                "title": title,
                "year": item.get("year"),
                "authors": authors[:6],
                "venue": item.get("venue") or "",
                "url": item.get("url") or "",
                "abstract": trim_text(item.get("abstract") or "", 900),
                "citation_count": item.get("citationCount"),
            }
        )
    return results


def search_crossref(query: str, max_results: int) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "query": f"{query} algorithm model",
            "rows": max_results,
            "select": "title,author,published-print,published-online,container-title,URL,abstract,is-referenced-by-count",
        }
    )
    url = f"https://api.crossref.org/works?{params}"
    try:
        payload = fetch_json(url)
    except Exception:
        return []
    items = payload.get("message", {}).get("items", []) or []
    results = []
    for item in items:
        title_values = item.get("title") or []
        title = title_values[0] if title_values else ""
        if not title:
            continue
        authors = []
        for author in item.get("author", []) or []:
            name = " ".join(part for part in [author.get("given", ""), author.get("family", "")] if part).strip()
            if name:
                authors.append(name)
        year = extract_crossref_year(item)
        container = item.get("container-title") or []
        results.append(
            {
                "source": "Crossref",
                "title": title,
                "year": year,
                "authors": authors[:6],
                "venue": container[0] if container else "",
                "url": item.get("URL") or "",
                "abstract": trim_text(strip_tags(item.get("abstract") or ""), 900),
                "citation_count": item.get("is-referenced-by-count"),
            }
        )
    return results


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "MathModelingWorkbench/0.1 (local academic assistant)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def extract_crossref_year(item: dict[str, Any]) -> int | None:
    for key in ["published-print", "published-online"]:
        parts = item.get(key, {}).get("date-parts") or []
        if parts and parts[0]:
            try:
                return int(parts[0][0])
            except Exception:
                return None
    return None


def dedupe_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    unique = []
    for item in results:
        title = " ".join(str(item.get("title", "")).lower().split())
        if not title or title in seen:
            continue
        seen.add(title)
        unique.append(item)
    return unique


def rank_results(results: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    return sorted(results, key=lambda item: score_result(item, query), reverse=True)


def score_result(item: dict[str, Any], query: str) -> float:
    query_norm = " ".join(query.lower().split())
    tokens = [token for token in re_split_words(query_norm) if len(token) >= 2]
    title = str(item.get("title") or "").lower()
    abstract = str(item.get("abstract") or "").lower()
    score = 0.0
    if query_norm and query_norm in title:
        score += 12
    if query_norm and query_norm in abstract:
        score += 5
    for token in tokens:
        if token in title:
            score += 3
        if token in abstract:
            score += 1
    citation_count = item.get("citation_count")
    try:
        score += min(float(citation_count or 0), 1000.0) / 250.0
    except Exception:
        pass
    try:
        year = int(item.get("year") or 0)
        if year >= 2015:
            score += 0.5
    except Exception:
        pass
    return score


def re_split_words(text: str) -> list[str]:
    current = []
    words = []
    for char in text:
        if char.isalnum() or char in {"_", "-"}:
            current.append(char)
        elif current:
            words.append("".join(current))
            current = []
    if current:
        words.append("".join(current))
    return words


def strip_tags(text: str) -> str:
    result = []
    inside = False
    for char in text:
        if char == "<":
            inside = True
            continue
        if char == ">":
            inside = False
            continue
        if not inside:
            result.append(char)
    return "".join(result)


def trim_text(text: str, limit: int) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."
