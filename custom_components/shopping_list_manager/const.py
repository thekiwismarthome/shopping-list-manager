"""Constants for Shopping List Manager."""

DOMAIN = "shopping_list_manager"

# Storage keys
STORAGE_VERSION = 1
STORAGE_KEY_PRODUCTS = f"{DOMAIN}.products"
STORAGE_KEY_ACTIVE = f"{DOMAIN}.active_list"

# Events
EVENT_SHOPPING_LIST_UPDATED = f"{DOMAIN}_updated"
