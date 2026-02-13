"""Category loader utility."""
import json
import logging
import os
from typing import List, Dict, Any
import aiofiles

_LOGGER = logging.getLogger(__name__)


async def load_categories(component_path: str, country_code: str = None) -> List[Dict[str, Any]]:
    """Load categories from JSON file asynchronously.
    
    Args:
        component_path: Path to the component directory
        country_code: Country code from HA config (e.g., 'NZ', 'AU', 'US')
                     If None, loads default categories.json
    
    Returns:
        List of category dictionaries
    """
    import os
    
    # Try country-specific file first if country_code provided
    if country_code:
        country_file = os.path.join(
            component_path, "data", f"categories_{country_code.lower()}.json"
        )
        if os.path.exists(country_file):
            categories_file = country_file
            _LOGGER.debug("Using country-specific categories: %s", country_code)
        else:
            _LOGGER.debug(
                "No country-specific categories found for %s, using default",
                country_code
            )
            categories_file = os.path.join(component_path, "data", "categories.json")
    else:
        categories_file = os.path.join(component_path, "data", "categories.json")
    
    try:
        async with aiofiles.open(categories_file, "r", encoding="utf-8") as f:
            content = await f.read()
            data = json.loads(content)
            
        _LOGGER.info(
            "Loaded categories version %s for region %s",
            data.get("version", "unknown"),
            data.get("region", "default")
        )
        
        return data.get("categories", [])
        
    except FileNotFoundError:
        _LOGGER.error("Categories file not found: %s", categories_file)
        return _get_fallback_categories()
    except json.JSONDecodeError as err:
        _LOGGER.error("Failed to parse categories file: %s", err)
        return _get_fallback_categories()
    except Exception as err:
        _LOGGER.error("Unexpected error loading categories: %s", err)
        return _get_fallback_categories()


def _get_fallback_categories() -> List[Dict[str, Any]]:
    """Get minimal fallback categories if file loading fails.
    
    Returns:
        List of basic category dictionaries
    """
    _LOGGER.warning("Using fallback categories")
    
    return [
        {
            "id": "produce",
            "name": "Produce",
            "icon": "mdi:fruit-cherries",
            "color": "#4CAF50",
            "sort_order": 1,
            "system": True
        },
        {
            "id": "dairy",
            "name": "Dairy",
            "icon": "mdi:cheese",
            "color": "#FFC107",
            "sort_order": 2,
            "system": True
        },
        {
            "id": "other",
            "name": "Other",
            "icon": "mdi:dots-horizontal",
            "color": "#9E9E9E",
            "sort_order": 99,
            "system": True
        }
    ]
