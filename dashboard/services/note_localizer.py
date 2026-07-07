"""Localize rendered markdown notes for dashboard UI language (el/en)."""
from __future__ import annotations

import re

from utils.topic_hierarchy import cluster_display_label, theme_display_title

# Markdown section headers — bidirectional
_SECTION_EL_TO_EN: dict[str, str] = {
    "Περίληψη": "Summary",
    "Σύνοψη": "Summary",
    "Κύριες Ιδέες": "Key Ideas",
    "Κύριες ιδέες": "Key Ideas",
    "Συμβουλές & Ενέργειες": "Takeaways & Action Items",
    "Σημαντικές Παραθέσεις": "Notable Quotes",
    "Σχετικές Έννοιες": "Related Concepts",
    "Σχετικές έννοιες": "Related Concepts",
    "Σχετικοί Όροι": "Related Concepts",
    "Βασικά Στιγμιότυπα": "Key Visuals",
    "Επισκόπηση": "Overview",
    "Κύριες γραμμές": "Key threads",
    "Καλύτερα σημεία εκκίνησης": "Best starting points",
    "Υποθέματα": "Subtopics",
    "Σχετικά υποθέματα": "Related subtopics",
    "Επεισόδια": "Episodes",
    "Βίντεο": "Videos",
    "Σχετικά θέματα": "Related topics",
    "Σχετικές θεματικές": "Related themes",
    "Ξεκίνα εδώ": "Start here",
    "Δομή": "Structure",
    "Συμβουλές": "Tips",
    "Περιγραφή": "Description",
    "Θεματικές & topics": "Themes & topics",
}

_SECTION_EN_TO_EL: dict[str, str] = {v: k for k, v in _SECTION_EL_TO_EN.items()}
# Prefer shorter Greek labels where duplicates exist
_SECTION_EN_TO_EL.update(
    {
        "Summary": "Περίληψη",
        "Key Ideas": "Κύριες Ιδέες",
        "Takeaways & Action Items": "Συμβουλές & Ενέργειες",
        "Notable Quotes": "Σημαντικές Παραθέσεις",
        "Related Concepts": "Σχετικές Έννοιες",
        "Key Visuals": "Βασικά Στιγμιότυπα",
        "Videos": "Βίντεο",
    }
)

_INLINE_EL_TO_EN: dict[str, str] = {
    "Θεματική:": "Theme:",
    "υποθέματα": "subtopics",
    "υποθέμα": "subtopic",
    "επεισόδια": "episodes",
    "επεισόδιο": "episode",
    "βίντεο": "videos",
    "βίντεό": "videos",
    "Δες": "Watch",
    "Παρακολούθηση": "Watch",
}

_INLINE_EN_TO_EL: dict[str, str] = {
    "Theme:": "Θεματική:",
    "Watch": "Δες",
    "subtopics": "υποθέματα",
    "subtopic": "υποθέμα",
    "episodes": "επεισόδια",
    "episode": "επεισόδιο",
    "videos": "βίντεο",
}

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_WIKILINK_THEME_RE = re.compile(
    r"\[\[Topics/([^|\]#]+)(?:\|([^\]]*))?\]\]",
    re.IGNORECASE,
)


def _swap_sections(text: str, mapping: dict[str, str]) -> str:
    def repl(m: re.Match[str]) -> str:
        hashes, title = m.group(1), m.group(2).strip()
        new_title = mapping.get(title, title)
        return f"{hashes} {new_title}"

    return _HEADER_RE.sub(repl, text)


def _swap_inline(text: str, mapping: dict[str, str]) -> str:
    out = text
    for src, tgt in sorted(mapping.items(), key=lambda x: -len(x[0])):
        out = out.replace(src, tgt)
    return out


def _localize_theme_wikilinks(text: str, lang: str) -> str:
    def repl(m: re.Match[str]) -> str:
        slug = m.group(1).strip()
        alias = (m.group(2) or "").strip()
        display = theme_display_title(slug.replace(".md", ""), lang)
        if "/" in slug:
            parts = slug.split("/")
            if len(parts) >= 2 and parts[0] == "Topics":
                if len(parts) == 2:
                    display = theme_display_title(parts[1], lang)
                elif len(parts) == 3:
                    display = cluster_display_label(parts[2], lang)
        label = alias if alias and lang == "el" else display
        if alias and lang == "en":
            label = display
        return f"[[Topics/{slug}|{label}]]"

    return _WIKILINK_THEME_RE.sub(repl, text)


def localize_markdown(content: str, lang: str = "el") -> str:
    """Return markdown with section headers and theme links localized for UI lang."""
    ui = "en" if lang == "en" else "el"
    if ui == "en":
        text = _swap_sections(content, _SECTION_EL_TO_EN)
        text = _swap_inline(text, _INLINE_EL_TO_EN)
    else:
        text = _swap_sections(content, _SECTION_EN_TO_EL)
        text = _swap_inline(text, _INLINE_EN_TO_EL)
    return _localize_theme_wikilinks(text, ui)


def localized_title(title: str, path: str, lang: str = "el") -> str:
    """Theme/subtopic display title for note lists."""
    ui = "en" if lang == "en" else "el"
    if path.startswith("Topics/"):
        parts = path.replace(".md", "").split("/")
        if len(parts) == 2:
            return theme_display_title(parts[1], ui)
        if len(parts) == 3:
            return cluster_display_label(parts[2], ui)
        if len(parts) >= 4:
            return parts[-1]
    return title
