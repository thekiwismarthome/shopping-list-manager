"""WebSocket API for Shopping List Manager."""
import logging
import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .models import InvariantError

_LOGGER = logging.getLogger(__name__)


@websocket_api.websocket_command({
    vol.Required("type"): "shopping_list_manager/add_product",
    vol.Optional("list_id", default="groceries"): str,
    vol.Required("key"): str,
    vol.Required("name"): str,
    vol.Optional("category", default="other"): str,
    vol.Optional("unit", default="pcs"): str,
    vol.Optional("image", default=""): str,
})
@websocket_api.async_response
async def websocket_add_product(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """
    Add or update a product in the catalog.
    
    Does NOT modify quantity - use set_qty for that.
    
    Request:
        {
            "type": "shopping_list_manager/add_product",
            "list_id": "groceries",  # optional, defaults to "groceries"
            "key": "milk",
            "name": "Milk",
            "category": "dairy",
            "unit": "pcs",
            "image": ""
        }
    
    Response:
        {
            "success": true,
            "result": {
                "key": "milk",
                "name": "Milk",
                "category": "dairy",
                "unit": "pcs",
                "image": ""
            }
        }
    """
    manager = hass.data[DOMAIN]["manager"]
    list_id = msg.get("list_id", "groceries")
    
    try:
        product = await manager.async_add_product(
            list_id=list_id,
            key=msg["key"],
            name=msg["name"],
            category=msg.get("category", "other"),
            unit=msg.get("unit", "pcs"),
            image=msg.get("image", "")
        )
        
        connection.send_result(msg["id"], product.to_dict())
        
    except Exception as err:
        _LOGGER.error("Error adding product to list '%s': %s", list_id, err)
        connection.send_error(msg["id"], "add_product_failed", str(err))


@websocket_api.websocket_command({
    vol.Required("type"): "shopping_list_manager/set_qty",
    vol.Optional("list_id", default="groceries"): str,
    vol.Required("key"): str,
    vol.Required("qty"): vol.All(int, vol.Range(min=0)),
})
@websocket_api.async_response
async def websocket_set_qty(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """
    Set quantity for a product on the shopping list.
    
    Product MUST exist in catalog first.
    qty = 0 removes from list.
    qty > 0 adds/updates on list.
    
    Request:
        {
            "type": "shopping_list_manager/set_qty",
            "list_id": "groceries",  # optional, defaults to "groceries"
            "key": "milk",
            "qty": 2
        }
    
    Response:
        {
            "success": true
        }
    
    Error (if product doesn't exist):
        {
            "success": false,
            "error": {
                "code": "invariant_violation",
                "message": "Cannot set quantity for unknown product 'milk'..."
            }
        }
    """
    manager = hass.data[DOMAIN]["manager"]
    list_id = msg.get("list_id", "groceries")
    
    try:
        await manager.async_set_qty(
            list_id=list_id,
            key=msg["key"],
            qty=msg["qty"]
        )
        
        connection.send_result(msg["id"], {"success": True})
        
    except InvariantError as err:
        # This is expected if frontend tries to set qty for non-existent product
        _LOGGER.warning("Invariant violation in set_qty (list '%s'): %s", list_id, err)
        connection.send_error(msg["id"], "invariant_violation", str(err))
        
    except Exception as err:
        _LOGGER.error("Error setting quantity in list '%s': %s", list_id, err)
        connection.send_error(msg["id"], "set_qty_failed", str(err))


@websocket_api.websocket_command({
    vol.Required("type"): "shopping_list_manager/get_products",
    vol.Optional("list_id", default="groceries"): str,
})
@websocket_api.async_response
async def websocket_get_products(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """
    Get all products in the catalog.
    
    Request:
        {
            "type": "shopping_list_manager/get_products",
            "list_id": "groceries"  # optional, defaults to "groceries"
        }
    
    Response:
        {
            "milk": {
                "key": "milk",
                "name": "Milk",
                "category": "dairy",
                "unit": "pcs",
                "image": ""
            },
            ...
        }
    """
    manager = hass.data[DOMAIN]["manager"]
    list_id = msg.get("list_id", "groceries")
    
    try:
        products = await manager.async_get_products(list_id=list_id)
        connection.send_result(msg["id"], products)
        
    except Exception as err:
        _LOGGER.error("Error getting products for list '%s': %s", list_id, err)
        connection.send_error(msg["id"], "get_products_failed", str(err))


@websocket_api.websocket_command({
    vol.Required("type"): "shopping_list_manager/get_active",
    vol.Optional("list_id", default="groceries"): str,
})
@websocket_api.async_response
async def websocket_get_active(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """
    Get active shopping list (quantities only).
    
    Request:
        {
            "type": "shopping_list_manager/get_active",
            "list_id": "groceries"  # optional, defaults to "groceries"
        }
    
    Response:
        {
            "milk": {"qty": 2},
            "bread": {"qty": 1},
            ...
        }
    """
    manager = hass.data[DOMAIN]["manager"]
    list_id = msg.get("list_id", "groceries")
    
    try:
        active = await manager.async_get_active(list_id=list_id)
        connection.send_result(msg["id"], active)
        
    except Exception as err:
        _LOGGER.error("Error getting active list for '%s': %s", list_id, err)
        connection.send_error(msg["id"], "get_active_failed", str(err))


@websocket_api.websocket_command({
    vol.Required("type"): "shopping_list_manager/delete_product",
    vol.Optional("list_id", default="groceries"): str,
    vol.Required("key"): str,
})
@websocket_api.async_response
async def websocket_delete_product(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """
    Delete a product from catalog (and remove from active list).
    
    Request:
        {
            "type": "shopping_list_manager/delete_product",
            "list_id": "groceries",  # optional, defaults to "groceries"
            "key": "milk"
        }
    
    Response:
        {
            "success": true
        }
    """
    manager = hass.data[DOMAIN]["manager"]
    list_id = msg.get("list_id", "groceries")
    
    try:
        await manager.async_delete_product(list_id=list_id, key=msg["key"])
        connection.send_result(msg["id"], {"success": True})
        
    except Exception as err:
        _LOGGER.error("Error deleting product from list '%s': %s", list_id, err)
        connection.send_error(msg["id"], "delete_product_failed", str(err))