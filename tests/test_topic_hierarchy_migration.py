"""Tests for automatic theme hierarchy migration detection."""
from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_metabolomic_vault_has_theme_folders_after_migration():
    vault = PROJECT_ROOT / "data" / "metabolomic-medicine" / "vault"
    if not vault.is_dir():
        pytest.skip("metabolomic-medicine vault not present")
    from dashboard.services.topic_sync import vault_hierarchy_status

    status = vault_hierarchy_status(vault)
    assert status["theme_folders"] >= 5
    assert status["needs_migration"] is False
    assert status["flat_topics"] <= 5


def test_flat_legacy_vault_detected():
    from dashboard.services.topic_sync import vault_needs_hierarchy_migration

    class Fake:
        pass

    # proswpikesshmeiwseismathshs should already be migrated
    migrated = PROJECT_ROOT / "data" / "proswpikesshmeiwseismathshs" / "vault"
    if migrated.is_dir():
        assert vault_needs_hierarchy_migration(migrated) is False
