"""Config flow for the Apollo TAB Dashboard integration."""

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class ApolloTabConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add the integration from the UI. There is nothing to configure."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm setup, then create the single config entry."""
        if user_input is None:
            return self.async_show_form(step_id="user")
        return self.async_create_entry(title="Apollo TAB Dashboard", data={})
