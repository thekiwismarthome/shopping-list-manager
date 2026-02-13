"""Storage management for Shopping List Manager."""
import logging
from typing import Dict, List, Optional, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    STORAGE_VERSION,
    STORAGE_KEY_LISTS,
    STORAGE_KEY_ITEMS,
    STORAGE_KEY_PRODUCTS,
    STORAGE_KEY_CATEGORIES,
)
from .data.catalog_loader import load_product_catalog
from .models import ShoppingList, Item, Product, Category, generate_id
from .data.category_loader import load_categories

_LOGGER = logging.getLogger(__name__)


class ShoppingListStorage:
    """Handle storage for shopping lists."""
    
    def __init__(self, hass: HomeAssistant, component_path: str) -> None:
        """Initialize storage.
        
        Args:
            hass: Home Assistant instance
            component_path: Path to the component directory
        """
        self.hass = hass
        self._component_path = component_path
        self._store_lists = Store(hass, STORAGE_VERSION, STORAGE_KEY_LISTS)
        self._store_items = Store(hass, STORAGE_VERSION, STORAGE_KEY_ITEMS)
        self._store_products = Store(hass, STORAGE_VERSION, STORAGE_KEY_PRODUCTS)
        self._store_categories = Store(hass, STORAGE_VERSION, STORAGE_KEY_CATEGORIES)
        
        self._lists: Dict[str, ShoppingList] = {}
        self._items: Dict[str, List[Item]] = {}
        self._products: Dict[str, Product] = {}
        self._categories: List[Category] = []
    
    async def async_load(self) -> None:
        """Load data from storage."""
        # Load lists
        lists_data = await self._store_lists.async_load()
        if lists_data:
            self._lists = {
                list_id: ShoppingList(**list_data)
                for list_id, list_data in lists_data.items()
            }
            _LOGGER.debug("Loaded %d lists", len(self._lists))
        else:
            # Create default list if none exist
            default_list = ShoppingList(
                id=generate_id(),
                name="Shopping List",
                icon="mdi:cart",
                active=True
            )
            self._lists[default_list.id] = default_list
            await self._save_lists()
            _LOGGER.info("Created default shopping list")
        
        # Load items
        items_data = await self._store_items.async_load()
        if items_data:
            self._items = {
                list_id: [Item(**item_data) for item_data in items]
                for list_id, items in items_data.items()
            }
            _LOGGER.debug("Loaded items for %d lists", len(self._items))
        
        # Load products
        products_data = await self._store_products.async_load()
        if products_data:
            self._products = {
                product_id: Product(**product_data)
                for product_id, product_data in products_data.items()
            }
            _LOGGER.debug("Loaded %d products", len(self._products))
        
        # Load categories
        categories_data = await self._store_categories.async_load()
        if categories_data:
            self._categories = [Category(**cat_data) for cat_data in categories_data]
            _LOGGER.debug("Loaded %d categories", len(self._categories))
        else:
            # Initialize with default categories from JSON file
            country_code = getattr(self.hass.config, 'country', None)
            default_categories = load_categories(self._component_path, country_code)
            self._categories = [Category(**cat) for cat in default_categories]
            await self._save_categories()
            _LOGGER.info(
                "Initialized %d default categories for country: %s", 
                len(self._categories),
                country_code or "default"
            )
        
        # NEW: Load product catalog if products are empty
        if not self._products:
            country_code = getattr(self.hass.config, 'country', None)
            catalog_products = load_product_catalog(self._component_path, country_code)
            
            if catalog_products:
                _LOGGER.info("Importing %d products from catalog", len(catalog_products))
                for prod_data in catalog_products:
                    try:
                        # Create Product from catalog data
                        product = Product(
                            id=prod_data.get("id", generate_id()),
                            name=prod_data["name"],
                            category_id=prod_data.get("category_id", "other"),
                            aliases=prod_data.get("aliases", []),
                            default_unit=prod_data.get("default_unit", "units"),
                            default_quantity=prod_data.get("default_quantity", 1),
                            price=prod_data.get("price") or prod_data.get("typical_price"),
                            currency=self.hass.config.currency,
                            barcode=prod_data.get("barcode"),
                            brands=prod_data.get("brands", []),
                            image_url=prod_data.get("image_url", ""),
                            custom=False,
                            source="catalog"
                        )
                        self._products[product.id] = product
                    except Exception as err:
                        _LOGGER.error("Failed to import product %s: %s", prod_data.get("name"), err)
                        continue
                
                await self._save_products()
                _LOGGER.info("Successfully imported %d products from catalog", len(self._products))
    
    # Lists methods
    async def _save_lists(self) -> None:
        """Save lists to storage."""
        data = {list_id: lst.to_dict() for list_id, lst in self._lists.items()}
        await self._store_lists.async_save(data)
    
    def get_lists(self) -> List[ShoppingList]:
        """Get all lists."""
        return list(self._lists.values())
    
    def get_list(self, list_id: str) -> Optional[ShoppingList]:
        """Get a specific list."""
        return self._lists.get(list_id)
    
    def get_active_list(self) -> Optional[ShoppingList]:
        """Get the active list."""
        for lst in self._lists.values():
            if lst.active:
                return lst
        return None
    
    async def create_list(self, name: str, icon: str = "mdi:cart") -> ShoppingList:
        """Create a new list."""
        new_list = ShoppingList(
            id=generate_id(),
            name=name,
            icon=icon,
            category_order=[cat.id for cat in self._categories]
        )
        self._lists[new_list.id] = new_list
        self._items[new_list.id] = []
        await self._save_lists()
        _LOGGER.info("Created new list: %s", name)
        return new_list
    
    async def update_list(self, list_id: str, **kwargs) -> Optional[ShoppingList]:
        """Update a list."""
        if list_id not in self._lists:
            return None
        
        lst = self._lists[list_id]
        for key, value in kwargs.items():
            if hasattr(lst, key):
                setattr(lst, key, value)
        
        from .models import current_timestamp
        lst.updated_at = current_timestamp()
        
        await self._save_lists()
        _LOGGER.debug("Updated list: %s", list_id)
        return lst
    
    async def delete_list(self, list_id: str) -> bool:
        """Delete a list."""
        if list_id not in self._lists:
            return False
        
        del self._lists[list_id]
        if list_id in self._items:
            del self._items[list_id]
        
        await self._save_lists()
        await self._save_items()
        _LOGGER.info("Deleted list: %s", list_id)
        return True
    
    async def set_active_list(self, list_id: str) -> bool:
        """Set the active list."""
        if list_id not in self._lists:
            return False
        
        # Deactivate all lists
        for lst in self._lists.values():
            lst.active = False
        
        # Activate the specified list
        self._lists[list_id].active = True
        
        await self._save_lists()
        _LOGGER.debug("Set active list: %s", list_id)
        return True
    
    # Items methods
    async def _save_items(self) -> None:
        """Save items to storage."""
        data = {
            list_id: [item.to_dict() for item in items]
            for list_id, items in self._items.items()
        }
        await self._store_items.async_save(data)
    
    def get_items(self, list_id: str) -> List[Item]:
        """Get items for a list."""
        return self._items.get(list_id, [])
    
    async def add_item(self, list_id: str, **kwargs) -> Optional[Item]:
        """Add an item to a list."""
        if list_id not in self._lists:
            return None
        
        new_item = Item(
            id=generate_id(),
            list_id=list_id,
            **kwargs
        )
        new_item.calculate_total()
        
        if list_id not in self._items:
            self._items[list_id] = []
        
        self._items[list_id].append(new_item)
        
        # Update product frequency if product_id provided
        if new_item.product_id and new_item.product_id in self._products:
            product = self._products[new_item.product_id]
            product.user_frequency += 1
            from .models import current_timestamp
            product.last_used = current_timestamp()
            await self._save_products()
        
        await self._save_items()
        _LOGGER.debug("Added item to list %s: %s", list_id, new_item.name)
        return new_item
    
    async def update_item(self, item_id: str, **kwargs) -> Optional[Item]:
        """Update an item."""
        for list_id, items in self._items.items():
            for item in items:
                if item.id == item_id:
                    for key, value in kwargs.items():
                        if hasattr(item, key):
                            setattr(item, key, value)
                    
                    from .models import current_timestamp
                    item.updated_at = current_timestamp()
                    item.calculate_total()
                    
                    await self._save_items()
                    _LOGGER.debug("Updated item: %s", item_id)
                    return item
        
        return None
    
    async def check_item(self, item_id: str, checked: bool) -> Optional[Item]:
        """Check or uncheck an item."""
        for items in self._items.values():
            for item in items:
                if item.id == item_id:
                    item.checked = checked
                    from .models import current_timestamp
                    item.checked_at = current_timestamp() if checked else None
                    item.updated_at = current_timestamp()
                    
                    await self._save_items()
                    _LOGGER.debug("Checked item: %s = %s", item_id, checked)
                    return item
        
        return None
    
    async def delete_item(self, item_id: str) -> bool:
        """Delete an item."""
        for list_id, items in self._items.items():
            for i, item in enumerate(items):
                if item.id == item_id:
                    del self._items[list_id][i]
                    await self._save_items()
                    _LOGGER.debug("Deleted item: %s", item_id)
                    return True
        
        return False
    
    async def bulk_check_items(self, item_ids: List[str], checked: bool) -> int:
        """Bulk check/uncheck items."""
        count = 0
        from .models import current_timestamp
        timestamp = current_timestamp()
        
        for items in self._items.values():
            for item in items:
                if item.id in item_ids:
                    item.checked = checked
                    item.checked_at = timestamp if checked else None
                    item.updated_at = timestamp
                    count += 1
        
        if count > 0:
            await self._save_items()
            _LOGGER.debug("Bulk checked %d items", count)
        
        return count
    
    async def clear_checked_items(self, list_id: str) -> int:
        """Clear all checked items from a list."""
        if list_id not in self._items:
            return 0
        
        original_count = len(self._items[list_id])
        self._items[list_id] = [item for item in self._items[list_id] if not item.checked]
        removed_count = original_count - len(self._items[list_id])
        
        if removed_count > 0:
            await self._save_items()
            _LOGGER.info("Cleared %d checked items from list %s", removed_count, list_id)
        
        return removed_count
    
    def get_list_total(self, list_id: str) -> Dict[str, Any]:
        """Get total price for a list."""
        items = self.get_items(list_id)
        total = 0.0
        item_count = 0
        
        for item in items:
            if not item.checked and item.price is not None:
                total += item.quantity * item.price
                item_count += 1
        
        return {
            "total": round(total, 2),
            "currency": self.hass.config.currency,
            "item_count": item_count
        }
    
    # Products methods
    async def _save_products(self) -> None:
        """Save products to storage."""
        data = {product_id: product.to_dict() for product_id, product in self._products.items()}
        await self._store_products.async_save(data)
    
    def get_products(self) -> List[Product]:
        """Get all products."""
        return list(self._products.values())
    
    def get_product(self, product_id: str) -> Optional[Product]:
        """Get a specific product."""
        return self._products.get(product_id)
    
    def search_products(self, query: str, limit: int = 10) -> List[Product]:
        """Search products by name or alias."""
        query_lower = query.lower()
        results = []
        
        for product in self._products.values():
            # Check name
            if query_lower in product.name.lower():
                results.append(product)
                continue
            
            # Check aliases
            if any(query_lower in alias.lower() for alias in product.aliases):
                results.append(product)
                continue
        
        # Sort by frequency
        results.sort(key=lambda p: p.user_frequency, reverse=True)
        
        return results[:limit]
    
    def get_product_suggestions(self, limit: int = 20) -> List[Product]:
        """Get product suggestions based on usage frequency."""
        products = list(self._products.values())
        products.sort(key=lambda p: p.user_frequency, reverse=True)
        return products[:limit]
    
    async def add_product(self, **kwargs) -> Product:
        """Add a new product."""
        new_product = Product(
            id=generate_id(),
            currency=self.hass.config.currency,
            **kwargs
        )
        self._products[new_product.id] = new_product
        await self._save_products()
        _LOGGER.debug("Added product: %s", new_product.name)
        return new_product
    
    async def update_product(self, product_id: str, **kwargs) -> Optional[Product]:
        """Update a product."""
        if product_id not in self._products:
            return None
        
        product = self._products[product_id]
        for key, value in kwargs.items():
            if hasattr(product, key):
                setattr(product, key, value)
        
        await self._save_products()
        _LOGGER.debug("Updated product: %s", product_id)
        return product
    
    # Categories methods
    async def _save_categories(self) -> None:
        """Save categories to storage."""
        data = [cat.to_dict() for cat in self._categories]
        await self._store_categories.async_save(data)
    
    def get_categories(self) -> List[Category]:
        """Get all categories."""
        return self._categories
