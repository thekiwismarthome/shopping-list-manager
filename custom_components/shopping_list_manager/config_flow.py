"""Config flow for Shopping List Manager."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN


class ShoppingListManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Shopping List Manager."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        # Only allow one instance
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        
        if user_input is not None:
            # Create entry with default country
            return self.async_create_entry(
                title="Shopping List Manager",
                data={"country": "NZ"},
                options={
                    "country": "NZ",
                    "enable_price_tracking": True,
                    "enable_image_search": True,
                    "metric_units_only": True,
                }
            )

        # Show simple setup form
        return self.async_show_form(
            step_id="user",
            description_placeholders={
                "info": "Country and other settings can be configured after setup via the Configure button."
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
            # Update options
            return self.async_create_entry(title="", data=user_input)

        # Get current settings
        current_country = self.config_entry.options.get(
            "country", 
            self.config_entry.data.get("country", "NZ")
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("country", default=current_country): vol.In({
                    "NZ": "New Zealand",
                    "AU": "Australia",
                    "US": "United States",
                    "GB": "United Kingdom",
                    "CA": "Canada",
                }),
                vol.Optional(
                    "enable_price_tracking",
                    default=self.config_entry.options.get("enable_price_tracking", True)
                ): bool,
                vol.Optional(
                    "enable_image_search",
                    default=self.config_entry.options.get("enable_image_search", True)
                ): bool,
                vol.Optional(
                    "metric_units_only",
                    default=self.config_entry.options.get("metric_units_only", True)
                ): bool,
            }),
            description_placeholders={
                "info": "Changing country will reload the product catalog on next restart."
            }
        )
