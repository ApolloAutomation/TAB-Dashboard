"""`when`: whether a part of a schema 2 card is there (C.2.5 of the cards spec).

Pure Python. Its twin is `whenHolds` in frontend/logic.js; both pass the
vectors of tests/fixtures/when_vectors.json.

`names` is one flat mapping from a term's name to its value: an option by
its name, a fact as "can.<what>" or "can.<param>.<what>", "has.<param>",
and "tablet.v2". A name that is not there is false.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

_TERM = re.compile(
    r"^(!)?([a-z][a-z0-9_]*(?:\.[a-z0-9][a-z0-9_]*){0,2})"
    r"(?:(=|!=)([a-z0-9_]+(?:\|[a-z0-9_]+)*))?$"
)


def truthy(value: object) -> bool:
    """Return whether a value counts as on.

    Yes, a number that is not 0, a text that is not empty and not "none",
    and a list or mapping that is not empty. A list of devices' facts counts
    when one entry counts.
    """
    if value is None or value is False:
        return False
    if value is True:
        return True
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        return value not in ("", "none")
    if isinstance(value, list | tuple):
        return len(value) > 0
    if isinstance(value, Mapping):
        return len(value) > 0
    return False


def _text(value: object) -> str | None:
    """Return the text a value is compared as, or None."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value)
    if isinstance(value, str):
        return value
    return None


def _equals(value: object, wanted: list[str]) -> bool:
    """Return whether a value is one of the wanted texts.

    For a list, one entry is enough. "none" also matches no value, an
    empty text and an empty list.
    """
    if "none" in wanted and not truthy(value):
        return True
    if isinstance(value, list | tuple):
        return any(_equals(entry, wanted) for entry in value if entry is not None)
    text = _text(value)
    return text is not None and text in wanted


def term_holds(term: str, names: Mapping[str, object]) -> bool:
    """Return whether one term holds. A term of a bad shape never holds."""
    match = _TERM.match(term) if isinstance(term, str) else None
    if match is None:
        return False
    negate, name, op, values = match.groups()
    if negate and op:
        return False
    value = names.get(name)
    if op is None:
        held = truthy(value)
        return not held if negate else held
    wanted = values.split("|")
    held = _equals(value, wanted)
    return held if op == "=" else not held


def when_holds(terms: list | None, names: Mapping[str, object]) -> bool:
    """Return whether every term of a `when` list holds. No terms: it holds."""
    return all(term_holds(term, names) for term in terms or [])
