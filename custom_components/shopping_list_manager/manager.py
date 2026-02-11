"""Core Shopping List Manager with invariant enforcement."""
import asyncio
import logging
from typing import Dict, Optional, List

from homeassistant.core import HomeAssistant
from homeassistant.helpers import storage
from homeassistant.helpers.storage import Store


from .const import (
    DOMAIN,
    EVENT_SHOPPING_LIST_UPDATED,
    STORAGE_KEY_ACTIVE,
    STORAGE_KEY_PRODUCTS,
    STORAGE_VERSION,
)
from .models import Product, ActiveItem, InvariantError, validate_invariant

_LOGGER = logging.getLogger(__name__)


class ShoppingListManager:
    """
    Manages multiple independent shopping lists.
    
    Each list_id gets its own pair of storage files:
    - shopping_list_manager.{list_id}.products
    - shopping_list_manager.{list_id}.active_list
    
    The default "groceries" list uses the original flat keys for backward compat:
    - shopping_list_manager.products → groceries products
    - shopping_list_manager.active_list → groceries active
    
    Architecture principles:
    1. Products and active_list are separate concerns per list
    2. Products are authoritative, persistent data
    3. Active list is ephemeral state
    4. Invariant (active ⊆ products) enforced on every mutation
    5. Lock ensures atomic operations per list
    """
    
    def __init__(self, hass: HomeAssistant):
        """Initialize the manager."""
        self.hass = hass
        # Per-list in-memory caches: list_id -> {key: Product}
        self._products: Dict[str, Dict[str, Product]] = {}
        self._active_list: Dict[str, Dict[str, ActiveItem]] = {}
        # Per-list locks
        self._locks: Dict[str, asyncio.Lock] = {}
        # Per-list storage Store instances (created lazily, except groceries)
        self._store_products: Dict[str, storage.Store] = {}
        self._store_active: Dict[str, storage.Store] = {}
        
        # Pre-create stores for the default "groceries" list using the original flat keys
        # for backward compatibility — existing data just works
        self._store_products["groceries"] = storage.Store(
            hass, STORAGE_VERSION, STORAGE_KEY_PRODUCTS  # "shopping_list_manager.products"
        )
        self._store_active["groceries"] = storage.Store(
            hass, STORAGE_VERSION, STORAGE_KEY_ACTIVE    # "shopping_list_manager.active_list"
        )
        # --- Catalogue + list metadata (NEW, additive) ---
        self._store_catalogues = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.catalogues",
        )
        self._catalogues: Dict[str, dict] = {}

        self._store_lists = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.lists",
        )
        self._lists: Dict[str, dict] = {}

    def _lock_for(self, list_id: str) -> asyncio.Lock:
        """Get or create lock for a list."""
        if list_id not in self._locks:
            self._locks[list_id] = asyncio.Lock()
        return self._locks[list_id]
    
    def _store_products_for(self, list_id: str) -> storage.Store:
        """Get or create products Store for a list."""
        if list_id not in self._store_products:
            catalogue_id = self._lists.get(list_id, {}).get("catalogue", list_id)
            catalogue = self._catalogues.get(catalogue_id)

            key = (
                catalogue["products_store"]
                if catalogue
                else f"{DOMAIN}.{list_id}.products"
            )

            self._store_products[list_id] = storage.Store(
                self.hass, STORAGE_VERSION, key
            )
        return self._store_products[list_id]

    
    def _store_active_for(self, list_id: str) -> storage.Store:
        """Get or create active Store for a list."""
        if list_id not in self._store_active:
            key = f"{DOMAIN}.{list_id}.active_list"
            self._store_active[list_id] = storage.Store(self.hass, STORAGE_VERSION, key)
        return self._store_active[list_id]
    
    async def _ensure_loaded(self, list_id: str) -> None:
        """Lazily load a list from storage if not yet in memory."""
        await self._ensure_catalogues_loaded()
        await self._ensure_lists_loaded()
        
        # Register list if it does not exist yet
        if list_id not in self._lists:
            self._lists[list_id] = {
                "catalogue": list_id
            }
            await self._store_lists.async_save(self._lists)


        if list_id in self._products:
            return  # already loaded
        
        products_data = await self._store_products_for(list_id).async_load()
        self._products[list_id] = {
            key: Product.from_dict(data) for key, data in (products_data or {}).items()
        }
        
        active_data = await self._store_active_for(list_id).async_load()
        self._active_list[list_id] = {
            key: ActiveItem.from_dict(data) for key, data in (active_data or {}).items()
        }
        
        # Repair any orphaned active items
        await self._async_repair_invariant(list_id)
        
        _LOGGER.info(
            "Loaded list '%s': %d products, %d active",
            list_id, len(self._products[list_id]), len(self._active_list[list_id])
        )
    
    async def _ensure_catalogues_loaded(self) -> None:
        data = await self._store_catalogues.async_load()
        if isinstance(data, dict):
            self._catalogues = data
            return

        # Bootstrap from existing behavior (no changes)
        self._catalogues = {
            "groceries": {
                "name": "Groceries",
                "icon": "🛒",
                "products_store": f"{DOMAIN}.products",
            }
        }

        await self._store_catalogues.async_save(self._catalogues)

    async def _ensure_lists_loaded(self) -> None:
        data = await self._store_lists.async_load()
        if isinstance(data, dict):
            import time

            # Migration: ensure new metadata fields exist
            for list_id, meta in data.items():
                if "owner" not in meta:
                    meta["owner"] = "system"
                if "visibility" not in meta:
                    meta["visibility"] = "shared"
                if "created_at" not in meta:
                    meta["created_at"] = time.time()
                if "updated_at" not in meta:
                    meta["updated_at"] = time.time()

            self._lists = data
            await self._store_lists.async_save(self._lists)
            return


        # Default: list_id == catalogue_id (current behavior)
        import time

        self._lists = {
            "groceries": {
                "catalogue": "groceries",
                "owner": "system",
                "visibility": "shared",
                "created_at": time.time(),
                "updated_at": time.time(),
            }
        }

        await self._store_lists.async_save(self._lists)

    async def async_load(self) -> None:
        """Pre-load the default groceries list for backward compat."""
        async with self._lock_for("groceries"):
            await self._ensure_loaded("groceries")
    
    async def _async_repair_invariant(self, list_id: str) -> None:
        """Remove active items whose product no longer exists."""
        orphaned = [k for k in self._active_list[list_id] if k not in self._products[list_id]]
        if orphaned:
            _LOGGER.warning(
                "List '%s': removing %d orphaned active items: %s",
                list_id, len(orphaned), orphaned
            )
            for k in orphaned:
                del self._active_list[list_id][k]
            await self._async_save_active(list_id)
    
    async def _async_save_products(self, list_id: str) -> None:
        """Persist products to storage."""
        data = {key: p.to_dict() for key, p in self._products[list_id].items()}
        await self._store_products_for(list_id).async_save(data)
    
    async def _async_save_active(self, list_id: str) -> None:
        """Persist active list to storage."""
        data = {key: a.to_dict() for key, a in self._active_list[list_id].items()}
        await self._store_active_for(list_id).async_save(data)
    
    def _fire_update_event(self) -> None:
        """Fire event to notify listeners of changes."""
        self.hass.bus.async_fire(EVENT_SHOPPING_LIST_UPDATED)
    
    # ========================================================================
    # PUBLIC API - All operations enforce invariants
    # ========================================================================
    
    async def async_add_product(
        self,
        list_id: str,
        key: str,
        name: str,
        category: str = "other",
        unit: str = "pcs",
        image: str = ""
    ) -> Product:
        """
        Add or update a product in a list's catalog.
        
        This operation:
        - Creates/updates product metadata
        - Does NOT modify quantities
        - Is idempotent
        - Persists to storage
        
        Args:
            list_id: List identifier
            key: Unique product identifier
            name: Display name
            category: Product category
            unit: Unit of measurement
            image: Image URL
            
        Returns:
            The created/updated Product
        """
        async with self._lock_for(list_id):
            await self._ensure_loaded(list_id)
            
            product = Product(
                key=key,
                name=name,
                category=category,
                unit=unit,
                image=image
            )
            
            self._products[list_id][key] = product
            await self._async_save_products(list_id)
            
            _LOGGER.debug("List '%s': added/updated product %s (%s)", list_id, name, key)
            self._fire_update_event()
            
            return product
    
    async def async_set_qty(self, list_id: str, key: str, qty: int) -> None:
        """
        Set quantity for a product on the shopping list.
        
        This operation:
        - REQUIRES product to exist (enforces invariant)
        - qty > 0: adds/updates active_list
        - qty == 0: removes from active_list
        - Persists state
        - Fires update event
        
        Args:
            list_id: List identifier
            key: Product key (must exist in catalog)
            qty: New quantity (0 to remove, >0 to add/update)
            
        Raises:
            InvariantError: If product doesn't exist
            ValueError: If qty is negative
        """
        if qty < 0:
            raise ValueError(f"Quantity cannot be negative: {qty}")
        
        async with self._lock_for(list_id):
            await self._ensure_loaded(list_id)
            
            # INVARIANT ENFORCEMENT: Product must exist
            if key not in self._products[list_id]:
                raise InvariantError(
                    f"Cannot set quantity for unknown product '{key}' in list '{list_id}'. "
                    f"Product must be created first with add_product."
                )
            
            # Update or remove from active list
            if qty > 0:
                self._active_list[list_id][key] = ActiveItem(qty=qty)
                _LOGGER.debug("List '%s': set qty for %s: %d", list_id, key, qty)
            else:
                # qty == 0: remove from list
                if key in self._active_list[list_id]:
                    del self._active_list[list_id][key]
                    _LOGGER.debug("List '%s': removed %s from active list", list_id, key)
            
            await self._async_save_active(list_id)
            self._fire_update_event()
    
    async def async_delete_product(self, list_id: str, key: str) -> None:
        """
        Delete a product from the catalog.
        
        This operation:
        - Removes product from catalog
        - Removes from active list (maintains invariant)
        - Persists both changes
        
        Args:
            list_id: List identifier
            key: Product key to delete
        """
        async with self._lock_for(list_id):
            await self._ensure_loaded(list_id)
            
            if key not in self._products[list_id]:
                _LOGGER.warning("List '%s': attempted to delete non-existent product: %s", list_id, key)
                return
            
            # Remove from catalog
            del self._products[list_id][key]
            
            # Remove from active list (maintain invariant)
            if key in self._active_list[list_id]:
                del self._active_list[list_id][key]
            
            await self._async_save_products(list_id)
            await self._async_save_active(list_id)
            
            _LOGGER.debug("List '%s': deleted product: %s", list_id, key)
            self._fire_update_event()
    
    def get_catalogues(self) -> Dict[str, dict]:
        return self._catalogues
    
    def get_visible_lists(self, user):
        if user.is_admin:
            return self._lists

        return {
            lid: meta
            for lid, meta in self._lists.items()
            if meta.get("visibility") == "shared"
            or meta.get("owner") == user.id
        }

    async def async_get_lists(self) -> Dict[str, dict]:
        await self._ensure_catalogues_loaded()
        await self._ensure_lists_loaded()
        return self._lists


    async def async_get_products(self, list_id: str) -> Dict[str, dict]:
        """
        Get all products in a list's catalog.
        
        Args:
            list_id: List identifier
        
        Returns:
            Dictionary of product key -> product data
        """
        async with self._lock_for(list_id):
            await self._ensure_loaded(list_id)
            return {key: product.to_dict() for key, product in self._products[list_id].items()}
    
    async def async_get_active(self, list_id: str) -> Dict[str, dict]:
        """
        Get active shopping list (quantities only).
        
        Args:
            list_id: List identifier
        
        Returns:
            Dictionary of product key -> active item data (qty only)
        """
        async with self._lock_for(list_id):
            await self._ensure_loaded(list_id)
            return {key: item.to_dict() for key, item in self._active_list[list_id].items()}
    
    # NOTE: The following methods were removed as they're not used by the websocket API
    # and would need updating to support per-list structure:
    # - async_get_full_state()
    # - get_product()
    # - get_active_qty()
