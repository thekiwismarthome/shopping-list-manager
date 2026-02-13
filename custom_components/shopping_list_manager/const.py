"""Constants for Shopping List Manager."""

# Domain
DOMAIN = "shopping_list_manager"

# Storage Keys
STORAGE_VERSION = 2
STORAGE_KEY_LISTS = f"{DOMAIN}.lists"
STORAGE_KEY_ITEMS = f"{DOMAIN}.items"
STORAGE_KEY_PRODUCTS = f"{DOMAIN}.products"
STORAGE_KEY_CATEGORIES = f"{DOMAIN}.categories"

# WebSocket Commands - Lists
WS_TYPE_LISTS_GET_ALL = f"{DOMAIN}/lists/get_all"
WS_TYPE_LISTS_CREATE = f"{DOMAIN}/lists/create"
WS_TYPE_LISTS_UPDATE = f"{DOMAIN}/lists/update"
WS_TYPE_LISTS_DELETE = f"{DOMAIN}/lists/delete"
WS_TYPE_LISTS_SET_ACTIVE = f"{DOMAIN}/lists/set_active"

# WebSocket Commands - Items
WS_TYPE_ITEMS_GET = f"{DOMAIN}/items/get"
WS_TYPE_ITEMS_ADD = f"{DOMAIN}/items/add"
WS_TYPE_ITEMS_UPDATE = f"{DOMAIN}/items/update"
WS_TYPE_ITEMS_CHECK = f"{DOMAIN}/items/check"
WS_TYPE_ITEMS_DELETE = f"{DOMAIN}/items/delete"
WS_TYPE_ITEMS_REORDER = f"{DOMAIN}/items/reorder"
WS_TYPE_ITEMS_BULK_CHECK = f"{DOMAIN}/items/bulk_check"
WS_TYPE_ITEMS_CLEAR_CHECKED = f"{DOMAIN}/items/clear_checked"
WS_TYPE_ITEMS_GET_TOTAL = f"{DOMAIN}/items/get_total"

# WebSocket Commands - Products
WS_TYPE_PRODUCTS_SEARCH = f"{DOMAIN}/products/search"
WS_TYPE_PRODUCTS_SUGGESTIONS = f"{DOMAIN}/products/suggestions"
WS_TYPE_PRODUCTS_ADD = f"{DOMAIN}/products/add"
WS_TYPE_PRODUCTS_UPDATE = f"{DOMAIN}/products/update"
WS_TYPE_PRODUCTS_DELETE = f"{DOMAIN}/products/delete"

# WebSocket Commands - Categories
WS_TYPE_CATEGORIES_GET_ALL = f"{DOMAIN}/categories/get_all"
WS_TYPE_CATEGORIES_REORDER = f"{DOMAIN}/categories/reorder"

# WebSocket Commands - Subscriptions
WS_TYPE_SUBSCRIBE = f"{DOMAIN}/subscribe"
WS_TYPE_UNSUBSCRIBE = f"{DOMAIN}/unsubscribe"

# WebSocket Commands - Barcode (Phase 5)
WS_TYPE_BARCODE_SCAN = f"{DOMAIN}/barcode/scan"
WS_TYPE_BARCODE_ADD = f"{DOMAIN}/barcode/add_to_list"

# WebSocket Commands - OpenFoodFacts (Phase 5)
WS_TYPE_OFF_FETCH = f"{DOMAIN}/openfoodfacts/fetch"
WS_TYPE_OFF_IMPORT = f"{DOMAIN}/openfoodfacts/import"

# Events
EVENT_ITEM_ADDED = f"{DOMAIN}_item_added"
EVENT_ITEM_UPDATED = f"{DOMAIN}_item_updated"
EVENT_ITEM_CHECKED = f"{DOMAIN}_item_checked"
EVENT_ITEM_DELETED = f"{DOMAIN}_item_deleted"
EVENT_LIST_UPDATED = f"{DOMAIN}_list_updated"
EVENT_LIST_DELETED = f"{DOMAIN}_list_deleted"

# Image Configuration
IMAGE_FORMAT = "webp"
IMAGE_SIZE = 200  # 200x200px
IMAGE_QUALITY = 85
IMAGE_MAX_SIZE_KB = 15

# Metric Units (always metric, regardless of country)
METRIC_UNITS = {
    "weight": ["kg", "g"],
    "volume": ["L", "mL"],
    "count": ["units", "pack", "loaf", "dozen", "ea", "pkt", "tray", "bottle", "can", "bunch", "pottle", "roll", "sachet", "tub", "bar"]
}

# Default quantities for common products (NZ-focused, can be country-specific later)
DEFAULT_QUANTITIES = {
    "milk": {"quantity": 2, "unit": "L"},
    "bread": {"quantity": 1, "unit": "loaf"},
    "butter": {"quantity": 500, "unit": "g"},
    "eggs": {"quantity": 12, "unit": "ea"},
    "cheese": {"quantity": 500, "unit": "g"},
    "yogurt": {"quantity": 1, "unit": "kg"},
    "flour": {"quantity": 1.5, "unit": "kg"},
    "sugar": {"quantity": 1.5, "unit": "kg"},
    "rice": {"quantity": 1, "unit": "kg"},
    "pasta": {"quantity": 500, "unit": "g"},
    "chicken breast": {"quantity": 1, "unit": "kg"},
    "beef mince": {"quantity": 500, "unit": "g"},
    "sausages": {"quantity": 500, "unit": "g"},
    "bacon": {"quantity": 500, "unit": "g"},
    "apples": {"quantity": 1, "unit": "kg"},
    "bananas": {"quantity": 1, "unit": "kg"},
    "potatoes": {"quantity": 2, "unit": "kg"},
    "onions": {"quantity": 1, "unit": "kg"},
    "carrots": {"quantity": 1, "unit": "kg"},
    "tomatoes": {"quantity": 500, "unit": "g"},
    "lettuce": {"quantity": 1, "unit": "ea"},
    "capsicum": {"quantity": 1, "unit": "ea"},
    "broccoli": {"quantity": 1, "unit": "ea"},
    "cereal": {"quantity": 1, "unit": "pack"},
    "baked beans": {"quantity": 1, "unit": "can"},
    "tuna": {"quantity": 1, "unit": "can"},
    "olive oil": {"quantity": 1, "unit": "L"},
    "coffee": {"quantity": 200, "unit": "g"},
    "tea bags": {"quantity": 100, "unit": "ea"},
    "toilet paper": {"quantity": 12, "unit": "roll"},
    "paper towels": {"quantity": 2, "unit": "roll"},
    "dishwashing liquid": {"quantity": 500, "unit": "mL"},
    "laundry powder": {"quantity": 2, "unit": "kg"}
}

# Paths
CATEGORIES_FILE = "categories.json"
PRODUCTS_CATALOG_FILE = "products_catalog.json"
IMAGES_PATH = "images/products"
