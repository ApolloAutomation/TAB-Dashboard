"""Tests for the config flow."""

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.apollo_tab.const import DOMAIN


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    """The user confirms an empty form and gets one config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Apollo TAB Dashboard"
    assert result["data"] == {}
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_second_flow_is_aborted(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Only one config entry is allowed."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
