"""
Shopping List Manager - Home Assistant Custom Integration
Clean-slate architecture with enforced invariants
"""
import logging
from pathlib import Path
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components import websocket_api

from .const import DOMAIN
from .manager import ShoppingListManager

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Shopping List Manager component."""
    # Register frontend path for the card (updated for HA 2023+)
    frontend_path = Path(__file__).parent / "frontend"
    hass.http.async_register_static_paths(
        [
            {
                "url_path": f"/hacsfiles/{DOMAIN}",
                "path": str(frontend_path),
                "cache_headers": False,
            }
        ]
    )
    _LOGGER.info(f"Registered frontend path: /hacsfiles/{DOMAIN}")
    
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Shopping List Manager from a config entry."""
    # Initialize the manager
    manager = ShoppingListManager(hass)
    await manager.async_load()
    
    # Store manager in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["manager"] = manager
    
    # Register WebSocket commands
    from .websocket_api import (
        websocket_add_product,
        websocket_set_qty,
        websocket_get_products,
        websocket_get_active,
        websocket_delete_product,
    )
    
    websocket_api.async_register_command(hass, websocket_add_product)
    websocket_api.async_register_command(hass, websocket_set_qty)
    websocket_api.async_register_command(hass, websocket_get_products)
    websocket_api.async_register_command(hass, websocket_get_active)
    websocket_api.async_register_command(hass, websocket_delete_product)
    
    _LOGGER.info("Shopping List Manager setup complete - registered 5 WebSocket commands")
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Shopping List Manager."""
    hass.data[DOMAIN].pop("manager", None)
    return True
