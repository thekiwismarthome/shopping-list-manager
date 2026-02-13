"""Config flow for Shopping List Manager."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN


class ShoppingListManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Shopping List Manager."""

    VERSION = 1

    def __init__(self):
        """Initialize config flow."""
        self._data = {}

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        # Only allow one instance
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        
        if user_input is not None:
            # Store country and initial list name
            self._data["country"] = user_input.get("country", "NZ")
            self._data["initial_list_name"] = user_input.get("list_name", "Shopping List")
            return await self.async_step_features()

        # Show setup form with country selection
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("country", default="NZ"): vol.In({
                    "NZ": "New Zealand",
                    "AU": "Australia",
                    "US": "United States",
                    "GB": "United Kingdom",
                    "CA": "Canada",
                }),
                vol.Optional("list_name", default="Shopping List"): str,
            }),
            description_placeholders={
                "version": "2.0.0",
            }
        )

    async def async_step_features(self, user_input=None):
        """Configure optional features."""
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(
                title="Shopping List Manager",
                data=self._data
            )

        return self.async_show_form(
            step_id="features",
            data_schema=vol.Schema({
                vol.Optional("enable_price_tracking", default=True): bool,
                vol.Optional("enable_image_search", default=True): bool,
                vol.Optional("metric_units_only", default=True): bool,
            }),
            description_placeholders={
                "features": "Configure optional features for your shopping lists"
            }
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Shopping List Manager."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    "country",
                    default=self.config_entry.data.get("country", "NZ")
                ): vol.In({
                    "NZ": "New Zealand",
                    "AU": "Australia",
                    "US": "United States",
                    "GB": "United Kingdom",
                    "CA": "Canada",
                }),
                vol.Optional(
                    "enable_price_tracking",
                    default=self.config_entry.data.get("enable_price_tracking", True)
                ): bool,
                vol.Optional(
                    "enable_image_search",
                    default=self.config_entry.data.get("enable_image_search", True)
                ): bool,
            })
        )
