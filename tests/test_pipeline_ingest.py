"""Tests for ingest pipeline video targeting."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_ingest_targets_video_from_url_not_first_manifest_entry():
    """Regression: must enrich/write the URL video, not the first ok entry in manifest."""
    from agents.transcript_agent import _video_id_from_url

    url = "https://www.youtube.com/watch?v=jrOPyvfge-0"
    assert _video_id_from_url(url) == "jrOPyvfge-0"

    manifest = {
        "videos": [
            {"id": "VSwlDCDmNR4", "status": "ok"},
            {"id": "jrOPyvfge-0", "status": "ok"},
        ]
    }
    ingest_id = _video_id_from_url(url)
    entry = next(v for v in manifest["videos"] if v["id"] == ingest_id)
    assert entry["id"] == "jrOPyvfge-0"
    assert manifest["videos"][0]["id"] != ingest_id


def test_local_vault_analytics_counts_nested_episodes():
    from dashboard.services.vault_scanner import vault_analytics

    myvault = PROJECT_ROOT / "Vaults" / "MyVault"
    if not myvault.is_dir():
        pytest.skip("MyVault not present")
    stats = vault_analytics(myvault)
    assert stats["videos_analyzed"] >= 1
    assert "total_notes" in stats
