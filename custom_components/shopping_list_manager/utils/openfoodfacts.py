"""Open Food Facts text search via Search-a-licious.

The old ``/api/v2/search?search_terms=...`` endpoint ignores the search text
entirely (it only filters on tags), so every query returned the same
top-scanned products regardless of what was typed. Free-text search is served
by OFF's Search-a-licious service instead.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

_LOGGER = logging.getLogger(__name__)

OFF_SEARCH_URL = "https://search.openfoodfacts.org/search"

# Fields the card reads from search results.
OFF_SEARCH_FIELDS = (
    "code,product_name,brands,categories_tags,"
    "image_front_thumb_url,image_front_url,image_url"
)

# Catalog country -> OFF countries_tags value. Custom regions have no entry
# and are searched worldwide.
OFF_COUNTRY_TAGS: Dict[str, str] = {
    "NZ": "en:new-zealand",
    "AU": "en:australia",
    "US": "en:united-states",
    "GB": "en:united-kingdom",
    "CA": "en:canada",
    "BE": "en:belgium",
    "ES": "en:spain",
    "FR": "en:france",
}

# Catalog country -> language used to analyse the query (default: English).
OFF_SEARCH_LANGS: Dict[str, str] = {
    "BE": "nl",
    "ES": "es",
    "FR": "fr",
}

# Characters with meaning in the Search-a-licious query syntax. Left in, an
# unbalanced quote or a stray colon makes the whole request fail.
_QUERY_SYNTAX_CHARS = re.compile(r'[\\"():^~*?\[\]{}<>!|&/+\-]')


_QUERY_OPERATORS = {"AND", "OR", "NOT"}


def sanitize_query(query: str) -> str:
    """Strip query-syntax characters and operator words so user text is plain terms."""
    cleaned = _QUERY_SYNTAX_CHARS.sub(" ", query or "")
    return " ".join(w for w in cleaned.split() if w not in _QUERY_OPERATORS)


async def _run_search(session, headers, q: str, page_size: int, lang: str, timeout) -> List[Dict[str, Any]]:
    params = {
        "q": q,
        "page_size": page_size,
        "fields": OFF_SEARCH_FIELDS,
        "langs": lang,
    }
    async with session.get(OFF_SEARCH_URL, params=params, headers=headers, timeout=timeout) as resp:
        if not resp.ok:
            _LOGGER.debug("OFF search returned HTTP %s for %r", resp.status, q)
            return []
        data = await resp.json(content_type=None)
    return data.get("hits", []) or []


async def search_products(
    session,
    headers: Dict[str, str],
    query: str,
    page_size: int,
    country: Optional[str],
    timeout,
) -> List[Dict[str, Any]]:
    """Search OFF by free text, local-country matches first, then worldwide.

    Returns a list of product dicts (``code``, ``product_name``, ...), at most
    ``page_size`` long, without duplicates.
    """
    clean = sanitize_query(query)
    if not clean:
        return []

    lang = OFF_SEARCH_LANGS.get(country or "", "en")
    results: List[Dict[str, Any]] = []
    seen = set()

    def add(hits: List[Dict[str, Any]]) -> None:
        for hit in hits:
            code = hit.get("code")
            if code in seen or not (hit.get("product_name") or "").strip():
                continue
            seen.add(code)
            results.append(hit)

    tag = OFF_COUNTRY_TAGS.get(country or "")
    if tag:
        try:
            add(await _run_search(session, headers, f'{clean} countries_tags:"{tag}"', page_size, lang, timeout))
        except Exception as err:  # noqa: BLE001 - fall through to worldwide search
            _LOGGER.debug("OFF country search failed, falling back to worldwide: %s", err)

    if len(results) < page_size:
        add(await _run_search(session, headers, clean, page_size, lang, timeout))

    return results[:page_size]
