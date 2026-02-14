"""Product catalog loader for Shopping List Manager."""
import json
import logging
from typing import List, Dict, Any
import aiofiles

_LOGGER = logging.getLogger(__name__)


async def load_product_catalog(component_path: str, country_code: str = "NZ") -> List[Dict[str, Any]]:
    """Load product catalog from JSON file asynchronously.
    
    Args:
        component_path: Path to the component directory
        country_code: Country code (e.g., 'NZ', 'AU', 'US')
    
    Returns:
        List of product dictionaries
    """
    import os
    
    # Try country-specific catalog first
    if country_code:
        catalog_file = os.path.join(
            component_path, "data", f"products_catalog_{country_code.lower()}.json"
        )
        if not os.path.exists(catalog_file):
            _LOGGER.warning(
                "No country-specific catalog found for %s at %s",
                country_code,
                catalog_file
            )
            return []
    else:
        return []
    
    try:
        # Use aiofiles for async file reading
        async with aiofiles.open(catalog_file, "r", encoding="utf-8") as f:
            content = await f.read()
            data = json.loads(content)
            
        _LOGGER.info(
            "Loaded product catalog version %s for region %s",
            data.get("version", "unknown"),
            data.get("region", "default")
        )
        
        products = data.get("products", [])
        _LOGGER.info("Loaded %d products from catalog", len(products))
        
        return products
        
    except FileNotFoundError:
        _LOGGER.error("Product catalog file not found: %s", catalog_file)
        return []
    except json.JSONDecodeError as err:
        _LOGGER.error("Failed to parse product catalog file: %s", err)
        return []
    except Exception as err:
        _LOGGER.error("Unexpected error loading product catalog: %s", err)
        return []
