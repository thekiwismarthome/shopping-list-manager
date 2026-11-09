"""The main supermarket chains for each built-in region (names only)."""
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

_FILE = Path(__file__).with_name("supermarkets.json")


@lru_cache(maxsize=1)
def _load() -> Dict[str, List[str]]:
    with _FILE.open(encoding="utf-8") as fh:
        return json.load(fh)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def get_chains(country: str) -> List[Dict[str, str]]:
    """Chains for a region, as [{id, name}]. Empty for a custom region."""
    return [{"id": _slug(n), "name": n} for n in _load().get((country or "").upper(), [])]
