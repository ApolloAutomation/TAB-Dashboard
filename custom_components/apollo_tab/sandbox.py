"""Run Component templates under hard limits on steps, time and sizes.

Component templates execute in a Home Assistant template environment that
checks limits on steps, wall time, value sizes and output size while the
template runs, so no template can stall the event loop or exhaust memory
whatever its expressions look like.
"""

from __future__ import annotations

import itertools
import time
from collections.abc import Callable, Iterator
from contextvars import ContextVar
from types import BuiltinMethodType, MethodType
from typing import Any

import jinja2.exceptions
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.template import RenderInfo, Template, TemplateEnvironment
from homeassistant.util.hass_dict import HassKey
from jinja2 import nodes
from jinja2.utils import _PassArg, pass_context
from jinja2.visitor import NodeTransformer

from .maker.const import (
    BLOCKED_TEXT_METHODS,
    UNAVAILABLE_FILTERS,
    UNAVAILABLE_GLOBALS,
    UNAVAILABLE_TESTS,
)

MAX_RENDER_STEPS = 20000  # loop items, operators, filter, test and function calls
RENDER_BUDGET_SECONDS = 0.1  # wall time per render, checked at every step
MAX_VALUE_SIZE = 32768  # characters of text, or items through nested containers
MAX_OUTPUT_SIZE = 32768  # characters of rendered output
MAX_INT_BITS = 1024  # largest integer an operator may produce
SLOW_RENDER_SECONDS = 0.2  # a tracked render slower than this is an overrun
# This many overruns within the window switch a template off. One overrun
# alone is not enough: a garbage collection or a busy host can stall any render.
OVERRUN_LIMIT = 3
OVERRUN_WINDOW_SECONDS = 60.0
CPU_WINDOW_SECONDS = 10.0
# More tracked render time than this in one window switches a slot off.
CPU_WINDOW_LIMIT_SECONDS = 1.0

_ENVIRONMENTS_KEY: HassKey[dict[tuple[bool, bool], ComponentEnvironment]] = HassKey(
    "apollo_tab.template_environments"
)

_TEXT_TYPES = (str, bytes)
_SEQUENCE_TYPES = (str, bytes, list, tuple)


class RenderLimitError(jinja2.exceptions.SecurityError):
    """Report a render that hit a hard limit, with ``kind`` naming the limit."""

    def __init__(self, message: str, kind: str) -> None:
        """Store the message and which kind of limit was hit."""
        super().__init__(message)
        self.kind = kind


def _steps_error() -> RenderLimitError:
    """Build the error for a render that ran out of steps."""
    return RenderLimitError(
        f"rendering needed more than {MAX_RENDER_STEPS} steps", "steps"
    )


def _time_error() -> RenderLimitError:
    """Build the error for a render that ran out of wall time."""
    return RenderLimitError(
        f"rendering took longer than {RENDER_BUDGET_SECONDS} seconds", "time"
    )


def _size_error() -> RenderLimitError:
    """Build the error for a value that grew too large."""
    return RenderLimitError(
        f"a value grew beyond {MAX_VALUE_SIZE} characters or items", "size"
    )


def _output_error() -> RenderLimitError:
    """Build the error for output that grew too long."""
    return RenderLimitError(
        f"the output grew beyond {MAX_OUTPUT_SIZE} characters", "size"
    )


def _int_error() -> RenderLimitError:
    """Build the error for an integer that grew too many bits."""
    return RenderLimitError(f"a number grew beyond {MAX_INT_BITS} bits", "size")


def limit_error(message: str) -> TemplateError:
    """Build a TemplateError that carries a switched-off RenderLimitError."""
    err = RenderLimitError(message, "switched_off")
    exc = TemplateError(err)
    exc.__cause__ = err
    return exc


def deep_size(value: Any, limit: int = MAX_VALUE_SIZE) -> int:
    """Count the characters and items nested in value, raising past limit.

    The walk uses an explicit stack instead of recursion, and stops as soon
    as the total passes limit, so one call costs at most about limit steps.
    """
    total = 0
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, (str, bytes, bytearray)):
            total += len(item)
        elif isinstance(item, (list, tuple, set, frozenset)):
            total += 1
            stack.extend(item)
        elif isinstance(item, dict):
            # Also covers mapping subclasses such as ReadOnlyDict.
            total += 1
            stack.extend(item)
            stack.extend(item.values())
        else:
            # States, generators, ranges, Undefined and namespaces count one.
            total += 1
        if total > limit:
            raise _size_error()
    return total


class _Budget:
    """Hold the deadline and step count of one render."""

    __slots__ = ("deadline", "steps")

    def __init__(self) -> None:
        """Start a budget with a fresh deadline and no spent steps."""
        self.deadline = time.monotonic() + RENDER_BUDGET_SECONDS
        self.steps = 0


_budget: ContextVar[_Budget | None] = ContextVar(
    "apollo_tab_render_budget", default=None
)


def _tick() -> None:
    """Charge one render step, enforcing the step and wall-time limits."""
    budget = _budget.get()
    if budget is None:
        # No active budget happens only while compiling, never while running.
        return
    budget.steps += 1
    if budget.steps > MAX_RENDER_STEPS:
        raise _steps_error()
    if time.monotonic() > budget.deadline:
        raise _time_error()


def _quiet_log(level: int, text: str) -> None:
    """Discard undefined-variable log messages from Component templates."""


def _limited_range(*args: int) -> range:
    """Build a range, rejecting any too long to materialize safely."""
    result = range(*args)
    try:
        length = len(result)
    except OverflowError:
        # len() overflows on ranges longer than sys.maxsize.
        raise _size_error() from None
    if length > MAX_VALUE_SIZE:
        raise _size_error()
    return result


def _check_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    """Raise when the summed deep size of the arguments is too large."""
    total = 0
    for arg in itertools.chain(args, kwargs.values()):
        # The remaining allowance bounds how much work deep_size may do.
        total += deep_size(arg, limit=MAX_VALUE_SIZE - total)


def _check_sizes(value: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    """Raise when the value plus the summed arguments grow too large."""
    total = deep_size(value)
    for arg in itertools.chain(args, kwargs.values()):
        total += deep_size(arg, limit=MAX_VALUE_SIZE - total)


def _check_repeat(seq: Any, count: int) -> None:
    """Raise when a sequence repetition would exceed the value size limit."""
    if deep_size(seq) * max(count, 0) > MAX_VALUE_SIZE:
        raise _size_error()


def _replace_exceeds(text: str | bytes, old: Any, new: Any, count: int | None) -> None:
    """Raise when a replace result would exceed the value size limit."""
    occurrences = text.count(old) if old else len(text) + 1
    if count is not None and count >= 0:
        occurrences = min(occurrences, count)
    if len(text) + occurrences * (len(new) - len(old)) > MAX_VALUE_SIZE:
        raise _size_error()


def _materialize_join(iterable: Any, separator_length: int) -> list[Any]:
    """Materialize join items while keeping the joined size within limits."""
    items: list[Any] = []
    total = 0
    for item in itertools.islice(iterable, MAX_VALUE_SIZE + 1):
        items.append(item)
        total += deep_size(item)
        if total + separator_length * (len(items) - 1) > MAX_VALUE_SIZE:
            raise _size_error()
    if len(items) > MAX_VALUE_SIZE:
        raise _size_error()
    return items


def _filter_center(value: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    """Raise when a center width exceeds the value size limit."""
    width = args[0] if args else kwargs.get("width", 80)
    if isinstance(width, int) and width > MAX_VALUE_SIZE:
        raise _size_error()
    return value


def _filter_indent(value: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    """Raise when an indent result would exceed the value size limit."""
    width = args[0] if args else kwargs.get("width", 4)
    per_line = width if isinstance(width, int) else len(width)
    text = str(value)
    if len(text) + (text.count("\n") + 1) * per_line > MAX_VALUE_SIZE:
        raise _size_error()
    return value


def _filter_wordwrap(value: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    """Raise when a wordwrap result would exceed the value size limit."""
    width = args[0] if args else kwargs.get("width", 79)
    wrapstring = args[2] if len(args) > 2 else kwargs.get("wrapstring")
    if not isinstance(width, int) or width < 1:
        # Jinja raises its own error for a width below 1.
        return value
    text = str(value)
    wrapped = len(text) + (len(text) // width + 1) * len(wrapstring or "\n")
    if wrapped > MAX_VALUE_SIZE:
        raise _size_error()
    return value


def _filter_replace(value: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    """Raise when a replace result would exceed the value size limit."""
    old = args[0] if args else kwargs.get("old")
    new = args[1] if len(args) > 1 else kwargs.get("new")
    count = args[2] if len(args) > 2 else kwargs.get("count")
    # Jinja's replace filter converts all of these to text.
    _replace_exceeds(str(value), str(old), str(new), count)
    return value


def _check_grouping(count: Any, fill_with: Any) -> None:
    """Raise when batch or slice would produce too many groups."""
    if not isinstance(count, int):
        return
    if count > MAX_VALUE_SIZE:
        raise _size_error()
    if fill_with is not None and count * deep_size(fill_with) > MAX_VALUE_SIZE:
        raise _size_error()


def _filter_batch(value: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    """Raise when a batch result would exceed the value size limit."""
    count = args[0] if args else kwargs.get("linecount")
    fill_with = args[1] if len(args) > 1 else kwargs.get("fill_with")
    _check_grouping(count, fill_with)
    return value


def _filter_slice(value: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    """Raise when a slice result would exceed the value size limit."""
    count = args[0] if args else kwargs.get("slices")
    fill_with = args[1] if len(args) > 1 else kwargs.get("fill_with")
    _check_grouping(count, fill_with)
    return value


def _filter_join(value: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    """Materialize the value, checking the joined size against the limit."""
    separator = str(args[0] if args else kwargs.get("d", ""))
    return _materialize_join(value, len(separator))


def _filter_sum(value: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    """Raise when sum would concatenate instead of adding numbers."""
    start = args[1] if len(args) > 1 else kwargs.get("start", 0)
    if not isinstance(start, (int, float)) or isinstance(start, bool):
        # Summing lists or text is quadratic, so only numbers may start.
        raise RenderLimitError("the sum filter needs a number to start from", "blocked")
    return value


_FILTER_PRE_CHECKS: dict[str, Callable[[Any, tuple[Any, ...], dict[str, Any]], Any]] = {
    "batch": _filter_batch,
    "center": _filter_center,
    "indent": _filter_indent,
    "join": _filter_join,
    "replace": _filter_replace,
    "slice": _filter_slice,
    "sum": _filter_sum,
    "wordwrap": _filter_wordwrap,
}


def _tick_each(iterator: Iterator[Any]) -> Iterator[Any]:
    """Yield items from an iterator, charging one render step per item."""
    for item in iterator:
        _tick()
        yield item


def _checked_result(result: Any) -> Any:
    """Check a call or filter result, wrapping iterators to cost steps."""
    if isinstance(result, (str, bytes)):
        if len(result) > MAX_VALUE_SIZE:
            raise _size_error()
        return result
    if isinstance(result, (list, tuple, set, frozenset, dict)):
        deep_size(result)
        return result
    if isinstance(result, Iterator) and not isinstance(result, str):
        # Lists built later from map, select or zip still cost steps.
        return _tick_each(result)
    return result


def _make_guard(
    name: str, func: Callable[..., Any], pre_check: Callable[..., Any] | None
) -> Callable[..., Any]:
    """Wrap a filter or test in a pass-context guard with size checks."""

    @pass_context
    def guard(context: Any, value: Any, /, *args: Any, **kwargs: Any) -> Any:
        """Charge a step, check sizes, then run the wrapped filter or test."""
        _tick()
        _check_sizes(value, args, kwargs)
        if pre_check is not None:
            value = pre_check(value, args, kwargs)
        pass_arg = _PassArg.from_obj(func)
        if pass_arg is _PassArg.context:
            result = func(context, value, *args, **kwargs)
        elif pass_arg is _PassArg.eval_context:
            result = func(context.eval_ctx, value, *args, **kwargs)
        elif pass_arg is _PassArg.environment:
            result = func(context.environment, value, *args, **kwargs)
        else:
            result = func(value, *args, **kwargs)
        return _checked_result(result)

    guard.__name__ = f"guarded_{name}"
    return guard


class _LimitTransformer(NodeTransformer):
    """Rewrite loops and concatenation into metered environment calls."""

    def visit_For(self, node: nodes.For) -> nodes.Node:
        """Route the loop iterable through loop_items to charge per item."""
        self.generic_visit(node)
        node.iter = nodes.Call(
            nodes.EnvironmentAttribute("loop_items", lineno=node.lineno),
            [node.iter],
            [],
            None,
            None,
            lineno=node.lineno,
        )
        return node

    def visit_Concat(self, node: nodes.Concat) -> nodes.Node:
        """Replace ``~`` with a concat_values call so it is never folded."""
        self.generic_visit(node)
        return nodes.Call(
            nodes.EnvironmentAttribute("concat_values", lineno=node.lineno),
            list(node.nodes),
            [],
            None,
            None,
            lineno=node.lineno,
        )


class ComponentEnvironment(TemplateEnvironment):
    """Enforce hard limits on steps, time and sizes while templates run."""

    intercepted_binops = frozenset({"+", "*", "%", "**"})

    def __init__(
        self,
        hass: HomeAssistant | None,
        limited: bool | None = False,
        strict: bool | None = False,
    ) -> None:
        """Set up the environment with guards on every filter and test."""
        super().__init__(hass, limited, strict, _quiet_log)
        # Constant folding evaluates operators in one uninterruptible call
        # before any limit can apply, so never fold at compile time.
        self.optimized = False
        # Components must not import or include from custom_templates.
        self.loader = None
        for name in UNAVAILABLE_FILTERS:
            self.filters.pop(name, None)
        for name in UNAVAILABLE_TESTS:
            self.tests.pop(name, None)
        for name in UNAVAILABLE_GLOBALS:
            self.globals.pop(name, None)
        self.globals["range"] = _limited_range
        # pass_context guards are never folded at compile time either.
        for name, func in list(self.filters.items()):
            self.filters[name] = _make_guard(name, func, _FILTER_PRE_CHECKS.get(name))
        for name, func in list(self.tests.items()):
            self.tests[name] = _make_guard(name, func, None)

    def call_binop(self, context: Any, operator: str, left: Any, right: Any) -> Any:
        """Charge a step and enforce size limits before applying an operator."""
        _tick()
        if operator == "*":
            if isinstance(left, int) and isinstance(right, int):
                if (
                    not isinstance(left, bool)
                    and not isinstance(right, bool)
                    and left.bit_length() + right.bit_length() > MAX_INT_BITS
                ):
                    raise _int_error()
            elif isinstance(left, _SEQUENCE_TYPES) and isinstance(right, int):
                _check_repeat(left, right)
            elif isinstance(right, _SEQUENCE_TYPES) and isinstance(left, int):
                _check_repeat(right, left)
        elif operator == "+":
            if isinstance(left, int) and isinstance(right, int):
                if (
                    not isinstance(left, bool)
                    and not isinstance(right, bool)
                    and max(left.bit_length(), right.bit_length()) + 1 > MAX_INT_BITS
                ):
                    raise _int_error()
            elif (
                isinstance(left, _TEXT_TYPES)
                and isinstance(right, _TEXT_TYPES)
                or isinstance(left, (list, tuple))
                and isinstance(right, (list, tuple))
            ) and deep_size(left) + deep_size(right) > MAX_VALUE_SIZE:
                raise _size_error()
        elif operator == "%":
            if isinstance(left, _TEXT_TYPES):
                # str % args can build an enormous string in one C call.
                raise RenderLimitError(
                    "formatting text with % is not allowed", "blocked"
                )
        elif (
            operator == "**"
            and isinstance(left, int)
            and not isinstance(left, bool)
            and isinstance(right, int)
            and not isinstance(right, bool)
            and right >= 0
            and abs(left) > 1
            and abs(left).bit_length() * right > MAX_INT_BITS
        ):
            raise _int_error()
        return self.binop_table[operator](left, right)

    def call(self, context: Any, obj: Any, /, *args: Any, **kwargs: Any) -> Any:
        """Charge a step, cap argument sizes and pre-check text methods."""
        _tick()
        _check_args(args, kwargs)
        # Only methods are asked for __self__: Home Assistant's states object
        # treats any attribute name as a domain and raises for it. Bound Python
        # methods cover Markup, whose text methods wrap the built-in ones.
        owner = (
            obj.__self__ if isinstance(obj, (BuiltinMethodType, MethodType)) else None
        )
        if isinstance(owner, (str, bytes)):
            name = getattr(obj, "__name__", "")
            if name in ("center", "ljust", "rjust", "zfill"):
                width = args[0] if args else kwargs.get("width")
                if isinstance(width, int) and width > MAX_VALUE_SIZE:
                    raise _size_error()
            elif name == "replace":
                old = args[0] if args else kwargs.get("old")
                new = args[1] if len(args) > 1 else kwargs.get("new")
                count = args[2] if len(args) > 2 else kwargs.get("count", -1)
                _replace_exceeds(owner, old, new, count)
            elif name == "join" and args:
                # Join the materialized list, not the original iterable.
                args = (_materialize_join(args[0], len(owner)), *args[1:])
        result = super().call(context, obj, *args, **kwargs)
        return _checked_result(result)

    def loop_items(self, iterable: Any) -> Iterator[Any]:
        """Yield loop items, charging one render step per item."""
        for item in iterable:
            _tick()
            yield item

    def concat_values(self, *values: Any) -> str:
        """Join ``~`` operands, capping the size of the result."""
        result = "".join(str(value) for value in values)
        if len(result) > MAX_VALUE_SIZE:
            raise _size_error()
        return result

    def is_safe_attribute(self, obj: Any, attr: str, value: Any) -> bool:
        """Block text methods that build large output from an argument."""
        if isinstance(obj, (str, bytes)) and attr in BLOCKED_TEXT_METHODS:
            return False
        return super().is_safe_attribute(obj, attr, value)

    def wrap_str_format(self, value: Any) -> None:
        """Leave str.format to is_safe_attribute instead of wrapping it."""
        return None

    def concat(self, iterable: Any) -> str:
        """Join render chunks while enforcing the budget and output size.

        Template.render runs the whole template inside this call, so the
        budget started here covers every metered operation of a render; a
        nested call (a block set) reuses the active budget.
        """
        token = None
        if _budget.get() is None:
            token = _budget.set(_Budget())
        try:
            chunks = []
            length = 0
            for chunk in iterable:
                _tick()
                chunks.append(chunk)
                length += len(chunk)
                if length > MAX_OUTPUT_SIZE:
                    raise _output_error()
            return "".join(chunks)
        finally:
            if token is not None:
                _budget.reset(token)

    def _parse(self, source: str, name: str | None, filename: str | None) -> Any:
        """Parse source, then rewrite loops and ``~`` to metered calls."""
        tree = super()._parse(source, name, filename)
        return _LimitTransformer().visit(tree)


class ComponentTemplate(Template):
    """Render a Component template with limits; switch it off when it stays slow."""

    __slots__ = (
        "_overruns",
        "_window_spent",
        "_window_start",
        "on_switched_off",
        "switched_off",
    )

    def __init__(self, template: str, hass: HomeAssistant) -> None:
        """Initialise the template with its switch-off state."""
        super().__init__(template, hass)
        self.switched_off: str | None = None
        self.on_switched_off: Callable[[str], None] | None = None
        self._window_start = time.monotonic()
        self._window_spent = 0.0
        self._overruns: list[float] = []

    @property
    def _env(self) -> ComponentEnvironment:
        """Return the shared ComponentEnvironment for these settings.

        Home Assistant's own property builds a new environment whenever a
        log function is set; the Component environment never logs, so one
        environment per (limited, strict) combination is cached and shared.
        """
        if (environments := self.hass.data.get(_ENVIRONMENTS_KEY)) is None:
            environments = self.hass.data[_ENVIRONMENTS_KEY] = {}
        key = (bool(self._limited), bool(self._strict))
        if (environment := environments.get(key)) is None:
            environment = environments[key] = ComponentEnvironment(
                self.hass, self._limited, self._strict
            )
        return environment

    @callback
    def async_render_to_info(
        self,
        variables: Any = None,
        strict: bool = False,
        log_fn: Callable[[int, str], None] | None = None,
        **kwargs: Any,
    ) -> RenderInfo:
        """Render the template, switching it off when it keeps being too slow."""
        if self.switched_off is not None:
            # A static info makes the tracker stop listening for updates.
            info = RenderInfo(self)
            info.exception = limit_error(self.switched_off)
            info.collecting = False
            info._freeze_static()
            return info

        started = time.monotonic()
        info = super().async_render_to_info(
            variables, strict=strict, log_fn=log_fn, **kwargs
        )
        now = time.monotonic()
        elapsed = now - started

        if now - self._window_start > CPU_WINDOW_SECONDS:
            self._window_start = now
            self._window_spent = 0.0
        # One render adds at most the slow-render bound, so a single stall
        # cannot use up the whole window.
        self._window_spent += min(elapsed, SLOW_RENDER_SECONDS)

        reason = None
        overrun = None
        cause = info.exception.__cause__ if info.exception is not None else None
        if isinstance(cause, RenderLimitError) and cause.kind == "steps":
            # The step count does not depend on timing, so it is final at once.
            reason = str(cause)
        elif isinstance(cause, RenderLimitError) and cause.kind == "time":
            overrun = str(cause)
        elif elapsed > SLOW_RENDER_SECONDS:
            overrun = f"rendering took {elapsed:.2f} seconds"

        if overrun is not None:
            # This render keeps its own result or error; only repeated
            # overruns switch the template off.
            self._overruns = [
                moment
                for moment in self._overruns
                if now - moment <= OVERRUN_WINDOW_SECONDS
            ]
            self._overruns.append(now)
            if len(self._overruns) >= OVERRUN_LIMIT:
                reason = overrun
        if reason is None and self._window_spent > CPU_WINDOW_LIMIT_SECONDS:
            reason = (
                f"rendering used more than {CPU_WINDOW_LIMIT_SECONDS} seconds"
                f" within {CPU_WINDOW_SECONDS} seconds"
            )

        if reason is not None:
            self.switched_off = f"switched off: {reason}"
            info.exception = limit_error(self.switched_off)
            if self.on_switched_off is not None:
                # Never call out from inside the tracker's own refresh.
                self.hass.loop.call_soon(self.on_switched_off, self.switched_off)

        return info
