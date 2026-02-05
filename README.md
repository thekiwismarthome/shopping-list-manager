## Installation

### 1. Install via HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=thekiwismarthome&repository=shopping-list-manager&category=integration)

Click the button above or manually add the custom repository in HACS.
Restart HA

### 2. Add the Card Resource

After installing via HACS, add the frontend resource:

1. Go to Settings → Dashboards
2. Click ⋮ (three dots, top right) → Resources
3. Click "+ Add Resource"
4. URL: `/hacsfiles/shopping-list-manager/shopping_list_card.js`
5. Resource type: JavaScript Module
6. Click "Create"

### 3. Add the Integration

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=shopping_list_manager)

Click the button above or manually add via Settings → Devices & Services.

### 4. Add Card to Dashboard
```yaml
type: custom:shopping-list-card
title: Shopping List
list_id: groceries
```


Use the ⚙️ cog button in the card to configure settings.
