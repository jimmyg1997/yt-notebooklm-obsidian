"""Extract [[wikilink]] concepts from enriched content and build concept→videos map."""
import json
import re
from pathlib import Path
from typing import Any


WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")


def extract_wikilinks(text: str) -> list[str]:
    """Return unique concept names from text containing [[Concept]] or [[Concept|alias]]."""
    if not text:
        return []
    names = [m.group(1).strip() for m in WIKILINK_RE.finditer(text)]
    seen = set()
    out = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def get_concepts_from_enriched(data: dict) -> list[str]:
    """Get list of concept names from one enriched JSON (gemini_sections or gemini_notes)."""
    sections = data.get("gemini_sections") or {}
    related = (
        sections.get("Related Concepts")
        or sections.get("Σχετικές Έννοιες")
        or sections.get("Σχετικές έννοιες")
        or sections.get("Σχετικοί Όροι")
        or sections.get("Σχετικοί όροι")
        or ""
    )
    concepts = extract_wikilinks(related)
    if not concepts:
        concepts = extract_wikilinks(data.get("gemini_notes") or "")
    return concepts


def summary_one_liner(data: dict, max_len: int = 200) -> str:
    """First sentence of Summary section, or first line of Key Ideas; capped length."""
    sections = data.get("gemini_sections") or {}
    summary = (
        (sections.get("Summary") or sections.get("Περίληψη") or "").strip()
    )
    if summary:
        first = summary.split(". ")[0].strip()
        if not first.endswith("."):
            first += "."
        return (first[: max_len - 1] + "…") if len(first) > max_len else first
    key_ideas = (
        (sections.get("Key Ideas") or sections.get("Κύριες Ιδέες") or "").strip().split("\n")[0].strip()
    )
    if key_ideas:
        return (key_ideas[: max_len - 1] + "…") if len(key_ideas) > max_len else key_ideas
    return ""


def build_concept_to_videos(
    enriched_paths: list[Path],
    safe_filename_fn,
) -> tuple[dict[str, list[tuple[str, str, str]]], dict[str, set[str]]]:
    """
    Build concept -> list of (video_note_link, title, one_liner) and concept -> set of co-occurring concepts.
    safe_filename_fn(i, title) -> filename like "01 - Title.md".
    Returns (concept_to_videos, concept_to_related_concepts for co-occurrence).
    """
    concept_to_videos: dict[str, list[tuple[str, str, str]]] = {}
    concept_to_related: dict[str, set[str]] = {}  # other concepts that appear in same videos

    for i, path in enumerate(enriched_paths, 1):
        try:
            data = _load_json(path)
        except Exception:
            continue
        title = data.get("title", "Unknown")
        filename = safe_filename_fn(i, title)
        note_name = filename.replace(".md", "")
        one_liner = summary_one_liner(data)
        concepts = get_concepts_from_enriched(data)
        for c in concepts:
            concept_to_videos.setdefault(c, []).append((note_name, title, one_liner))
            concept_to_related.setdefault(c, set()).update(x for x in concepts if x != c)
        # Also ensure every concept has a set (even if empty)
        for c in concepts:
            if c not in concept_to_related:
                concept_to_related[c] = set()

    return concept_to_videos, concept_to_related


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
