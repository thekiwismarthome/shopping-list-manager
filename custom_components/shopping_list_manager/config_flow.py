"""Config flow for Shopping List Manager."""
from homeassistant import config_entries

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
            return self.async_create_entry(
                title="Shopping List Manager",
                data={}
            )

        # Show simple form
        return self.async_show_form(step_id="user")