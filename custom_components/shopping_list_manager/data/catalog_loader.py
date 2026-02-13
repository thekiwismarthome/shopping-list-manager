
"""Product catalog loader for Shopping List Manager."""
import json
import logging
import os
from typing import List, Dict, Any

_LOGGER = logging.getLogger(__name__)


def load_product_catalog(component_path: str, country_code: str = "NZ") -> List[Dict[str, Any]]:
    """Load product catalog from JSON file.
    
    Args:
        component_path: Path to the component directory
        country_code: Country code (e.g., 'NZ', 'AU', 'US')
    
    Returns:
        List of product dictionaries
    """
    # Try country-specific catalog first
    if country_code:
        country_file = os.path.join(
            component_path, "data", f"products_catalog_{country_code.lower()}.json"
        )
        if os.path.exists(country_file):
            catalog_file = country_file
            _LOGGER.debug("Using country-specific product catalog: %s", country_code)
        else:
            _LOGGER.warning(
                "No country-specific catalog found for %s",
                country_code
            )
            return []
    else:
        return []
    
    try:
        with open(catalog_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            
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
