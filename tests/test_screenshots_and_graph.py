"""Tests for screenshots, VTT cues, note formatting, and graph/explorer metadata."""
from pathlib import Path

import pytest

from agents.screenshot_agent import compute_frame_budget
from utils.note_formatter import format_key_visuals_section, format_transcript_section
from utils.vtt_cleaner import cue_text_at_second, parse_vtt_cues


SAMPLE_VTT = """WEBVTT

00:00:01.000 --> 00:00:04.000
Witam w sklepie Biedronka

00:01:30.500 --> 00:01:35.000
Najlepszy produkt to jajka ekologiczne
"""


def test_parse_vtt_cues():
    cues = parse_vtt_cues(SAMPLE_VTT)
    assert len(cues) == 2
    assert "Biedronka" in cues[0]["text"]


def test_cue_text_at_second():
    cues = parse_vtt_cues(SAMPLE_VTT)
    assert "jajka" in cue_text_at_second(cues, 92)


def test_screenshot_budget_minimum_20():
    budget = compute_frame_budget(600, {"gemini_sections": {}})
    assert budget >= 20


def test_key_visuals_pairs_excerpt():
    frames = [
        {
            "rel_path": "assets/x/frame_01.jpg",
            "caption": "Eggs aisle",
            "timestamp_label": "1:30",
            "transcript_excerpt": "Najlepszy produkt to jajka ekologiczne",
        }
    ]
    md = format_key_visuals_section(frames, "x")
    assert "jajka" in md
    assert "Eggs aisle" in md


def test_transcript_section_collapsible():
    md = format_transcript_section("Hello transcript")
    assert "<details>" in md
    assert "Hello transcript" in md


def test_classify_theme_moc():
    from dashboard.services.vault_reader import _classify_note

    moc = '---\ntags:\n  - theme\n  - moc\nrole: theme\n---\n'
    assert _classify_note("Topics/διατροφή.md", moc) == "theme"


def test_classify_video_vs_subtopic():
    from dashboard.services.vault_reader import _classify_note

    video = '---\nsource: youtube\nvideo_id: "abc"\n---\n'
    assert _classify_note("01 - Title.md", video) == "video"
    topic = '---\ntags:\n  - topic\n  - subtopic\nparent: "διατροφή"\n---\n'
    assert _classify_note("Topics/διατροφή/Αβγά.md", topic) == "subtopic"


def test_graph_includes_video_group(vault_id):
    from dashboard.services.vault_reader import VaultReader

    g = VaultReader(vault_id).build_graph()
    groups = {n["group"] for n in g["nodes"]}
    assert "video" in groups or "theme" in groups or "subtopic" in groups


@pytest.fixture
def vault_id():
    candidate = Path(__file__).resolve().parent.parent / "data" / "proswpikesshmeiwseismathshs" / "vault"
    if not candidate.is_dir():
        pytest.skip("sample vault missing")
    from dashboard.services.vault_scanner import encode_vault_id

    return encode_vault_id(candidate)
