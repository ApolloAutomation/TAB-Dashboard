"""List what Home Assistant's ESPHome integration needs that is not installed.

The tablet link test uses ESPHome's real RuntimeEntryData. Importing it pulls
in more than the esphome and usb manifests list: esphome imports
assist_satellite, whose chain needs hassil, home-assistant-intents and more.
So this follows, from esphome and usb:

- every integration their code imports, and
- each manifest's "dependencies", all the way down,

and prints the requirements of all of them whose package is not installed,
one per line, for ``pip install -c <pip freeze> -r <this output>``. Packages
that are installed are left out, so the install never changes a version the
test requirements chose.

``--check`` instead fails when the installed aioesphomeapi is not the version
the installed Home Assistant pins, or when a listed package is still missing.
It runs after the install.

Usage: python .github/scripts/esphome_requirements.py [--check]
"""

from __future__ import annotations

import json
import re
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import homeassistant.components as components

START = ("esphome", "usb")
IMPORT = re.compile(
    r"homeassistant\.components\.([a-z0-9_]+)|^\s*from \.\.([a-z0-9_]+)", re.M
)
REQUIREMENT = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*(?:==\s*(\S+))?"
)


def components_root() -> Path:
    """Return the folder of the installed Home Assistant's integrations."""
    return Path(components.__file__).parent


def manifest(root: Path, domain: str) -> dict:
    """Return one integration's manifest, or {} when it has none."""
    path = root / domain / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def imported(root: Path, domain: str) -> set[str]:
    """Return the integrations one integration's code imports."""
    found: set[str] = set()
    for path in (root / domain).rglob("*.py"):
        for absolute, relative in IMPORT.findall(path.read_text(encoding="utf-8")):
            found.add(absolute or relative)
    found.discard(domain)
    return {name for name in found if (root / name / "manifest.json").is_file()}


def closure(root: Path, start: tuple[str, ...] = START) -> list[str]:
    """Return the integrations the start ones need, in name order."""
    todo = list(start)
    for domain in start:
        todo.extend(imported(root, domain))
    seen: set[str] = set()
    while todo:
        domain = todo.pop()
        if domain in seen:
            continue
        seen.add(domain)
        todo.extend(manifest(root, domain).get("dependencies", []))
    return sorted(seen)


def requirements(root: Path, domains: list[str]) -> list[str]:
    """Return every requirement of these integrations, once each, in order."""
    out: list[str] = []
    for domain in domains:
        for line in manifest(root, domain).get("requirements", []):
            if line not in out:
                out.append(line)
    return out


def split(line: str) -> tuple[str, str | None]:
    """Return (package name, pinned version or None) of one requirement."""
    match = REQUIREMENT.match(line.strip())
    if not match:
        return line.strip(), None
    return match.group(1), match.group(2)


def installed(name: str) -> str | None:
    """Return the installed version of a package, or None."""
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def missing(lines: list[str]) -> list[str]:
    """Return the requirements whose package is not installed."""
    return [line for line in lines if installed(split(line)[0]) is None]


def check(root: Path) -> list[str]:
    """Return the problems after the install; empty when all is well."""
    problems = [
        f"not installed: {line}" for line in missing(requirements(root, closure(root)))
    ]
    pins = [split(line) for line in manifest(root, "esphome").get("requirements", [])]
    pin = next((pinned for name, pinned in pins if name == "aioesphomeapi"), None)
    have = installed("aioesphomeapi")
    if pin is not None and have != pin:
        problems.append(f"aioesphomeapi {have} is installed, Home Assistant pins {pin}")
    return problems


def main(argv: list[str]) -> int:
    """Print the missing requirements, or check the install with --check."""
    root = components_root()
    if argv[1:] == ["--check"]:
        problems = check(root)
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0
    if argv[1:]:
        print(__doc__, file=sys.stderr)
        return 2
    for line in missing(requirements(root, closure(root))):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
