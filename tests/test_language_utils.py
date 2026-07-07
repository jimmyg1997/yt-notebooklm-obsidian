"""Unit tests for multilingual subtitle and language detection."""
from utils.language_utils import (
    build_subtitle_lang_order,
    detect_text_language,
    enrichment_instructions,
    lang_display_name,
    resolve_source_language,
)


def test_polish_subtitle_order_from_metadata():
    info = {
        "language": "pl",
        "automatic_captions": {"pl": [], "en": []},
        "subtitles": {},
    }
    order = build_subtitle_lang_order("Jak działa glukoza?", info)
    assert order[0] == "pl"


def test_detect_polish_text():
    text_pl = "Ważne są węglowodany, błonnik i żelazo w diecie."
    assert detect_text_language(text_pl) == "pl"
    text_en = "Glucose and insulin regulate blood sugar levels in the body."
    assert detect_text_language(text_en) == "en"


def test_enrichment_translates_polish_to_greek():
    lang_inst, quote_inst = enrichment_instructions("greek", "pl", "Polish")
    assert "Polish" in lang_inst
    assert "Greek" in lang_inst or "Greek" in lang_inst or "Greek" in lang_inst.lower() or "Translate" in lang_inst
    assert "Translate" in quote_inst or "Greek" in quote_inst


def test_resolve_source_language_uses_subtitle_hint():
    code, name = resolve_source_language("sample text", subtitle_lang="pl")
    assert code == "pl"
    assert name == "Polish"


def test_lang_display_name():
    assert lang_display_name("pl") == "Polish"
    assert lang_display_name("el") == "Greek"
