"""Import the integration's pure logic without installing Home Assistant.

``custom_components/aus_rego/__init__.py`` pulls in Home Assistant, so these
tests register the package directory under a synthetic ``aus_rego`` name with an
empty init. Relative imports inside the package still resolve, which lets the
parsing, status and scheduling layers be tested on their own — and those are
exactly the layers that decide whether an automation fires.
"""

from __future__ import annotations

import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components" / "aus_rego"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"

if "aus_rego" not in sys.modules:
    package = types.ModuleType("aus_rego")
    package.__path__ = [str(COMPONENT)]
    sys.modules["aus_rego"] = package

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def fixture(name: str) -> str:
    """Read a captured result page."""
    return (FIXTURES / name).read_text()
