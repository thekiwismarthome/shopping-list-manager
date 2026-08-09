"""Shopping List Manager integration for Home Assistant."""
import json
import logging
import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, EVENT_ITEM_ADDED, EVENT_ITEM_UPDATED, EVENT_ITEM_CHECKED, EVENT_ITEM_DELETED, EVENT_LIST_UPDATED, EVENT_LIST_DELETED
from .storage import ShoppingListStorage
from .utils.images import ImageHandler

_LOGGER = logging.getLogger(__name__)

# Track storage instance globally
DATA_STORAGE = f"{DOMAIN}_storage"


def _load_manifest_version(component_path: str) -> str:
    """Load the integration version from manifest.json."""
    with open(os.path.join(component_path, "manifest.json"), encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)

    return manifest.get("version", "unknown")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Shopping List Manager component from yaml (not used)."""
    # This integration doesn't support YAML configuration
    # All setup is done via config entries (UI configuration)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Shopping List Manager from a config entry."""
    _LOGGER.info("Setting up Shopping List Manager")

    # Get component path for loading data files
    component_path = os.path.dirname(__file__)
    config_path = hass.config.path()

    # Get country from options (or fall back to data, or default to NZ)
    country = entry.options.get("country") or entry.data.get("country", "NZ")
    _LOGGER.info("Using country: %s", country)

    # Initialize storage with country
    storage = ShoppingListStorage(hass, component_path, country)
    await storage.async_load()

    # Initialize image handler
    image_handler = ImageHandler(hass, config_path)

    # Read installed version from manifest
    version = await hass.async_add_executor_job(_load_manifest_version, component_path)

    # Store instances in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][DATA_STORAGE] = storage
    hass.data[DOMAIN]["image_handler"] = image_handler
    hass.data[DOMAIN]["country"] = country
    hass.data[DOMAIN]["version"] = version
    
    # Register update listener for options changes
    entry.async_on_unload(entry.add_update_listener(update_listener))
    
    # Register WebSocket commands
    await _async_register_websocket_handlers(hass, storage)
    
    # Register frontend resources
    await _async_register_frontend(hass)
    
    # CRITICAL: Register event listeners so non-admin users can subscribe
    # Without these, non-admin users cannot receive real-time updates
    def _dummy_listener(event):
        """Dummy listener to enable event subscription for all users."""
        pass
    
    hass.bus.async_listen(EVENT_ITEM_ADDED, _dummy_listener)
    hass.bus.async_listen(EVENT_ITEM_UPDATED, _dummy_listener)
    hass.bus.async_listen(EVENT_ITEM_CHECKED, _dummy_listener)
    hass.bus.async_listen(EVENT_ITEM_DELETED, _dummy_listener)
    hass.bus.async_listen(EVENT_LIST_UPDATED, _dummy_listener)
    hass.bus.async_listen(EVENT_LIST_DELETED, _dummy_listener)
    
    _LOGGER.info("Shopping List Manager setup complete with event subscriptions enabled")
    
    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    # Reload the integration when options change
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Shopping List Manager")
    
    # Clean up hass.data
    if DOMAIN in hass.data:
        hass.data[DOMAIN].pop(DATA_STORAGE, None)
    
    return True


async def _async_register_websocket_handlers(
    hass: HomeAssistant, 
    storage: ShoppingListStorage
) -> None:
    """Register WebSocket API handlers."""
    from homeassistant.components import websocket_api
    from .websocket import handlers
    
    # Lists handlers
    websocket_api.async_register_command(
        hass,
        handlers.websocket_subscribe,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_get_lists,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_create_list,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_update_list,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_delete_list,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_set_active_list,
    )
    
    # Items handlers
    websocket_api.async_register_command(
        hass,
        handlers.websocket_get_items,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_add_item,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_update_item,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_check_item,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_increment_item,
    )

    websocket_api.async_register_command(
        hass,
        handlers.websocket_delete_item,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_reorder_items,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_bulk_check_items,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_clear_checked_items,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_get_list_total,
    )
    
    # Products handlers
    websocket_api.async_register_command(
        hass,
        handlers.websocket_download_product_image,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_search_by_barcode,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_search_products,
    )
    websocket_api.async_register_command(
        hass,
        handlers.ws_get_products_by_ids,
    )

    websocket_api.async_register_command(
        hass,
        handlers.websocket_get_product_suggestions,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_add_product,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_update_product,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_delete_product,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_get_product_substitutes,
    )
    
    # OpenFoodFacts proxy
    websocket_api.async_register_command(
        hass,
        handlers.websocket_off_fetch,
    )

    # Categories handlers
    websocket_api.async_register_command(
        hass,
        handlers.websocket_get_categories,
    )

    # Integration settings handlers
    websocket_api.async_register_command(
        hass,
        handlers.websocket_get_integration_settings,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_set_country,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_create_custom_region,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_delete_custom_region,
    )

    # Backup / Restore handlers
    websocket_api.async_register_command(
        hass,
        handlers.websocket_export_data,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_import_data,
    )

    # List members handler
    websocket_api.async_register_command(
        hass,
        handlers.websocket_update_list_members,
    )

    # HA users handler
    websocket_api.async_register_command(
        hass,
        handlers.websocket_get_ha_users,
    )

    # Loyalty card handlers
    websocket_api.async_register_command(
        hass,
        handlers.websocket_get_loyalty_cards,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_add_loyalty_card,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_update_loyalty_card,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_delete_loyalty_card,
    )
    websocket_api.async_register_command(
        hass,
        handlers.websocket_update_loyalty_card_members,
    )

    _LOGGER.debug("WebSocket handlers registered")


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Register frontend resources."""
    # Since frontend is a separate HACS module, we don't need to register it here
    # The frontend card registers itself independently
    _LOGGER.debug("Frontend resources skipped (separate HACS module)")


def get_storage(hass: HomeAssistant) -> ShoppingListStorage:
    """Get the storage instance from hass.data.
    
    Helper function for WebSocket handlers to access storage.
    """
    return hass.data[DOMAIN][DATA_STORAGE]
