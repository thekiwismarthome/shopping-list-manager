"""Storage management for Shopping List Manager."""
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from .utils.search import ProductSearch
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    STORAGE_VERSION,
    STORAGE_KEY_LISTS,
    STORAGE_KEY_ITEMS,
    STORAGE_KEY_PRODUCTS,
    STORAGE_KEY_CATEGORIES,
    STORAGE_KEY_LOYALTY_CARDS,
    STORAGE_KEY_CUSTOM_REGIONS,
    IMAGES_LOCAL_DIR,
    LEGACY_IMAGES_LOCAL_DIR,
    LOCAL_IMAGE_URL_PREFIX,
    LEGACY_IMAGE_URL_PREFIX,
)
from .data.catalog_loader import load_product_catalog
from .models import ShoppingList, Item, Product, Category, LoyaltyCard, generate_id
from .data.category_loader import load_categories

_LOGGER = logging.getLogger(__name__)


class ShoppingListStorage:
    """Handle storage for shopping lists."""
    
    def __init__(self, hass: HomeAssistant, component_path: str, country: str = "NZ") -> None:
        """Initialize storage.
        
        Args:
            hass: Home Assistant instance
            component_path: Path to the component directory
            country: Country code (NZ, AU, US, GB, CA, etc.)
        """
        self.hass = hass
        self._component_path = component_path
        self._country = country  # Store country
        self._store_lists = Store(hass, STORAGE_VERSION, STORAGE_KEY_LISTS)
        self._store_items = Store(hass, STORAGE_VERSION, STORAGE_KEY_ITEMS)
        self._store_products = Store(hass, STORAGE_VERSION, STORAGE_KEY_PRODUCTS)
        self._store_categories = Store(hass, STORAGE_VERSION, STORAGE_KEY_CATEGORIES)
        self._store_loyalty_cards = Store(hass, STORAGE_VERSION, STORAGE_KEY_LOYALTY_CARDS)
        self._store_custom_regions = Store(hass, STORAGE_VERSION, STORAGE_KEY_CUSTOM_REGIONS)

        self._lists: Dict[str, ShoppingList] = {}
        self._items: Dict[str, List[Item]] = {}
        self._products: Dict[str, Product] = {}
        self._categories: List[Category] = []
        self._loyalty_cards: Dict[str, LoyaltyCard] = {}
        self._custom_regions: Dict[str, Any] = {}  # code -> {name, currency_symbol, language}
        self._search_engine: Optional[ProductSearch] = None
        self._images_dir = Path(hass.config.path(IMAGES_LOCAL_DIR))
        self._legacy_images_dir = Path(hass.config.path(LEGACY_IMAGES_LOCAL_DIR))
    
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

        # Ensure image directory exists and migrate legacy image paths/URLs.
        self._images_dir.mkdir(parents=True, exist_ok=True)
        await self._migrate_legacy_images_and_urls()
        
        # Load country-specific system categories so labels follow the selected country.
        await self._load_categories_for_country(self._country)
        
        # Load product catalog if products are empty
        if not self._products:
            _LOGGER.info("Loading product catalog for country: %s", self._country)
            catalog_products = await load_product_catalog(self._component_path, self._country)  # Use self._country
            
            if catalog_products:
                _LOGGER.info("Importing %d products from catalog", len(catalog_products))
                # ... rest of import code ...
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
                            source="catalog",
                            tags=prod_data.get("tags", []),
                            collections=prod_data.get("collections", []),
                            taxonomy=prod_data.get("taxonomy", {}),
                            allergens=prod_data.get("allergens", []),
                            substitution_group=prod_data.get("substitution_group", ""),
                            priority_level=prod_data.get("priority_level", 0),
                            image_hint=prod_data.get("image_hint", "")
                        )
                        self._products[product.id] = product
                    except Exception as err:
                        _LOGGER.error("Failed to import product %s: %s", prod_data.get("name"), err)
                        continue
                
                await self._save_products()
                _LOGGER.info("Successfully imported %d products from catalog", len(self._products))
    
        # Load loyalty cards
        loyalty_data = await self._store_loyalty_cards.async_load()
        if loyalty_data:
            self._loyalty_cards = {
                card_id: LoyaltyCard(**card_data)
                for card_id, card_data in loyalty_data.items()
            }
            _LOGGER.debug("Loaded %d loyalty cards", len(self._loyalty_cards))

        # Load custom regions (migrate old string-only format)
        custom_regions_data = await self._store_custom_regions.async_load()
        if custom_regions_data:
            raw = custom_regions_data.get("regions", {})
            self._custom_regions = {
                k: (v if isinstance(v, dict) else {"name": v, "currency_symbol": None, "language": None})
                for k, v in raw.items()
            }
            _LOGGER.debug("Loaded %d custom regions", len(self._custom_regions))

# Initialize search engine after products are loaded
        if self._products:
            products_dict = {pid: p.to_dict() for pid, p in self._products.items()}
            self._search_engine = ProductSearch(products_dict)
            _LOGGER.debug("Initialized product search engine with %d products", len(self._products))
        else:
            self._search_engine = None
            _LOGGER.warning("No products loaded, search engine not initialized")
            
    # Lists methods
    async def _save_lists(self) -> None:
        """Save lists to storage."""
        data = {list_id: lst.to_dict() for list_id, lst in self._lists.items()}
        await self._store_lists.async_save(data)
    
    def get_lists(self, user_id: str = None, is_admin: bool = False) -> List[ShoppingList]:
        """Get lists visible to the specified user.

        Global lists (owner_id=None) are visible to everyone.
        Private lists are visible to their owner, anyone in allowed_users, and admins.
        """
        all_lists = list(self._lists.values())
        if is_admin or user_id is None:
            return all_lists
        return [
            lst for lst in all_lists
            if lst.owner_id is None
            or lst.owner_id == user_id
            or user_id in (lst.allowed_users or [])
        ]
    
    def get_list(self, list_id: str) -> Optional[ShoppingList]:
        """Get a specific list."""
        return self._lists.get(list_id)
    
    def get_active_list(self) -> Optional[ShoppingList]:
        """Get the active list."""
        for lst in self._lists.values():
            if lst.active:
                return lst
        return None
    
    async def create_list(self, name: str, icon: str = "mdi:cart", owner_id: str = None) -> ShoppingList:
        """Create a new list. Pass owner_id to make the list private to that user."""
        new_list = ShoppingList(
            id=generate_id(),
            name=name,
            icon=icon,
            category_order=[cat.id for cat in self._categories],
            owner_id=owner_id,
        )
        self._lists[new_list.id] = new_list
        self._items[new_list.id] = []
        await self._save_lists()
        await self._write_config_backup()
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
    
    async def update_list_members(self, list_id: str, allowed_users: List[str]) -> Optional[ShoppingList]:
        """Update the allowed_users for a private list."""
        if list_id not in self._lists:
            return None
        lst = self._lists[list_id]
        lst.allowed_users = allowed_users
        from .models import current_timestamp
        lst.updated_at = current_timestamp()
        await self._save_lists()
        _LOGGER.debug("Updated members for list: %s", list_id)
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

    async def _migrate_legacy_images_and_urls(self) -> None:
        """Move old image files and rewrite stored URLs to the new path."""
        moved_files = 0
        updated_product_urls = 0
        updated_item_urls = 0

        if self._legacy_images_dir.exists() and self._legacy_images_dir != self._images_dir:
            for src in self._legacy_images_dir.glob("*"):
                if not src.is_file():
                    continue
                dest = self._images_dir / src.name
                if dest.exists():
                    continue
                try:
                    shutil.move(str(src), str(dest))
                    moved_files += 1
                except Exception as err:
                    _LOGGER.debug("Could not move legacy image %s: %s", src, err)

        for product in self._products.values():
            image_url = product.image_url or ""
            if image_url.startswith(LEGACY_IMAGE_URL_PREFIX):
                product.image_url = image_url.replace(
                    LEGACY_IMAGE_URL_PREFIX, LOCAL_IMAGE_URL_PREFIX, 1
                )
                updated_product_urls += 1

        for items in self._items.values():
            for item in items:
                image_url = item.image_url or ""
                if image_url.startswith(LEGACY_IMAGE_URL_PREFIX):
                    item.image_url = image_url.replace(
                        LEGACY_IMAGE_URL_PREFIX, LOCAL_IMAGE_URL_PREFIX, 1
                    )
                    updated_item_urls += 1

        if updated_product_urls:
            await self._save_products()
        if updated_item_urls:
            await self._save_items()

        if moved_files or updated_product_urls or updated_item_urls:
            _LOGGER.info(
                "Migrated shopping list images to %s (moved_files=%d, updated_product_urls=%d, updated_item_urls=%d)",
                IMAGES_LOCAL_DIR,
                moved_files,
                updated_product_urls,
                updated_item_urls,
            )
    
    def get_products(self) -> List[Product]:
        """Get all products."""
        return list(self._products.values())
    
    def get_product(self, product_id: str) -> Optional[Product]:
        """Get a specific product."""
        return self._products.get(product_id)
    
    def search_products(
        self,
        query: str,
        limit: int = 10,
        exclude_allergens: Optional[List[str]] = None,
        include_tags: Optional[List[str]] = None,
        substitution_group: Optional[str] = None,
    ) -> List[Product]:
        """Search products with enhanced fuzzy matching and filters.
        
        Args:
            query: Search query
            limit: Maximum results
            exclude_allergens: Allergens to exclude
            include_tags: Tags to include
            substitution_group: Filter by substitution group
            
        Returns:
            List of matching products
        """
        if not self._search_engine:
            _LOGGER.warning("Search engine not initialized")
            return []
        
        # Convert products dict to format search engine expects
        products_dict = {pid: p.to_dict() for pid, p in self._products.items()}
        search_engine = ProductSearch(products_dict)
        
        results = search_engine.search(
            query=query,
            limit=limit,
            exclude_allergens=exclude_allergens,
            include_tags=include_tags,
            substitution_group=substitution_group,
        )
        
        # Convert back to Product objects
        return [self._products[r["id"]] for r in results if r["id"] in self._products]

    def find_product_substitutes(self, product_id: str, limit: int = 5) -> List[Product]:
        """Find substitute products.
        
        Args:
            product_id: Product to find substitutes for
            limit: Maximum substitutes
            
        Returns:
            List of substitute products
        """
        if not self._search_engine:
            return []
        
        products_dict = {pid: p.to_dict() for pid, p in self._products.items()}
        search_engine = ProductSearch(products_dict)
        
        results = search_engine.find_substitutes(product_id, limit)
        return [self._products[r["id"]] for r in results if r["id"] in self._products]
        
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
        await self._write_config_backup()
        # Rebuild search engine so the new product is immediately searchable
        products_dict = {pid: p.to_dict() for pid, p in self._products.items()}
        self._search_engine = ProductSearch(products_dict)
        _LOGGER.debug("Added product: %s", new_product.name)
        return new_product
    
    async def reload_catalog(self, country_code: str) -> int:
        """Replace catalog-sourced products with those from a new country's catalog.
        Products with source='user' are preserved."""
        catalog_ids = [
            pid for pid, p in self._products.items()
            if getattr(p, 'source', 'user') == 'catalog'
        ]
        for pid in catalog_ids:
            del self._products[pid]

        self._country = country_code
        await self._load_categories_for_country(country_code)

        catalog_products = await load_product_catalog(self._component_path, country_code)
        count = 0
        for prod_data in catalog_products:
            try:
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
                    source="catalog",
                    tags=prod_data.get("tags", []),
                    collections=prod_data.get("collections", []),
                    taxonomy=prod_data.get("taxonomy", {}),
                    allergens=prod_data.get("allergens", []),
                    substitution_group=prod_data.get("substitution_group", ""),
                    priority_level=prod_data.get("priority_level", 0),
                    image_hint=prod_data.get("image_hint", "")
                )
                self._products[product.id] = product
                count += 1
            except Exception as err:
                _LOGGER.error("Failed to import product %s: %s", prod_data.get("name"), err)

        await self._save_products()
        products_dict = {pid: p.to_dict() for pid, p in self._products.items()}
        self._search_engine = ProductSearch(products_dict)
        _LOGGER.info("Reloaded catalog for %s: %d products imported", country_code, count)
        return count

    async def delete_product(self, product_id: str) -> bool:
        """Delete a product from the catalog."""
        if product_id not in self._products:
            return False
        del self._products[product_id]
        await self._save_products()
        # Rebuild search engine so the product is no longer searchable
        products_dict = {pid: p.to_dict() for pid, p in self._products.items()}
        self._search_engine = ProductSearch(products_dict)
        _LOGGER.debug("Deleted product: %s", product_id)
        return True

    async def update_product(self, product_id: str, **kwargs) -> Optional[Product]:
        """Update a product."""
        if product_id not in self._products:
            return None

        product = self._products[product_id]
        for key, value in kwargs.items():
            if hasattr(product, key):
                setattr(product, key, value)

        await self._save_products()
        await self._write_config_backup()
        _LOGGER.debug("Updated product: %s", product_id)
        return product

    # ---------------------------------------------------------------------------
    # Backup / Restore
    # ---------------------------------------------------------------------------

    async def export_user_data(self) -> dict:
        """Return a serialisable snapshot of all user-created data."""
        user_products = [
            p.to_dict() for p in self._products.values()
            if getattr(p, "source", "user") == "user"
        ]
        lists = [lst.to_dict() for lst in self._lists.values()]
        items = {
            list_id: [item.to_dict() for item in items_list]
            for list_id, items_list in self._items.items()
        }
        return {
            "slm_backup_version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "country": self._country,
            "user_products": user_products,
            "lists": lists,
            "items": items,
        }

    async def import_user_data(self, data: dict) -> dict:
        """Merge a backup into live storage. Skips anything already present by ID."""
        imported_products = 0
        imported_lists = 0
        imported_items = 0

        for prod_data in data.get("user_products", []):
            prod_id = prod_data.get("id")
            if prod_id and prod_id not in self._products:
                try:
                    self._products[prod_id] = Product(**prod_data)
                    imported_products += 1
                except Exception as err:
                    _LOGGER.warning("Skipped product during import: %s", err)

        if imported_products:
            await self._save_products()
            products_dict = {pid: p.to_dict() for pid, p in self._products.items()}
            self._search_engine = ProductSearch(products_dict)

        for list_data in data.get("lists", []):
            list_id = list_data.get("id")
            if list_id and list_id not in self._lists:
                try:
                    lst = ShoppingList(**list_data)
                    lst.active = False
                    self._lists[list_id] = lst
                    imported_lists += 1
                except Exception as err:
                    _LOGGER.warning("Skipped list during import: %s", err)

        backup_items = data.get("items", {})
        for list_id, items_list in backup_items.items():
            if list_id in self._lists and list_id not in self._items:
                try:
                    self._items[list_id] = [Item(**d) for d in items_list]
                    imported_items += len(self._items[list_id])
                except Exception as err:
                    _LOGGER.warning("Skipped items for list %s: %s", list_id, err)

        if imported_lists or imported_items:
            await self._save_lists()
            await self._save_items()

        _LOGGER.info(
            "Import complete: %d products, %d lists, %d items",
            imported_products, imported_lists, imported_items,
        )
        return {"products": imported_products, "lists": imported_lists, "items": imported_items}

    async def _write_config_backup(self) -> None:
        """Silently write a backup JSON to the HA config directory."""
        try:
            backup_path = os.path.join(
                self.hass.config.config_dir,
                "shopping_list_manager_backup.json",
            )
            data = await self.export_user_data()

            def _write() -> None:
                with open(backup_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

            await self.hass.async_add_executor_job(_write)
            _LOGGER.debug("Auto-backup written to %s", backup_path)
        except Exception as err:
            _LOGGER.warning("Failed to write config backup: %s", err)
    
    # Categories methods
    async def _load_categories_for_country(self, country_code: str) -> None:
        """Load and persist system categories for the selected country."""
        categories = await load_categories(self._component_path, country_code)
        self._categories = [Category(**cat_data) for cat_data in categories]
        await self._save_categories()
        _LOGGER.info(
            "Loaded %d categories for country: %s",
            len(self._categories),
            country_code,
        )

    async def _save_categories(self) -> None:
        """Save categories to storage."""
        data = [cat.to_dict() for cat in self._categories]
        await self._store_categories.async_save(data)
    
    def get_categories(self) -> List[Category]:
        """Get all categories."""
        return self._categories

    # Loyalty card methods
    async def _save_loyalty_cards(self) -> None:
        """Save loyalty cards to storage."""
        data = {card_id: card.to_dict() for card_id, card in self._loyalty_cards.items()}
        await self._store_loyalty_cards.async_save(data)

    def get_loyalty_cards(self, user_id: str = None, is_admin: bool = False) -> List[LoyaltyCard]:
        """Get loyalty cards visible to the specified user.

        Global cards (owner_id=None) are visible to everyone.
        Private cards are visible to their owner, anyone in allowed_users, and admins.
        """
        all_cards = list(self._loyalty_cards.values())
        if is_admin or user_id is None:
            return all_cards
        return [
            card for card in all_cards
            if card.owner_id is None
            or card.owner_id == user_id
            or user_id in (card.allowed_users or [])
        ]

    def get_loyalty_card(self, card_id: str) -> Optional[LoyaltyCard]:
        """Get a specific loyalty card."""
        return self._loyalty_cards.get(card_id)

    async def create_loyalty_card(self, owner_id: str = None, **kwargs) -> LoyaltyCard:
        """Create a new loyalty card."""
        from .models import current_timestamp
        new_card = LoyaltyCard(
            id=generate_id(),
            owner_id=owner_id,
            **kwargs
        )
        self._loyalty_cards[new_card.id] = new_card
        await self._save_loyalty_cards()
        _LOGGER.debug("Created loyalty card: %s", new_card.name)
        return new_card

    async def update_loyalty_card(self, card_id: str, **kwargs) -> Optional[LoyaltyCard]:
        """Update a loyalty card."""
        if card_id not in self._loyalty_cards:
            return None

        card = self._loyalty_cards[card_id]
        for key, value in kwargs.items():
            if hasattr(card, key):
                setattr(card, key, value)

        from .models import current_timestamp
        card.updated_at = current_timestamp()
        await self._save_loyalty_cards()
        _LOGGER.debug("Updated loyalty card: %s", card_id)
        return card

    async def delete_loyalty_card(self, card_id: str) -> bool:
        """Delete a loyalty card."""
        if card_id not in self._loyalty_cards:
            return False

        del self._loyalty_cards[card_id]
        await self._save_loyalty_cards()
        _LOGGER.debug("Deleted loyalty card: %s", card_id)
        return True

    async def update_loyalty_card_members(self, card_id: str, allowed_users: List[str]) -> Optional[LoyaltyCard]:
        """Update the allowed_users for a private loyalty card."""
        if card_id not in self._loyalty_cards:
            return None

        card = self._loyalty_cards[card_id]
        card.allowed_users = allowed_users
        from .models import current_timestamp
        card.updated_at = current_timestamp()
        await self._save_loyalty_cards()
        _LOGGER.debug("Updated members for loyalty card: %s", card_id)
        return card

    # ==========================================================================
    # Custom Regions
    # ==========================================================================

    def get_custom_regions(self) -> Dict[str, Any]:
        """Return all custom regions as {code: {name, currency_symbol, language}}."""
        return dict(self._custom_regions)

    async def create_custom_region(
        self, code: str, name: str, currency_symbol: Optional[str] = None, language: Optional[str] = None
    ) -> bool:
        """Create a new custom region. Returns False if the code already exists."""
        if code in self._custom_regions:
            return False
        self._custom_regions[code] = {
            "name": name,
            "currency_symbol": currency_symbol,
            "language": language,
        }
        await self._save_custom_regions()
        _LOGGER.debug("Created custom region: %s (%s)", code, name)
        return True

    async def delete_custom_region(self, code: str) -> bool:
        """Delete a custom region. Returns False if not found."""
        if code not in self._custom_regions:
            return False
        del self._custom_regions[code]
        await self._save_custom_regions()
        _LOGGER.debug("Deleted custom region: %s", code)
        return True

    async def _save_custom_regions(self) -> None:
        """Persist custom regions to storage."""
        await self._store_custom_regions.async_save({"regions": self._custom_regions})
