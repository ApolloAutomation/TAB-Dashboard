"""Tests for `when` of schema 2 cards (cards spec C.2.5), with the shared vectors."""

import json
from pathlib import Path

import pytest

from custom_components.apollo_tab.maker.when import term_holds, truthy, when_holds

VECTORS = json.loads(
    (Path(__file__).parent / "fixtures" / "when_vectors.json").read_text(
        encoding="utf-8"
    )
)


def _names(case: dict) -> dict:
    """Return the names of one vector: the base mapping or its own."""
    return VECTORS["base"] if case["names"] == "base" else case["names"]


@pytest.mark.parametrize(
    "case", VECTORS["cases"], ids=[case["why"] for case in VECTORS["cases"]]
)
def test_when_vectors(case: dict) -> None:
    """when_holds gives the hand-written answer of every shared vector."""
    assert when_holds(case["terms"], _names(case)) is case["holds"]


def test_the_vectors_cover_each_form_of_term() -> None:
    """The file has terms of every form, each true and false somewhere."""
    seen: dict = {}
    for case in VECTORS["cases"]:
        if len(case["terms"]) != 1:
            continue
        term = case["terms"][0]
        form = (
            "!="
            if "!=" in term
            else "="
            if "=" in term
            else "!"
            if term[0] == "!"
            else ""
        )
        seen.setdefault(form, set()).add(case["holds"])
    assert seen == {
        "": {True, False},
        "!": {True, False},
        "=": {True, False},
        "!=": {True, False},
    }


def test_more_than_one_term_means_all_of_them() -> None:
    """Each term must hold; one that fails makes the list fail."""
    names = {"a": True, "b": False}
    assert when_holds(["a"], names)
    assert not when_holds(["a", "b"], names)
    assert when_holds(["a", "!b"], names)
    assert when_holds(None, names)


def test_truthy_follows_the_rule_of_the_spec() -> None:
    """A toggle that is on; a choice, text or list not empty and not none."""
    assert truthy(True) and not truthy(False)
    assert truthy("bar") and not truthy("") and not truthy("none")
    assert truthy(["x"]) and not truthy([])
    assert truthy(2000) and not truthy(0) and not truthy(None)
    assert truthy({"a": 1}) and not truthy({})


def test_a_negated_value_term_never_holds() -> None:
    """`!name=a` is not a term; it holds for no value at all."""
    for value in ("a", "b", None):
        assert not term_holds("!name=a", {"name": value})
