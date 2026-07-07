"""Tests for subtopic content extraction from enriched JSON."""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_vitamins_health_not_smoking_content():
    path = PROJECT_ROOT / "data" / "metabolomic-medicine" / "enriched" / "iPs1TPO1dJA.json"
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    concept = "Βιταμίνες και υγεία"
    from utils.topic_content import (
        extract_quotes_for_concept,
        extract_takeaways_for_concept,
        synthesize_subtopic_overview,
    )

    takeaways = extract_takeaways_for_concept(data, concept)
    assert len(takeaways) <= 2
    assert all("καπν" not in t.lower() and "τσιγ" not in t.lower() for t in takeaways)
    assert any("βιταμιν" in t.lower() for t in takeaways)
    quotes = extract_quotes_for_concept(data, concept)
    assert len(quotes) == 0
    overview = synthesize_subtopic_overview(concept, takeaways=takeaways, summaries=[], angles=[])
    assert "καπν" not in overview.lower()


def test_line_matches_rejects_unrelated_bullets():
    from utils.topic_content import _line_matches_concept

    concept = "Βιταμίνες και υγεία"
    assert not _line_matches_concept(
        "Άμεση διακοπή: Το κόψιμο μαχαίρι είναι πιο αποτελεσματικό από τη σταδιακή μείωση του καπνίσματος.",
        concept,
    )
    assert _line_matches_concept(
        "Διατροφή και τρόπος ζωής: Η βελτίωση της διατροφής και η λήψη βιταμινών είναι σημαντικοί παράγοντες.",
        concept,
    )

    path = PROJECT_ROOT / "data" / "metabolomic-medicine" / "enriched" / "aN3uVyK78bA.json"
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    concept = "Ελλείψεις Βιταμινών"
    from utils.topic_content import (
        extract_summary_for_concept,
        extract_takeaways_for_concept,
        synthesize_subtopic_overview,
        video_mentions_concept,
    )

    assert video_mentions_concept(data, concept)
    takeaways = extract_takeaways_for_concept(data, concept)
    assert len(takeaways) >= 1
    assert any("βιταμιν" in t.lower() or "θρεπτικ" in t.lower() for t in takeaways)
    summary = extract_summary_for_concept(data, concept)
    assert summary
    overview = synthesize_subtopic_overview(
        concept, takeaways=takeaways, summaries=[summary], angles=[], parent_theme="υγεία"
    )
    assert "δες παρακάτω" not in overview.lower()
    assert len(overview) > 40


def test_extract_theme_threads_stays_on_theme_concepts():
    from utils.topic_content import extract_theme_threads, video_mentions_concept

    learning_video = {
        "title": "Organize notes",
        "gemini_sections": {
            "Takeaways": "Η μάθηση από βίντεο απαιτεί οργάνωση θεματικών ώστε να συνδέεις γνώση χωρίς να χάνεσαι σε links.",
            "Related Concepts": "[[Μάθηση]]",
        },
        "gemini_notes": "[[Μάθηση]]",
    }
    smoking_video = {
        "title": "Smoking",
        "gemini_sections": {
            "Takeaways": "Άμεση διακοπή καπνίσματος — χρόνια βλάβη από το κάπνισμα.",
            "Related Concepts": "[[Κάπνισμα]]",
        },
        "gemini_notes": "[[Κάπνισμα]]",
    }
    theme_concepts = ["Μάθηση", "Οργάνωση"]
    threads = extract_theme_threads([smoking_video, learning_video], theme_concepts)
    assert threads
    assert all("καπν" not in t.lower() and "τσιγ" not in t.lower() for t in threads)
    assert not video_mentions_concept(smoking_video, "Μάθηση")
