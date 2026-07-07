"""Logical user-flow tests for vault dashboard (edit, graph, topics, wikilinks)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def vault_path():
    """Use a known experiment vault if present."""
    candidate = PROJECT_ROOT / "data" / "proswpikesshmeiwseismathshs" / "vault"
    if not candidate.is_dir():
        pytest.skip("Sample vault not present locally")
    return candidate


@pytest.fixture
def vault_id(vault_path):
    from dashboard.services.vault_scanner import encode_vault_id

    return encode_vault_id(vault_path)


def test_resolve_topics_path_wikilink(vault_id):
    from dashboard.services.vault_reader import VaultReader

    reader = VaultReader(vault_id)
    themes = reader.list_all_notes_flat()
    topic = next((n for n in themes if n["path"].startswith("Topics/")), None)
    if not topic:
        pytest.skip("No topic notes in vault")
    stem = topic["path"].replace(".md", "")
    res = reader.resolve_wikilink(stem)
    assert res["found"], f"Should resolve path-style link: {stem}"


def test_graph_focus_scope_centers_on_note(vault_id):
    from dashboard.services.vault_reader import VaultReader

    reader = VaultReader(vault_id)
    notes = reader.list_all_notes_flat()
    video = next((n for n in notes if n["path"].startswith("0") and "Topics" not in n["path"]), None)
    if not video:
        pytest.skip("No episode note in sample vault")
    g = reader.build_graph(scope="focus", focus=video["path"])
    assert g["center_id"] == video["path"]
    assert g["layout"] == "focus"
    assert 1 <= len(g["nodes"]) <= 72
    assert video["path"] in {n["id"] for n in g["nodes"]}


def test_overview_uses_hierarchical_layout(vault_id):
    from dashboard.services.vault_reader import VaultReader

    g = VaultReader(vault_id).build_graph(scope="overview")
    assert g["layout"] == "hierarchical"
    groups = {n["group"] for n in g["nodes"]}
    assert "subtopic" not in groups


def test_update_vault_metadata_roundtrip(vault_id, vault_path):
    from dashboard.services.vault_editor import update_vault_metadata
    from dashboard.services.vault_factory import read_vault_meta

    original = read_vault_meta(vault_path) or {}
    name = original.get("name", "Test")
    updated = update_vault_metadata(
        vault_id,
        description=(original.get("description") or "") + " ",
    )
    assert updated.get("name") == name
    # restore trailing space trim
    update_vault_metadata(vault_id, description=(original.get("description") or ""))


def test_sync_topics_links_episode(vault_path, monkeypatch):
    monkeypatch.setenv("TOPIC_SYNC_SKIP_LLM", "1")
    from dashboard.services.topic_sync import sync_topics_after_ingest

    data_dir = vault_path.parent
    enriched = data_dir / "enriched" / "VSwlDCDmNR4.json"
    if not enriched.is_file():
        pytest.skip("No enriched JSON for sample video")
    note = None
    for p in vault_path.rglob("*.md"):
        if "VSwlDCDmNR4" in p.read_text(encoding="utf-8", errors="replace") and "Topics/" not in str(p.relative_to(vault_path)):
            note = p.stem
            break
    if not note:
        pytest.skip("No video note for VSwlDCDmNR4")
    meta_path = data_dir / ".vault-meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    touched = sync_topics_after_ingest(
        vault_path,
        enriched,
        note,
        vault_name=meta.get("name", "Vault"),
        vault_themes=meta.get("themes"),
    )
    assert touched, "Should touch at least one topic"
    any_mention = False
    mention_headers = (
        "## Mentioned in",
        "## Εμφανίζεται σε",
        "## Πηγές (επεισόδια)",
        "## Sources (episodes)",
    )
    for tp in vault_path.rglob("Topics/**/*.md"):
        text = tp.read_text(encoding="utf-8")
        if note in text and any(h in text for h in mention_headers):
            any_mention = True
            assert (
                "## Σχετικά" in text
                or "## Related subtopics" in text
                or "## Related topics" in text
            )
            break
    assert any_mention, "Topic note should list the episode under Mentioned in"


def test_vault_analytics_breakdown(vault_path):
    from dashboard.services.vault_scanner import vault_analytics

    stats = vault_analytics(vault_path)
    assert stats["topics"] >= 1
    assert stats["videos_analyzed"] >= 1
    assert stats["total_notes"] >= stats["topics"]


def test_topic_notes_have_related_section(vault_path):
    topics_root = vault_path / "Topics"
    if not topics_root.is_dir():
        pytest.skip("No Topics folder")
    topics = list(topics_root.rglob("*.md"))
    if not topics:
        pytest.skip("No topic notes")
    for tp in topics[:5]:
        text = tp.read_text(encoding="utf-8")
        assert (
            "## Σχετικά" in text
            or "## Related subtopics" in text
            or "## Related topics" in text
            or "## Εμφανίζεται σε" in text
            or "## Mentioned in" in text
            or "## Υποθέματα" in text
            or "## Subtopics" in text
        )
        assert "## What you'll learn" not in text
        if "subtopic" in text and "parent:" in text:
            assert "## Τι καλύπτει" in text or "## About this concept" in text
            assert "## Συγκεκριμένα από τα βίντεο" in text or "## Key facts from your videos" in text
