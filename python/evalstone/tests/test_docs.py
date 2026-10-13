"""The site's reference pages against the library they describe (skipped when the
site is not checked out next to the library)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SITE_DOCS = (
    Path(__file__).resolve().parents[3] / "javascript" / "evalstone-site" / "content" / "docs"
)

pytestmark = pytest.mark.skipif(not SITE_DOCS.exists(), reason="site docs not checked out")


def test_checks_catalog_lists_every_configurable_type():
    from evalstone.config import FACTORIES

    page = (SITE_DOCS / "reference" / "checks.mdx").read_text(encoding="utf-8")
    documented = set(re.findall(r"^\| `([a-z_.]+)` \|", page, flags=re.MULTILINE))
    missing = sorted(set(FACTORIES) - documented)
    assert missing == [], f"check types without a catalog row: {missing}"


def test_cli_reference_names_every_command():
    from evalstone.cli import app

    page = (SITE_DOCS / "reference" / "cli.mdx").read_text(encoding="utf-8")
    commands = {c.name or c.callback.__name__ for c in app.registered_commands}
    missing = sorted(c for c in commands if f"`{c}" not in page)
    assert missing == [], f"commands without a reference row: {missing}"
