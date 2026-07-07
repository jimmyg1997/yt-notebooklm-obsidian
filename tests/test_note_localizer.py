"""Tests for note localization (el/en rendering)."""
from __future__ import annotations

from dashboard.services.note_localizer import localize_markdown, localized_title


def test_localize_section_headers_to_english():
    md = "## Περίληψη\n\nΚείμενο.\n\n## Κύριες Ιδέες\n"
    out = localize_markdown(md, "en")
    assert "## Summary" in out
    assert "## Key Ideas" in out
    assert "Περίληψη" not in out


def test_localize_section_headers_to_greek():
    md = "## Summary\n\nText.\n\n## Key Ideas\n"
    out = localize_markdown(md, "el")
    assert "## Περίληψη" in out
    assert "## Κύριες Ιδέες" in out


def test_localized_theme_title_english():
    assert localized_title("υγεία", "Topics/υγεία.md", "en") == "Health & Metabolism"
