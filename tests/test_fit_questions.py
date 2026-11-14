"""The fit of a layout v2 counts the cover questions (C.4; decision 5, I13).

The sender writes a question into the device layout for every widget or
card that moves a garage, gate or door cover. The converter's fit to the
tablet's limits must count those bytes, or a layout it calls fitting is
refused as too big when the sender compiles it.
"""

from __future__ import annotations

import copy

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.apollo_tab import live
from custom_components.apollo_tab.maker import convert, device
from custom_components.apollo_tab.maker.device import ContractError

from .conftest import SaveTabDashboard, setup_integration
from .test_maker_convert2 import ICONS, _codes, _convert, _two_lamps
from .test_tablet_input import tab_config

QUESTION = "Open the large garage door at the back of the house?"


def _questions(bindings: dict) -> dict[int, str]:
    """Ask before every tap, as the sender would for a garage door."""
    return {
        int(key.partition(":")[0]): QUESTION
        for key in bindings["actions"]
        if key.endswith(":tap")
    }


def _size(layout: dict, caps: dict, questions: dict | None = None) -> int:
    """Return the bytes of the device layout."""
    return device.compile_device_layout(layout, ICONS, caps, confirm=questions)["size"]


def test_the_questions_make_the_layout_bigger() -> None:
    """The precondition of the tests below: the light cards have taps to ask for."""
    result = _convert(_two_lamps(), 2)
    caps = dict(device.ENGINE_CAPS_V2)
    questions = _questions(result["bindings"])
    assert len(questions) >= 2
    assert _size(result["layout"], caps, questions) > _size(result["layout"], caps)


def test_a_layout_that_fits_only_without_its_questions_is_fitted_again() -> None:
    """Detail pages are left out until the layout fits with its questions."""
    full = _convert(_two_lamps(), 2)
    caps = {**device.ENGINE_CAPS_V2}
    caps["max_layout"] = _size(full["layout"], caps)
    # Without the questions the converter sees no reason to leave anything out,
    plain = _convert(_two_lamps(), 2, caps=caps)
    assert "too_many_details" not in _codes(plain)
    # and the sender's compile with the questions is refused.
    try:
        _size(plain["layout"], caps, _questions(plain["bindings"]))
    except ContractError as err:
        assert err.code == "too_big"
    else:
        raise AssertionError("the layout fitted with its questions")
    seen: list[dict] = []

    def confirm(bindings: dict) -> dict[int, str]:
        seen.append(bindings)
        return _questions(bindings)

    result = _convert(_two_lamps(), 2, caps=caps, confirm=confirm)
    assert "too_many_details" in _codes(result)
    # One detail page went; both cards stay.
    pages = result["layout"]["pages"]
    assert [page["id"] for page in pages] == ["home", "home~1"]
    assert sum(1 for item in pages[0]["w"] if item["t"] == "card") == 2
    assert seen and all("actions" in bindings for bindings in seen)
    questions = _questions(result["bindings"])
    assert _size(result["layout"], caps, questions) <= caps["max_layout"]


def test_not_kept_counts_the_questions() -> None:
    """A layout kept only without its questions is not kept."""
    full = _convert(_two_lamps(), 2)
    caps = {**device.ENGINE_CAPS_V2}
    caps["max_stored"] = _size(full["layout"], caps)
    assert "not_kept" not in _codes(_convert(_two_lamps(), 2, caps=caps))
    with_questions = _convert(_two_lamps(), 2, caps=caps, confirm=_questions)
    assert "not_kept" in _codes(with_questions)


async def test_the_manager_fits_with_the_senders_questions(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A garage door's questions count when the manager makes a layout v2."""
    hass.states.async_set(
        "cover.garage", "closed", {"device_class": "garage", "friendly_name": "Garage"}
    )
    hass.states.async_set(
        "light.h1401",
        "on",
        {"supported_color_modes": ["brightness"], "color_mode": "brightness"},
    )
    light = {
        "type": "custom:apollo-tab-card",
        "component": "apollo/light",
        "params": {"entity": "light.h1401"},
    }
    garage = {
        "type": "custom:apollo-tab-card",
        "component": "apollo/blinds",
        "params": {"entity": "cover.garage"},
    }
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light, garage))
    manager = config_entry.runtime_data.manager
    components = config_entry.runtime_data.library.components

    def questions(bindings: dict) -> dict[int, str]:
        return live.cover_questions(hass, components, bindings)

    roomy = {**device.ENGINE_CAPS_V2}
    full = manager.layout_for("tab-home", 2, roomy)
    assert [page["id"] for page in full["layout"]["pages"]] == ["home", "home~1"]
    asked = questions(full["bindings"])
    assert asked and set(asked.values()) >= {"Open Garage?"}
    without = _size(full["layout"], roomy)
    assert _size(full["layout"], roomy, asked) > without

    tight = {**device.ENGINE_CAPS_V2, "max_layout": without}
    fitted = manager.layout_for("tab-home", 2, tight)
    assert "too_many_details" in [warning["code"] for warning in fitted["warnings"]]
    assert [page["id"] for page in fitted["layout"]["pages"]] == ["home"]
    size = _size(fitted["layout"], tight, questions(fitted["bindings"]))
    assert size <= without


async def test_the_editor_preview_fits_with_the_questions(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The preview of a layout v2 counts a garage door's questions too."""
    hass.states.async_set(
        "cover.garage", "closed", {"device_class": "garage", "friendly_name": "Garage"}
    )
    hass.states.async_set(
        "light.h1401",
        "on",
        {"supported_color_modes": ["brightness"], "color_mode": "brightness"},
    )
    light = {
        "type": "custom:apollo-tab-card",
        "component": "apollo/light",
        "params": {"entity": "light.h1401"},
    }
    garage = {
        "type": "custom:apollo-tab-card",
        "component": "apollo/blinds",
        "params": {"entity": "cover.garage"},
    }
    await setup_integration(hass, config_entry)
    manager = config_entry.runtime_data.manager
    config = tab_config(light, garage)
    full = await manager.async_preview(copy.deepcopy(config), dl=2)
    assert [page["id"] for page in full["layout"]["pages"]] == ["home", "home~1"]
    roomy = {**device.ENGINE_CAPS_V2}
    without = _size(full["layout"], roomy)

    # The preview fits to what engine 0.2.0 answers; make that tight.
    monkeypatch.setattr(
        convert, "ENGINE_CAPS_V2", {**device.ENGINE_CAPS_V2, "max_layout": without}
    )
    fitted = await manager.async_preview(copy.deepcopy(config), dl=2)
    assert "too_many_details" in [warning["code"] for warning in fitted["warnings"]]
    assert [page["id"] for page in fitted["layout"]["pages"]] == ["home"]


def test_caps_without_max_stored_keep_the_contracts_default() -> None:
    """A tablet that leaves max_stored out keeps what contract 3 says."""
    caps = {**device.ENGINE_CAPS_V2}
    del caps["max_stored"]
    result = _convert(_two_lamps(), 2, caps=caps)
    assert "not_kept" not in _codes(result)
    size = _size(result["layout"], device.ENGINE_CAPS_V2)
    assert size <= device.CAPS_DEFAULTS["max_stored"]
