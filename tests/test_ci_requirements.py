"""The CI helper that installs what ESPHome's RuntimeEntryData needs."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "esphome_requirements.py"


@pytest.fixture(scope="module")
def script():
    """Load the helper script as a module."""
    spec = importlib.util.spec_from_file_location("esphome_requirements", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_closure_reaches_what_esphome_imports(script) -> None:
    """The list follows imports and dependencies, not only two manifests."""
    root = script.components_root()
    domains = script.closure(root)
    for domain in (
        "esphome",
        "usb",
        "assist_satellite",
        "assist_pipeline",
        "conversation",
        "bluetooth",
    ):
        assert domain in domains
    lines = script.requirements(root, domains)
    names = {script.split(line)[0] for line in lines}
    for name in ("aioesphomeapi", "hassil", "home-assistant-intents", "pymicro-vad"):
        assert name in names
    assert len(lines) == len(set(lines))


def test_only_missing_packages_are_listed(script, monkeypatch) -> None:
    """An installed package is never listed, so its version never changes."""
    monkeypatch.setattr(
        script, "installed", lambda name: "1.0" if name == "hassil" else None
    )
    assert script.missing(["hassil==3.12.1", "mutagen==1.48.1"]) == ["mutagen==1.48.1"]
    assert script.split("bleak[extra]==3.0.2") == ("bleak", "3.0.2")
    assert script.split("serialx") == ("serialx", None)


def test_check_wants_home_assistants_aioesphomeapi(
    script, monkeypatch, tmp_path
) -> None:
    """--check fails when aioesphomeapi is not the version HA pins."""
    for domain, data in (
        ("esphome", {"requirements": ["aioesphomeapi==46.6.0"], "dependencies": []}),
        ("usb", {}),
    ):
        (tmp_path / domain).mkdir()
        (tmp_path / domain / "manifest.json").write_text(json.dumps(data))
    monkeypatch.setattr(script, "installed", lambda name: "46.25.0")
    assert script.check(tmp_path) == [
        "aioesphomeapi 46.25.0 is installed, Home Assistant pins 46.6.0"
    ]
    monkeypatch.setattr(script, "installed", lambda name: "46.6.0")
    assert script.check(tmp_path) == []
    monkeypatch.setattr(script, "installed", lambda name: None)
    assert script.check(tmp_path) == [
        "not installed: aioesphomeapi==46.6.0",
        "aioesphomeapi None is installed, Home Assistant pins 46.6.0",
    ]


@pytest.mark.parametrize("name", ["test.yml", "beta.yml"])
def test_workflows_use_the_helper(name: str) -> None:
    """Both jobs install with the helper, keep installed versions, then check."""
    text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
    assert "python .github/scripts/esphome_requirements.py >" in text
    assert 'pip install -c "$RUNNER_TEMP/installed.txt"' in text
    assert "python .github/scripts/esphome_requirements.py --check" in text
    assert text.index("--check") < text.index("import RuntimeEntryData")


def test_no_stray_aioesphomeapi_pin() -> None:
    """The test requirements do not pin an aioesphomeapi HA does not use."""
    assert "aioesphomeapi" not in (ROOT / "requirements_test.in").read_text()
    assert "aioesphomeapi" not in (ROOT / "requirements_test.txt").read_text()
