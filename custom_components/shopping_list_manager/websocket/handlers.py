"""WebSocket API handlers for Shopping List Manager."""
import logging
from typing import Any, Dict

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from ..const import DOMAIN

from ..const import (
    WS_TYPE_LISTS_GET_ALL,
    WS_TYPE_LISTS_CREATE,
    WS_TYPE_LISTS_UPDATE,
    WS_TYPE_LISTS_DELETE,
    WS_TYPE_LISTS_SET_ACTIVE,
    WS_TYPE_ITEMS_GET,
    WS_TYPE_ITEMS_ADD,
    WS_TYPE_ITEMS_UPDATE,
    WS_TYPE_ITEMS_CHECK,
    WS_TYPE_ITEMS_DELETE,
    WS_TYPE_ITEMS_REORDER,
    WS_TYPE_ITEMS_BULK_CHECK,
    WS_TYPE_ITEMS_CLEAR_CHECKED,
    WS_TYPE_ITEMS_GET_TOTAL,
    WS_TYPE_PRODUCTS_SEARCH,
    WS_TYPE_PRODUCTS_SUGGESTIONS,
    WS_TYPE_PRODUCTS_ADD,
    WS_TYPE_PRODUCTS_UPDATE,
    WS_TYPE_CATEGORIES_GET_ALL,
    EVENT_ITEM_ADDED,
    EVENT_ITEM_UPDATED,
    EVENT_ITEM_CHECKED,
    EVENT_ITEM_DELETED,
    EVENT_LIST_UPDATED,
    EVENT_LIST_DELETED,
)
from .. import get_storage

_LOGGER = logging.getLogger(__name__)


# =============================================================================
# LIST HANDLERS
# =============================================================================

@websocket_api.websocket_command({
    vol.Required("type"): "shopping_list_manager/items/increment",
    vol.Required("item_id"): str,
    vol.Required("amount"): vol.Coerce(float),
})
@websocket_api.async_response
async def websocket_increment_item(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Increment item quantity atomically."""

    storage = get_storage(hass)
    item_id = msg["item_id"]
    amount = msg["amount"]

    # Loop through all lists to find the item
    for list_id in storage.lists:
        items = storage.get_items(list_id)

        for item in items:
            if item.id == item_id:
                item.quantity += amount

                # Prevent negative quantities
                if item.quantity < 1:
                    item.quantity = 1

                await storage.async_save()

                connection.send_result(msg["id"], {
                    "item": item.to_dict()
                })
                return

    connection.send_error(msg["id"], "not_found", "Item not found")


@websocket_api.websocket_command({
    vol.Required("type"): "shopping_list_manager/products/get_by_ids",
    vol.Required("product_ids"): [str],
})
@websocket_api.async_response
async def ws_get_products_by_ids(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Return products matching given product IDs."""

    storage = get_storage(hass)
    product_ids = set(msg["product_ids"])

    # Get all products from storage
    all_products = storage.get_all_products()

    products = [
        product.to_dict()
        for product in all_products
        if product.id in product_ids
    ]

    connection.send_result(msg["id"], {"products": products})



@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_LISTS_GET_ALL,
    }
)
@callback
def websocket_get_lists(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Handle get all lists command."""
    storage = get_storage(hass)
    lists = storage.get_lists()
    
    connection.send_result(
        msg["id"],
        {
            "lists": [lst.to_dict() for lst in lists]
        }
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_LISTS_CREATE,
        vol.Required("name"): str,
        vol.Optional("icon", default="mdi:cart"): str,
    }
)
@websocket_api.async_response
async def websocket_create_list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Handle create list command."""
    storage = get_storage(hass)
    
    new_list = await storage.create_list(
        name=msg["name"],
        icon=msg.get("icon", "mdi:cart")
    )
    
    # Fire event
    hass.bus.async_fire(
        EVENT_LIST_UPDATED,
        {"list_id": new_list.id, "action": "created"}
    )
    
    connection.send_result(
        msg["id"],
        {"list": new_list.to_dict()}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_LISTS_UPDATE,
        vol.Required("list_id"): str,
        vol.Optional("name"): str,
        vol.Optional("icon"): str,
        vol.Optional("category_order"): [str],
    }
)
@websocket_api.async_response
async def websocket_update_list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Handle update list command."""
    storage = get_storage(hass)
    list_id = msg["list_id"]
    
    # Build update kwargs
    update_data = {}
    if "name" in msg:
        update_data["name"] = msg["name"]
    if "icon" in msg:
        update_data["icon"] = msg["icon"]
    if "category_order" in msg:
        update_data["category_order"] = msg["category_order"]
    
    updated_list = await storage.update_list(list_id, **update_data)
    
    if updated_list is None:
        connection.send_error(msg["id"], "not_found", "List not found")
        return
    
    # Fire event
    hass.bus.async_fire(
        EVENT_LIST_UPDATED,
        {"list_id": list_id, "action": "updated"}
    )
    
    connection.send_result(
        msg["id"],
        {"list": updated_list.to_dict()}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_LISTS_DELETE,
        vol.Required("list_id"): str,
    }
)
@websocket_api.async_response
async def websocket_delete_list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Handle delete list command."""
    storage = get_storage(hass)
    list_id = msg["list_id"]
    
    success = await storage.delete_list(list_id)
    
    if not success:
        connection.send_error(msg["id"], "not_found", "List not found")
        return
    
    # Fire event
    hass.bus.async_fire(
        EVENT_LIST_DELETED,
        {"list_id": list_id}
    )
    
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_LISTS_SET_ACTIVE,
        vol.Required("list_id"): str,
    }
)
@websocket_api.async_response
async def websocket_set_active_list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Handle set active list command."""
    storage = get_storage(hass)
    list_id = msg["list_id"]
    
    success = await storage.set_active_list(list_id)
    
    if not success:
        connection.send_error(msg["id"], "not_found", "List not found")
        return
    
    # Fire event
    hass.bus.async_fire(
        EVENT_LIST_UPDATED,
        {"list_id": list_id, "action": "set_active"}
    )
    
    connection.send_result(msg["id"], {"success": True})


# =============================================================================
# ITEM HANDLERS
# =============================================================================

@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_ITEMS_GET,
        vol.Required("list_id"): str,
    }
)
@callback
def websocket_get_items(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Handle get items command."""
    storage = get_storage(hass)
    list_id = msg["list_id"]
    
    items = storage.get_items(list_id)
    
    connection.send_result(
        msg["id"],
        {
            "items": [item.to_dict() for item in items]
        }
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_ITEMS_ADD,
        vol.Required("list_id"): str,
        vol.Required("name"): str,
        vol.Required("category_id"): str,
        vol.Optional("product_id"): str,
        vol.Optional("quantity", default=1): vol.Coerce(float),
        vol.Optional("unit", default="units"): str,
        vol.Optional("note"): str,
        vol.Optional("price"): vol.Coerce(float),
        vol.Optional("image_url"): str,
        vol.Optional("barcode"): str,
    }
)
@websocket_api.async_response
async def websocket_add_item(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Handle add item command."""
    storage = get_storage(hass)
    list_id = msg["list_id"]
    
    # Build item data
    item_data = {
        "name": msg["name"],
        "category_id": msg["category_id"],
        "quantity": msg.get("quantity", 1),
        "unit": msg.get("unit", "units"),
    }
    
    # Optional fields
    optional_fields = ["product_id", "note", "price", "image_url", "barcode"]
    for field in optional_fields:
        if field in msg:
            item_data[field] = msg[field]
    
    new_item = await storage.add_item(list_id, **item_data)
    
    if new_item is None:
        connection.send_error(msg["id"], "not_found", "List not found")
        return
    
    # Fire event
    hass.bus.async_fire(
        EVENT_ITEM_ADDED,
        {
            "list_id": list_id,
            "item_id": new_item.id,
            "item": new_item.to_dict()
        }
    )
    
    connection.send_result(
        msg["id"],
        {"item": new_item.to_dict()}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_ITEMS_UPDATE,
        vol.Required("item_id"): str,
        vol.Optional("name"): str,
        vol.Optional("quantity"): vol.Coerce(float),
        vol.Optional("unit"): str,
        vol.Optional("note"): str,
        vol.Optional("price"): vol.Coerce(float),
        vol.Optional("category_id"): str,
        vol.Optional("image_url"): str,
    }
)
@websocket_api.async_response
async def websocket_update_item(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Handle update item command."""
    storage = get_storage(hass)
    item_id = msg["item_id"]
    
    # Build update data
    update_data = {}
    update_fields = ["name", "quantity", "unit", "note", "price", "category_id", "image_url"]
    for field in update_fields:
        if field in msg:
            update_data[field] = msg[field]
    
    updated_item = await storage.update_item(item_id, **update_data)
    
    if updated_item is None:
        connection.send_error(msg["id"], "not_found", "Item not found")
        return
    
    # Fire event
    hass.bus.async_fire(
        EVENT_ITEM_UPDATED,
        {
            "list_id": updated_item.list_id,
            "item_id": item_id,
            "item": updated_item.to_dict()
        }
    )
    
    connection.send_result(
        msg["id"],
        {"item": updated_item.to_dict()}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_ITEMS_CHECK,
        vol.Required("item_id"): str,
        vol.Required("checked"): bool,
    }
)
@websocket_api.async_response
async def websocket_check_item(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Handle check/uncheck item command."""
    storage = get_storage(hass)
    item_id = msg["item_id"]
    checked = msg["checked"]
    
    updated_item = await storage.check_item(item_id, checked)
    
    if updated_item is None:
        connection.send_error(msg["id"], "not_found", "Item not found")
        return
    
    # Fire event
    hass.bus.async_fire(
        EVENT_ITEM_CHECKED,
        {
            "list_id": updated_item.list_id,
            "item_id": item_id,
            "checked": checked
        }
    )
    
    connection.send_result(
        msg["id"],
        {"item": updated_item.to_dict()}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_ITEMS_DELETE,
        vol.Required("item_id"): str,
    }
)
@websocket_api.async_response
async def websocket_delete_item(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Handle delete item command."""
    storage = get_storage(hass)
    item_id = msg["item_id"]
    
    success = await storage.delete_item(item_id)
    
    if not success:
        connection.send_error(msg["id"], "not_found", "Item not found")
        return
    
    # Fire event
    hass.bus.async_fire(
        EVENT_ITEM_DELETED,
        {"item_id": item_id}
    )
    
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_ITEMS_REORDER,
        vol.Required("list_id"): str,
        vol.Required("item_order"): [str],
    }
)
@websocket_api.async_response
async def websocket_reorder_items(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Handle reorder items command."""
    storage = get_storage(hass)
    list_id = msg["list_id"]
    item_order = msg["item_order"]
    
    updated_list = await storage.update_list(list_id, item_order=item_order)
    
    if updated_list is None:
        connection.send_error(msg["id"], "not_found", "List not found")
        return
    
    # Fire event
    hass.bus.async_fire(
        EVENT_LIST_UPDATED,
        {"list_id": list_id, "action": "reordered"}
    )
    
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_ITEMS_BULK_CHECK,
        vol.Required("item_ids"): [str],
        vol.Required("checked"): bool,
    }
)
@websocket_api.async_response
async def websocket_bulk_check_items(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Handle bulk check/uncheck items command."""
    storage = get_storage(hass)
    item_ids = msg["item_ids"]
    checked = msg["checked"]
    
    count = await storage.bulk_check_items(item_ids, checked)
    
    # Fire event
    hass.bus.async_fire(
        EVENT_ITEM_CHECKED,
        {
            "item_ids": item_ids,
            "checked": checked,
            "count": count
        }
    )
    
    connection.send_result(
        msg["id"],
        {"success": True, "count": count}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_ITEMS_CLEAR_CHECKED,
        vol.Required("list_id"): str,
    }
)
@websocket_api.async_response
async def websocket_clear_checked_items(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Handle clear checked items command."""
    storage = get_storage(hass)
    list_id = msg["list_id"]
    
    count = await storage.clear_checked_items(list_id)
    
    # Fire event
    hass.bus.async_fire(
        EVENT_ITEM_DELETED,
        {"list_id": list_id, "count": count, "action": "cleared_checked"}
    )
    
    connection.send_result(
        msg["id"],
        {"success": True, "count": count}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_ITEMS_GET_TOTAL,
        vol.Required("list_id"): str,
    }
)
@callback
def websocket_get_list_total(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Handle get list total command."""
    storage = get_storage(hass)
    list_id = msg["list_id"]
    
    total_data = storage.get_list_total(list_id)
    
    connection.send_result(msg["id"], total_data)


# =============================================================================
# PRODUCT HANDLERS
# =============================================================================

@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_PRODUCTS_SEARCH,
        vol.Required("query"): str,
        vol.Optional("limit", default=10): int,
        vol.Optional("exclude_allergens", default=None): vol.Any(None, [str]),
        vol.Optional("include_tags", default=None): vol.Any(None, [str]),
        vol.Optional("substitution_group", default=None): vol.Any(None, str),
    }
)
@callback
def websocket_search_products(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Handle search products command with enhanced filters."""
    storage = get_storage(hass)
    
    try:
        results = storage.search_products(
            query=msg["query"],
            limit=msg.get("limit", 10),
            exclude_allergens=msg.get("exclude_allergens"),
            include_tags=msg.get("include_tags"),
            substitution_group=msg.get("substitution_group"),
        )
        
        connection.send_result(
            msg["id"],
            {"products": [product.to_dict() for product in results]}
        )
    except Exception as err:
        _LOGGER.error("Error searching products: %s", err)
        connection.send_error(msg["id"], "search_failed", str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "shopping_list_manager/products/substitutes",
        vol.Required("product_id"): str,
        vol.Optional("limit", default=5): int,
    }
)
@callback
def websocket_get_product_substitutes(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Handle get product substitutes command."""
    storage = get_storage(hass)
    
    try:
        substitutes = storage.find_product_substitutes(
            product_id=msg["product_id"],
            limit=msg.get("limit", 5),
        )
        
        connection.send_result(
            msg["id"],
            {"substitutes": [product.to_dict() for product in substitutes]}
        )
    except Exception as err:
        _LOGGER.error("Error finding substitutes: %s", err)
        connection.send_error(msg["id"], "substitutes_failed", str(err))

@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_PRODUCTS_SEARCH,
        vol.Required("query"): str,
        vol.Optional("limit", default=10): int,
        vol.Optional("exclude_allergens"): [str],
        vol.Optional("include_tags"): [str],
        vol.Optional("substitution_group"): str,
    }
)
@callback
def websocket_search_products(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Handle search products command with enhanced filters."""
    storage = get_storage(hass)
    
    try:
        results = storage.search_products(
            query=msg["query"],
            limit=msg.get("limit", 10),
            exclude_allergens=msg.get("exclude_allergens"),
            include_tags=msg.get("include_tags"),
            substitution_group=msg.get("substitution_group"),
        )
        
        connection.send_result(
            msg["id"],
            {"products": [product.to_dict() for product in results]}
        )
    except Exception as err:
        _LOGGER.error("Error searching products: %s", err)
        connection.send_error(msg["id"], "search_failed", str(err))
@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_PRODUCTS_SUGGESTIONS,
        vol.Optional("limit", default=20): int,
    }
)
@callback
def websocket_get_product_suggestions(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Handle get product suggestions command."""
    storage = get_storage(hass)
    limit = msg.get("limit", 20)
    
    suggestions = storage.get_product_suggestions(limit)
    
    connection.send_result(
        msg["id"],
        {
            "products": [product.to_dict() for product in suggestions]
        }
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_PRODUCTS_ADD,
        vol.Required("name"): str,
        vol.Required("category_id"): str,
        vol.Optional("aliases"): [str],
        vol.Optional("default_unit", default="units"): str,
        vol.Optional("default_quantity", default=1): vol.Coerce(float),
        vol.Optional("price"): vol.Coerce(float),
        vol.Optional("barcode"): str,
        vol.Optional("image_url"): str,
    }
)
@websocket_api.async_response
async def websocket_add_product(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Handle add product command."""
    storage = get_storage(hass)
    
    # Build product data
    product_data = {
        "name": msg["name"],
        "category_id": msg["category_id"],
        "default_unit": msg.get("default_unit", "units"),
        "default_quantity": msg.get("default_quantity", 1),
        "custom": True,
        "source": "user"
    }
    
    # Optional fields
    optional_fields = ["aliases", "price", "barcode", "image_url"]
    for field in optional_fields:
        if field in msg:
            product_data[field] = msg[field]
    
    new_product = await storage.add_product(**product_data)
    
    connection.send_result(
        msg["id"],
        {"product": new_product.to_dict()}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_PRODUCTS_UPDATE,
        vol.Required("product_id"): str,
        vol.Optional("name"): str,
        vol.Optional("category_id"): str,
        vol.Optional("price"): vol.Coerce(float),
        vol.Optional("default_unit"): str,
        vol.Optional("default_quantity"): vol.Coerce(float),
        vol.Optional("aliases"): [str],
        vol.Optional("image_url"): str,
    }
)
@websocket_api.async_response
async def websocket_update_product(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Handle update product command."""
    storage = get_storage(hass)
    product_id = msg["product_id"]
    
    # Build update data
    update_data = {}
    update_fields = ["name", "category_id", "price", "default_unit", "default_quantity", "aliases", "image_url"]
    for field in update_fields:
        if field in msg:
            update_data[field] = msg[field]
    
    # Add price_updated timestamp if price changed
    if "price" in update_data:
        from ..models import current_timestamp
        update_data["price_updated"] = current_timestamp()
    
    updated_product = await storage.update_product(product_id, **update_data)
    
    if updated_product is None:
        connection.send_error(msg["id"], "not_found", "Product not found")
        return
    
    connection.send_result(
        msg["id"],
        {"product": updated_product.to_dict()}
    )


# =============================================================================
# CATEGORY HANDLERS
# =============================================================================

@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_CATEGORIES_GET_ALL,
    }
)
@callback
def websocket_get_categories(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Dict[str, Any],
) -> None:
    """Handle get all categories command."""
    storage = get_storage(hass)
    categories = storage.get_categories()
    
    connection.send_result(
        msg["id"],
        {
            "categories": [cat.to_dict() for cat in categories]
        }
    )
