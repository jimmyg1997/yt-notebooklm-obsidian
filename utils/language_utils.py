"""Language detection and subtitle-language selection for multilingual YouTube ingest."""
from __future__ import annotations

import os
from typing import Any

# ISO 639-1 (+ common YouTube variants) → English display name
LANG_NAMES: dict[str, str] = {
    "el": "Greek",
    "en": "English",
    "en-us": "English (US)",
    "en-gb": "English (UK)",
    "pl": "Polish",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "pt-br": "Portuguese (Brazil)",
    "ru": "Russian",
    "uk": "Ukrainian",
    "nl": "Dutch",
    "sv": "Swedish",
    "no": "Norwegian",
    "da": "Danish",
    "fi": "Finnish",
    "cs": "Czech",
    "sk": "Slovak",
    "hu": "Hungarian",
    "ro": "Romanian",
    "bg": "Bulgarian",
    "tr": "Turkish",
    "ar": "Arabic",
    "he": "Hebrew",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "zh-hans": "Chinese (Simplified)",
    "zh-hant": "Chinese (Traditional)",
    "hi": "Hindi",
}

# Fallback order when video metadata does not list subtitles
SUBTITLE_LANGS_FALLBACK = ["en", "en-US", "el", "pl", "de", "fr", "es", "it", "pt", "ru", "uk"]


def normalize_lang_code(lang: str | None) -> str:
    """Normalize YouTube lang codes to lowercase base or region form."""
    if not lang:
        return ""
    code = lang.strip().lower().replace("_", "-")
    # yt-dlp sometimes returns "english" etc.
    aliases = {
        "english": "en",
        "greek": "el",
        "polish": "pl",
        "german": "de",
        "french": "fr",
        "spanish": "es",
    }
    if code in aliases:
        return aliases[code]
    return code


def lang_display_name(code: str | None) -> str:
    """Human-readable language name for notes and prompts."""
    norm = normalize_lang_code(code)
    if not norm:
        return "Unknown"
    if norm in LANG_NAMES:
        return LANG_NAMES[norm]
    base = norm.split("-")[0]
    if base in LANG_NAMES:
        return LANG_NAMES[base]
    return norm.upper()


def subtitle_langs_from_info(info: dict[str, Any] | None) -> list[str]:
    """Collect manual + automatic caption languages from yt-dlp info."""
    if not info:
        return []
    manual = list((info.get("subtitles") or {}).keys())
    auto = list((info.get("automatic_captions") or {}).keys())
    out: list[str] = []
    seen: set[str] = set()
    for lang in manual + auto:
        code = normalize_lang_code(lang)
        if code and code not in seen:
            seen.add(code)
            out.append(code)
    return out


def build_subtitle_lang_order(title: str = "", info: dict[str, Any] | None = None) -> list[str]:
    """
    Build subtitle download order: video metadata first, then manual subs,
    then auto-captions, then sensible fallbacks (en, pl, el, …).
    """
    order: list[str] = []
    seen: set[str] = set()

    def add(lang: str | None) -> None:
        code = normalize_lang_code(lang)
        if not code or code in seen:
            return
        seen.add(code)
        order.append(code)

    meta_lang = ""
    if info:
        meta_lang = normalize_lang_code(info.get("language") or info.get("original_language") or "")
        if meta_lang:
            add(meta_lang)

        manual = sorted((info.get("subtitles") or {}).keys())
        auto = sorted((info.get("automatic_captions") or {}).keys())

        def sort_key(lang: str) -> tuple[int, str]:
            code = normalize_lang_code(lang)
            return (0 if code == meta_lang else 1, code)

        for lang in sorted(manual, key=sort_key):
            add(lang)
        for lang in sorted(auto, key=sort_key):
            add(lang)

    if title:
        ascii_chars = sum(1 for c in title if ord(c) < 128)
        if ascii_chars / max(len(title), 1) > 0.85:
            for code in ("en", "en-us"):
                add(code)

    env_langs = os.environ.get("SUBTITLE_LANGS", "").strip()
    if env_langs:
        for part in env_langs.split(","):
            add(part.strip())

    for code in SUBTITLE_LANGS_FALLBACK:
        add(code)

    return order[:14]


def detect_text_language(text: str, hint: str | None = None) -> str:
    """Heuristic language detection from transcript text (no extra deps)."""
    hint_code = normalize_lang_code(hint)
    sample = (text or "")[:8000]
    if not sample.strip():
        return hint_code or "unknown"

    greek = sum(1 for c in sample if "\u0370" <= c <= "\u03ff" or "\u1f00" <= c <= "\u1fff")
    polish_chars = set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")
    polish = sum(1 for c in sample if c in polish_chars)
    cyrillic = sum(1 for c in sample if "\u0400" <= c <= "\u04ff")
    total_alpha = sum(1 for c in sample if c.isalpha())
    if total_alpha == 0:
        return hint_code or "unknown"

    if greek / total_alpha > 0.12:
        return "el"
    if polish >= 2 or polish / total_alpha > 0.008:
        return "pl"
    if cyrillic / total_alpha > 0.12:
        return "ru"

    if hint_code:
        return hint_code
    return "en"


def resolve_source_language(
    transcript: str,
    *,
    subtitle_lang: str | None = None,
    video_lang: str | None = None,
) -> tuple[str, str]:
    """Return (iso_code, display_name) for the spoken/subtitle language."""
    hint = subtitle_lang or video_lang
    code = detect_text_language(transcript, hint)
    if code == "unknown" and hint:
        code = normalize_lang_code(hint) or "unknown"
    return code, lang_display_name(code)


def enrichment_instructions(
    output_lang: str,
    source_lang: str,
    source_name: str,
) -> tuple[str, str]:
    """
    Return (language_instruction, quote_instruction) for the LLM enrichment prompt.
    Always translates when source ≠ output language.
    """
    out = (output_lang or "english").strip().lower()
    if out not in ("english", "greek"):
        out = "english"

    src = normalize_lang_code(source_lang) or "unknown"
    src_name = source_name or lang_display_name(src)

    def same_language() -> bool:
        if out == "greek" and src in ("el", "gr"):
            return True
        if out == "english" and src in ("en", "en-us", "en-gb"):
            return True
        return normalize_lang_code(out) == src

    if out == "greek":
        if same_language():
            lang_inst = (
                f"The transcript is in {src_name}. Respond entirely in Greek "
                "(summary, key ideas, takeaways, quotes, and [[wikilinks]] in Greek)."
            )
            quote_inst = "Keep quotes in Greek."
        else:
            lang_inst = (
                f"The transcript is in {src_name}. Translate everything into Greek: "
                "summary, key ideas, takeaways, notable quotes, and [[wikilinks]] "
                "(Greek concept names)."
            )
            quote_inst = "Translate quotes to Greek; add the original in parentheses only if the wording is iconic."
    else:
        if same_language():
            lang_inst = (
                f"The transcript is in {src_name}. Respond entirely in English "
                "(summary, key ideas, takeaways, quotes, and [[wikilinks]] in English)."
            )
            quote_inst = "Keep quotes in English."
        else:
            lang_inst = (
                f"The transcript is in {src_name}. Translate everything into English: "
                "summary, key ideas, takeaways, notable quotes, and [[wikilinks]] "
                "(English concept names)."
            )
            quote_inst = "Translate quotes to English."

    return lang_inst, quote_inst


def note_language_footer(
    source_lang: str,
    source_name: str,
    output_lang: str,
) -> str:
    """Footer line for generated Obsidian notes."""
    out = (output_lang or "english").strip().lower()
    out_label = "Greek" if out == "greek" else "English"
    src_name = source_name or lang_display_name(source_lang)
    return (
        f"*Generated from **{src_name}** transcript → **{out_label}** notes.*"
    )
