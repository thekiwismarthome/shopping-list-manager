"""
Shopping List Manager - Home Assistant Custom Integration
Clean-slate architecture with enforced invariants
"""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components import websocket_api as ha_websocket
from .websocket_api import websocket_create_list


from .const import DOMAIN
from .manager import ShoppingListManager
# Import websocket handler functions directly
from .websocket_api import (
    websocket_add_product,
    websocket_set_qty,
    websocket_get_products,
    websocket_get_active,
    websocket_delete_product,
    ws_get_catalogues,
    ws_get_lists,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Shopping List Manager from a config entry."""
    # Initialize the manager
    manager = ShoppingListManager(hass)
    await manager.async_load()
    
    # Store manager in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["manager"] = manager
    
    # Register WebSocket commands using Home Assistant's websocket_api
    ha_websocket.async_register_command(hass, websocket_create_list)
    ha_websocket.async_register_command(hass, websocket_add_product)
    ha_websocket.async_register_command(hass, websocket_set_qty)
    ha_websocket.async_register_command(hass, websocket_get_products)
    ha_websocket.async_register_command(hass, websocket_get_active)
    ha_websocket.async_register_command(hass, websocket_delete_product)
    ha_websocket.async_register_command(hass, ws_get_catalogues)
    ha_websocket.async_register_command(hass, ws_get_lists)
    
    _LOGGER.info("Shopping List Manager setup complete - registered 7 WebSocket commands")
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Shopping List Manager."""
    hass.data[DOMAIN].pop("manager", None)
    return True
