"""Test the Component template sandbox."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import jinja2.exceptions
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.template import Template

from custom_components.apollo_tab import sandbox
from custom_components.apollo_tab.sandbox import (
    ComponentEnvironment,
    ComponentTemplate,
    RenderLimitError,
    deep_size,
)

_SLOW_LOOP = (
    "{% for i in range(30000) %}{% for j in range(30000) %}{% endfor %}{% endfor %}"
)


def _render(hass: HomeAssistant, text: str, **variables: Any) -> Any:
    """Render a Component template and return its raw string result."""
    return ComponentTemplate(text, hass).async_render(variables, parse_result=False)


def _assert_limited(hass: HomeAssistant, text: str) -> BaseException:
    """Render text expecting a fast limit failure and return the cause."""
    started = time.monotonic()
    with pytest.raises(TemplateError) as excinfo:
        _render(hass, text)
    assert time.monotonic() - started < 1
    cause = excinfo.value.__cause__
    assert isinstance(cause, jinja2.exceptions.SecurityError)
    return cause


@pytest.mark.parametrize(
    ("text", "kinds"),
    [
        ("{{ ('%9' ~ '99999999d') % 1 }}", ("blocked",)),
        ("{{ 'x' | center(30000 * 30000) }}", ("size",)),
        ("{% set n = 100000 %}{{ 'x'.center(n * n) }}", ("size",)),
        ("{{ (range(100000)|list) * 3000 }}", ("size",)),
        ("{% set a = ('x'|string) * 100000 %}{{ (a * 9000)|length }}", ("size",)),
        (
            "{% for i in range(30000) %}{% for j in range(30000) %}"
            "{% endfor %}{% endfor %}",
            ("steps", "time"),
        ),
        (
            "{% set ns = namespace(a='x') %}{% for i in range(40) %}"
            "{% set ns.a = ns.a ~ ns.a %}{% endfor %}{{ ns.a | length }}",
            ("size",),
        ),
        (
            "{% set ns = namespace(a=[0]) %}{% for i in range(40) %}"
            "{% set ns.a = ns.a + ns.a %}{% endfor %}{{ ns.a | length }}",
            ("size",),
        ),
        ("{{ 9 ** 9999999 }}", ("size",)),
        ("{{ [[0] * 30000] * 30000 }}", ("size",)),
        ("{{ range(30000) | map('iif', 'x' * 30000) | join }}", ("size",)),
        ("{{ [1] | batch(1000000000, 'x') | list }}", ("size",)),
        ("{{ [1] | slice(1000000000) | list }}", ("size",)),
        ("{{ ('x' * 30000) | indent(30000) }}", ("size",)),
        ("{{ ('x' * 30000) | wordwrap(1, wrapstring='y' * 1000) }}", ("size",)),
        ("{{ ('ab' * 10000) | replace('a', 'aaaaaaaaaa') }}", ("size",)),
        ("{{ ('ab' * 10000).replace('', 'x' * 100) }}", ("size",)),
        ("{{ 'a'.ljust(1000000000) }}", ("size",)),
        ("{{ '1'.zfill(1000000000) }}", ("size",)),
        ("{{ ('x' | safe).center(1000000000) }}", ("size",)),
        ("{{ [1, 2] | sum(start=[]) }}", ("blocked",)),
        ("{% for i in range(5000) %}{{ 'x' * 10 }}{% endfor %}", ("size",)),
        (
            "{% set big = range(30000) | list %}"
            "{% for i in range(19000) %}{{ big | length }}{% endfor %}",
            ("steps", "time"),
        ),
    ],
)
async def test_expensive_templates_fail_fast(
    hass: HomeAssistant, text: str, kinds: tuple[str, ...]
) -> None:
    """Check expensive templates fail fast with the expected limit kind."""
    cause = _assert_limited(hass, text)
    assert isinstance(cause, RenderLimitError)
    assert cause.kind in kinds


@pytest.mark.parametrize(
    "text",
    [
        "{{ '{:999999999}'.format(1) }}",
        "{{ 'aaaa'.translate({97: 'x' * 30000}) }}",
    ],
)
async def test_blocked_text_methods_fail_fast(hass: HomeAssistant, text: str) -> None:
    """Check blocked text methods fail fast with a security error."""
    _assert_limited(hass, text)


@pytest.mark.parametrize(
    "text",
    [
        "{{ ('%9' ~ '99999999d') % 1 }}",
        "{{ 'x' | center(30000 * 30000) }}",
    ],
)
async def test_defect_templates_compile_fast(hass: HomeAssistant, text: str) -> None:
    """Check the templates from the library defect compile in under 0.1 s."""
    started = time.monotonic()
    ComponentTemplate(text, hass).ensure_valid()
    assert time.monotonic() - started < 0.1


async def test_unavailable_filter_fails(hass: HomeAssistant) -> None:
    """Check a removed filter makes the template invalid."""
    with pytest.raises(TemplateError):
        ComponentTemplate("{{ 'a' | regex_match('a') }}", hass).ensure_valid()


async def test_unavailable_global_fails_fast(hass: HomeAssistant) -> None:
    """Check a removed global fails quickly when rendered."""
    started = time.monotonic()
    with pytest.raises(TemplateError):
        _render(hass, "{{ lipsum(1000000) }}")
    assert time.monotonic() - started < 1


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("{{ 'ab' * 3 }}", "ababab"),
        ("{{ [1, 2] + [3] }}", "[1, 2, 3]"),
        ("{{ 7 % 3 }}", "1"),
        ("{{ 2 ** 10 }}", "1024"),
        ("{{ 'a' ~ 1 }}", "a1"),
        ("{% for i in range(3) %}{{ i }}{% endfor %}", "012"),
        ("{{ 'a_b' | replace('_', ' ') }}", "a b"),
        ("{{ '[' ~ 'x'.center(5) ~ ']' }}", "[  x  ]"),
        ("{{ ['a', 'b'] | join(', ') }}", "a, b"),
        ("{{ [1, 2, 3] | sum }}", "6"),
        ("{% set x %}{{ 1 + 1 }}{% endset %}{{ x }}", "2"),
        ("{{ range(3) | map('string') | join }}", "012"),
        ("{{ {'a': 1}.get('a') }}", "1"),
        ("{{ 'a-b'.split('-') | join('+') }}", "a+b"),
    ],
)
async def test_ordinary_templates_still_work(
    hass: HomeAssistant, text: str, expected: str
) -> None:
    """Check ordinary templates render their normal output."""
    assert _render(hass, text) == expected


async def test_templates_with_states(hass: HomeAssistant) -> None:
    """Check state helpers keep working under the sandbox."""
    hass.states.async_set("light.kitchen", "on", {"brightness": 128})
    assert (
        _render(
            hass,
            "{{ state_attr('light.kitchen', 'brightness') | int(0) * 100 // 255 }}",
        )
        == "50"
    )
    assert _render(hass, "{{ states('light.kitchen') }}") == "on"
    assert (
        _render(
            hass,
            "{{ expand(['light.kitchen']) | selectattr('state', 'eq', 'on')"
            " | list | count }}",
        )
        == "1"
    )


async def test_slow_template_switches_off(hass: HomeAssistant) -> None:
    """Check a slow template switches off and stays cheap afterwards."""
    template = ComponentTemplate(_SLOW_LOOP, hass)
    messages: list[str] = []
    template.on_switched_off = messages.append

    info = template.async_render_to_info({})
    assert info.exception is not None
    assert isinstance(info.exception.__cause__, RenderLimitError)
    assert template.switched_off is not None
    assert template.switched_off.startswith("switched off: ")
    assert not messages

    started = time.monotonic()
    second = template.async_render_to_info({})
    assert time.monotonic() - started < 0.05
    assert second.is_static
    assert str(second.exception) == str(info.exception)

    await asyncio.sleep(0)
    assert messages == [template.switched_off]


class _StallingClock:
    """Stand in for the time module and add a stall when asked to."""

    def __init__(self) -> None:
        """Start without a stall."""
        self.offset = 0.0
        self.stall_seconds = 0.0
        self.readings_before_stall = 0

    def stall(self, seconds: float, after_readings: int) -> None:
        """Jump ahead by seconds once that many more readings were taken."""
        self.stall_seconds = seconds
        self.readings_before_stall = after_readings

    def monotonic(self) -> float:
        """Return the real clock plus every stall so far."""
        if self.stall_seconds:
            if self.readings_before_stall == 0:
                self.offset += self.stall_seconds
                self.stall_seconds = 0.0
            else:
                self.readings_before_stall -= 1
        return time.monotonic() + self.offset


async def test_one_stalled_render_keeps_template_on(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One render that a stall made slow still gives its result."""
    clock = _StallingClock()
    monkeypatch.setattr(sandbox, "time", clock)
    template = ComponentTemplate("{{ 1 + 1 }}", hass)
    # The stall falls between the start reading and the end reading.
    clock.stall(0.5, after_readings=1)
    info = template.async_render_to_info({})
    assert info.exception is None
    assert info.result() == 2
    assert template.switched_off is None
    assert template.async_render_to_info({}).result() == 2


async def test_one_time_limit_fails_that_render_only(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A render that ran out of time once is an error for that render only."""
    clock = _StallingClock()
    monkeypatch.setattr(sandbox, "time", clock)
    template = ComponentTemplate("{{ 1 + 1 }}", hass)
    # The stall falls after the deadline is set, so the next step is late.
    clock.stall(0.15, after_readings=2)
    info = template.async_render_to_info({})
    assert isinstance(info.exception.__cause__, RenderLimitError)
    assert info.exception.__cause__.kind == "time"
    assert "switched off" not in str(info.exception)
    assert template.switched_off is None
    assert template.async_render_to_info({}).result() == 2


async def test_repeated_overruns_switch_off(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The third slow render within a minute switches the template off."""
    clock = _StallingClock()
    monkeypatch.setattr(sandbox, "time", clock)
    template = ComponentTemplate("{{ 1 + 1 }}", hass)
    for _ in range(sandbox.OVERRUN_LIMIT - 1):
        clock.stall(0.5, after_readings=1)
        assert template.async_render_to_info({}).result() == 2
    assert template.switched_off is None
    clock.stall(0.5, after_readings=1)
    info = template.async_render_to_info({})
    assert template.switched_off == "switched off: rendering took 0.50 seconds"
    assert isinstance(info.exception.__cause__, RenderLimitError)


async def test_old_overruns_are_forgotten(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Slow renders more than a minute apart never add up."""
    clock = _StallingClock()
    monkeypatch.setattr(sandbox, "time", clock)
    template = ComponentTemplate("{{ 1 + 1 }}", hass)
    for _ in range(sandbox.OVERRUN_LIMIT * 2):
        clock.stall(0.5, after_readings=1)
        assert template.async_render_to_info({}).result() == 2
        clock.offset += sandbox.OVERRUN_WINDOW_SECONDS
    assert template.switched_off is None


async def test_fast_template_stays_on(hass: HomeAssistant) -> None:
    """Check a fast template is not switched off after rendering."""
    template = ComponentTemplate("{{ 1 + 1 }}", hass)
    info = template.async_render_to_info({})
    assert info.exception is None
    assert template.switched_off is None


async def test_environment_sharing(hass: HomeAssistant) -> None:
    """Check ComponentTemplates share a cached ComponentEnvironment."""
    first = ComponentTemplate("{{ 1 }}", hass)
    second = ComponentTemplate("{{ 2 }}", hass)
    env = first._env
    assert isinstance(env, ComponentEnvironment)
    assert second._env is env
    assert not isinstance(Template("{{ 1 }}", hass)._env, ComponentEnvironment)


async def test_limited_render_uses_separate_environment(
    hass: HomeAssistant,
) -> None:
    """Check limited renders use a separate environment without states."""
    limited = ComponentTemplate("{{ states('light.kitchen') }}", hass)
    with pytest.raises(TemplateError):
        limited.async_render({}, limited=True)
    assert isinstance(limited._env, ComponentEnvironment)
    assert limited._env is not ComponentTemplate("{{ 1 }}", hass)._env


def test_deep_size() -> None:
    """Count nested sizes and raise past the limit."""
    assert deep_size("abc") == 3
    assert deep_size([1, "ab", {"k": "v"}]) == 1 + 1 + 2 + 1 + 1 + 1
    with pytest.raises(RenderLimitError):
        deep_size(list(range(10)), limit=5)
