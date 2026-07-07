"""Tests for topic text deduplication."""
from utils.topic_dedup import dedupe_bullets


def test_dedupe_bullets_drops_substrings():
    items = [
        "Το ελληνικό γιαούρτι είναι πλούσιο σε πρωτεΐνη.",
        "Το ελληνικό γιαούρτι είναι πλούσιο σε πρωτεΐνη και χαμηλό σε ζάχαρη, επιβραδύνοντας την απορρόφηση γλυκόζης.",
    ]
    out = dedupe_bullets(items)
    assert len(out) == 1
    assert "γλυκόζης" in out[0]


def test_dedupe_bullets_keeps_distinct():
    items = [
        "Αβγά: πλήρης πρωτεΐνη και κορεσμός.",
        "Κανέλα: βελτιώνει ευαισθησία στην ινσουλίνη.",
    ]
    assert len(dedupe_bullets(items)) == 2
