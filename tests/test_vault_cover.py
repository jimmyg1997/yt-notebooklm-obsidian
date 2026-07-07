"""Tests for vault cover generation."""
from pathlib import Path

import pytest


def test_ensure_vault_cover_creates_file(vault_path):
    pytest.importorskip("PIL")
    from dashboard.services.vault_cover import COVER_REL, ensure_vault_cover

    rel = ensure_vault_cover(vault_path, force=True)
    assert rel == COVER_REL
    cover = vault_path / COVER_REL
    assert cover.is_file()
    assert cover.stat().st_size > 1000


@pytest.fixture
def vault_path():
    candidate = Path(__file__).resolve().parent.parent / "data" / "proswpikesshmeiwseismathshs" / "vault"
    if not candidate.is_dir():
        pytest.skip("sample vault missing")
    return candidate
