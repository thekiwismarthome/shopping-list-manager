# Shopping List Manager

A custom Home Assistant integration that provides an enhanced shopping list experience, including a companion Lovelace card for managing items directly from your dashboard.

---

## Features

- 📋 Manage shopping list items from Home Assistant
- 🔌 WebSocket-based backend (no polling entities)
- 🖥️ Custom Lovelace card
- ⚙️ UI-based configuration (Config Flow)
- 🚀 Compatible with Home Assistant **2024.8+**

---

## 1. Installation (HACS)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](
https://my.home-assistant.io/redirect/hacs_repository/?owner=thekiwismarthome&repository=shopping-list-manager&category=integration
)

Click the button above **or** follow the manual steps below.

1. Open **HACS**
2. Go to **Integrations**
3. Click **⋮ → Custom repositories**
4. Add this repository:
   - **Repository:** `https://github.com/thekiwismarthome/shopping-list-manager`
   - **Category:** Integration
5. Install **Shopping List Manager**
6. **Restart Home Assistant**

---

## 2. Install the Lovelace Card Resource (Required)

The Lovelace card JavaScript file is included with the integration, but **must be copied manually** to the `www` directory so Home Assistant can load it.

### Step 1: Copy the card file

Run the following command (via SSH, Terminal add-on, or container shell):

```bash
mkdir -p /config/www/community/shopping_list_card && \
cp /config/custom_components/shopping_list_manager/frontend/shopping_list_card.js \
   /config/www/community/shopping_list_card/shopping_list_card.js
```

---

### Step 2: Add the resource to Home Assistant

1. Go to **Settings → Dashboards**
2. Click **⋮ (top right) → Resources**
3. Click **Add Resource**
4. Enter:

```text
URL: /local/community/shopping_list_card/shopping_list_card.js
Type: JavaScript Module
```

5. Click **Create**
6. Refresh your browser (**Ctrl + F5**)

---

## 3. Add the Integration

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](
https://my.home-assistant.io/redirect/config_flow_start/?domain=shopping_list_manager
)

Click the button above **or** add it manually:

1. Go to **Settings → Devices & Services**
2. Click **Add Integration**
3. Search for **Shopping List Manager**
4. Follow the setup steps

No YAML configuration is required.

---

## 4. Add the Card to a Dashboard

Add a **Manual** card to your dashboard and use the following YAML:

```yaml
type: custom:shopping-list-card
title: Shopping List
list_id: groceries
```

Use the **⚙️ cog button** in the card to configure additional settings.

---

## Updating

- HACS updates will update the **integration**
- If the Lovelace card JavaScript changes in a future release, you must **repeat the copy command** above

This is expected behavior for single-repository integrations.

---

## Compatibility Notes

- Designed for **Home Assistant 2024.8+**
- Uses WebSocket APIs
- Fully compatible with the **Services → Actions** change introduced in Home Assistant 2024.8

---

## Troubleshooting

If the card does not load:

1. Ensure Home Assistant was restarted after installation
2. Verify the file exists at:

```
/config/www/community/shopping_list_card/shopping_list_card.js
```

3. Confirm the resource URL is correct
4. Perform a hard browser refresh (**Ctrl + F5**)

---

## License

MIT License
