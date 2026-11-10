"""Find shops on a map (OpenStreetMap Nominatim) for the Supermarkets settings.

Only the words the user typed, the chain they picked and, when they allowed it, the rough
position they are searching around are sent. Nothing else leaves Home Assistant.
Nominatim asks for at most one request a second, so calls are spaced and answers are cached.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import Any, Dict, List, Optional, Tuple

_LOGGER = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "HomeAssistant-ShoppingListManager/1.0 (supermarket lookup)"

# Searched around the user's position in growing steps (degrees; 0.1 is about 11 km), starting small.
# Nominatim returns the most "important" matches in the box, not the nearest, so a big box over a city
# loses nearby shops of a common chain. A small box that holds enough shops cannot.
_RADII_DEG = (0.05, 0.1, 0.18, 0.33, 0.6, 1.1, 2.0)
_MAX_HITS = 40  # the most Nominatim gives for one search
# With no chain picked, only places that sell groceries (not a takeaway that tagged itself a shop)
_GROCERY_TYPES = {"supermarket", "convenience", "greengrocer", "wholesale", "general", "grocery"}
_MIN_GAP_S = 1.1
_CACHE_TTL_S = 3600
_CACHE_MAX = 100

_lock = asyncio.Lock()
_last_call = 0.0
_cache: Dict[Tuple, Tuple[float, List[Dict[str, Any]], Optional[Tuple[float, float]]]] = {}


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(a)))


def _norm(text: str) -> str:
    return "".join(ch for ch in (text or "").lower() if ch.isalnum())


def split_chain(query: str, chain_names: List[str]) -> Tuple[Optional[str], str]:
    """If the text starts with a known chain ("PAK'nSAVE Glen Innes"), split it into chain and place."""
    query = (query or "").strip()
    for name in chain_names:
        want = _norm(name)
        if not want or not _norm(query).startswith(want):
            continue
        for i in range(1, len(query) + 1):
            if _norm(query[:i]) == want:
                return name, query[i:].strip(" ,-")
    return None, query


def format_address(addr: Dict[str, Any]) -> str:
    """A short postal-style address from Nominatim's address parts."""
    street = " ".join(p for p in (addr.get("house_number"), addr.get("road")) if p)
    place = (
        addr.get("suburb") or addr.get("neighbourhood") or addr.get("quarter")
        or addr.get("city_district") or ""
    )
    town = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality") or ""
    parts = []
    for p in (street, place, town, addr.get("postcode")):
        if p and p not in parts:
            parts.append(p)
    return ", ".join(parts)


def _parse(hit: Dict[str, Any], lat: Optional[float], lng: Optional[float]) -> Optional[Dict[str, Any]]:
    try:
        plat, plon = float(hit["lat"]), float(hit["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    display = hit.get("display_name") or ""
    name = (hit.get("name") or display.split(",")[0]).strip()
    if not name:
        return None
    addr = hit.get("address") or {}
    # OpenStreetMap often calls a shop just "PAK'nSAVE"; add the suburb so they can be told apart
    suburb = addr.get("suburb") or addr.get("neighbourhood") or addr.get("town") or addr.get("village") or ""
    if suburb and suburb.lower() not in name.lower():
        name = f"{name} {suburb}"
    result = {
        "name": name[:80],
        "address": format_address(addr) or display[:200],
        "latitude": round(plat, 6),
        "longitude": round(plon, 6),
        "distance_km": None,
    }
    if lat is not None and lng is not None:
        result["distance_km"] = round(distance_km(lat, lng, plat, plon), 1)
    return result


async def _get(session, params: Dict[str, Any], timeout) -> List[Dict[str, Any]]:
    """One polite request to Nominatim."""
    global _last_call
    async with _lock:
        wait = _MIN_GAP_S - (time.monotonic() - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with session.get(
                NOMINATIM_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=timeout
            ) as resp:
                if not resp.ok:
                    _LOGGER.debug("Nominatim returned HTTP %s", resp.status)
                    raise RuntimeError(f"HTTP {resp.status}")
                data = await resp.json(content_type=None)
        finally:
            _last_call = time.monotonic()
    return data if isinstance(data, list) else []


def _box(lat: float, lng: float, radius: float) -> str:
    dx = radius / max(0.2, math.cos(math.radians(lat)))
    return f"{lng - dx:.5f},{lat + radius:.5f},{lng + dx:.5f},{lat - radius:.5f}"


async def search_places(
    session,
    chain: Optional[str],
    place: Optional[str],
    country: Optional[str],
    lat: Optional[float],
    lng: Optional[float],
    limit: int,
    timeout,
) -> Tuple[List[Dict[str, Any]], Optional[Tuple[float, float]]]:
    """Shops for a chain and/or a place, nearest first when there is a position to measure from.

    - a position (lat, lng): the chain (or any supermarket) closest to it
    - a chain and a place ("PAK'nSAVE", "Glen Innes"): the place is found first, then the chain nearest it
    - only a chain: that chain's shops, only a place or name: shops by that name
    Returns the shops and the position distances are measured from, if any.
    """
    chain = " ".join((chain or "").split())[:80]
    place = " ".join((place or "").split())[:100]
    if not (chain or place) and lat is None:
        return [], None

    key = (chain.lower(), place.lower(), (country or "").upper(),
           None if lat is None else round(lat, 2), None if lng is None else round(lng, 2), limit)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < _CACHE_TTL_S:
        return hit[1], hit[2]

    base: Dict[str, Any] = {"format": "jsonv2", "addressdetails": 1}
    if country:
        base["countrycodes"] = country.lower()

    centre: Optional[Tuple[float, float]] = (lat, lng) if lat is not None and lng is not None else None
    if centre is None and chain and place:
        found = await _get(session, dict(base, q=place, limit=1), timeout)
        if not found:
            return [], None
        try:
            centre = (float(found[0]["lat"]), float(found[0]["lon"]))
        except (KeyError, TypeError, ValueError):
            return [], None

    raw: List[Dict[str, Any]] = []
    if centre:
        terms = chain or place or "supermarket"
        for radius in _RADII_DEG:
            raw = [h for h in await _get(session, dict(base, q=terms, limit=_MAX_HITS, bounded=1,
                                                       viewbox=_box(centre[0], centre[1], radius)), timeout)
                   if h.get("category") == "shop" and (chain or place or h.get("type") in _GROCERY_TYPES)]
            # Enough close shops: stop. In thinly served areas settle for a few after a wide look.
            if len(raw) >= limit or (radius >= 0.6 and len(raw) >= 3):
                break
    else:
        raw = [h for h in await _get(session, dict(base, q=chain or place, limit=20), timeout)
               if h.get("category") == "shop"]

    results: List[Dict[str, Any]] = []
    seen = set()
    for item in raw:
        parsed = _parse(item, centre[0] if centre else None, centre[1] if centre else None)
        if not parsed:
            continue
        # The same shop can be mapped twice (as a building and as a shop): same name within ~150 m
        ident = (parsed["name"].lower(), round(parsed["latitude"], 3), round(parsed["longitude"], 3))
        if item.get("place_id") in seen or ident in seen:
            continue
        seen.add(item.get("place_id"))
        seen.add(ident)
        results.append(parsed)
    if centre:
        results.sort(key=lambda r: r["distance_km"])
    results = results[:limit]

    if len(_cache) >= _CACHE_MAX:
        _cache.pop(next(iter(_cache)))
    _cache[key] = (time.monotonic(), results, centre)
    return results, centre
