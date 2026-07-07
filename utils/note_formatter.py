"""Obsidian markdown formatter with YAML frontmatter."""
import re
from datetime import date
from typing import Any

from utils.language_utils import lang_display_name, note_language_footer


def safe_filename(index: int, title: str, max_len: int = 80) -> str:
    """Build a safe filename: '01 - Title Here.md'."""
    safe = re.sub(r'[\\/*?:"<>|]', "", title)
    safe = re.sub(r"\s+", " ", safe).strip()
    return f"{index:02d} - {safe[:max_len]}.md"


def safe_concept_filename(concept: str, max_len: int = 80) -> str:
    """Safe filename for a topic/concept note (e.g. 'Online Marketing.md')."""
    safe = re.sub(r'[\\/*?:"<>|]', "-", concept)
    safe = re.sub(r"\s+", " ", safe).strip()
    safe = re.sub(r"-+", "-", safe).strip("-")
    return (safe[:max_len] or "Unnamed").strip() + ".md"


def format_key_visuals_section(frames: list[dict], video_id: str) -> str:
    """Markdown gallery: each screenshot paired with transcript text at that moment."""
    if not frames:
        return ""
    lines = ["## Key visuals", "", "*Each frame is paired with what is being said at that timestamp.*", ""]
    for f in frames:
        rel = f.get("rel_path") or f"assets/{video_id}/{f.get('filename', 'frame.jpg')}"
        caption = f.get("caption") or "Screenshot"
        ts = f.get("timestamp_label") or ""
        excerpt = (f.get("transcript_excerpt") or "").strip()
        lines.append(f"### {caption}" + (f" `{ts}`" if ts else ""))
        lines.append("")
        lines.append(f"![{caption}]({rel})")
        lines.append("")
        if excerpt:
            lines.append(f"> {excerpt}")
        else:
            lines.append(f"*{caption}*")
        lines.append("")
    return "\n".join(lines)


def format_transcript_section(transcript: str) -> str:
    """Full transcript appendix (collapsible in Obsidian)."""
    text = (transcript or "").strip()
    if not text:
        return ""
    return f"""## Full transcript

<details>
<summary>Show full transcript</summary>

{text}

</details>
"""


def format_note(
    title: str,
    playlist_title: str,
    url: str,
    video_id: str,
    uploader: str,
    upload_date: Any,
    duration: str,
    notebook_id: str,
    gemini_notes: str,
    playlist_slug: str,
    output_language: str = "english",
    key_visuals: str = "",
    source_language: str = "",
    source_language_name: str = "",
    subtitle_lang: str = "",
    transcript: str = "",
) -> str:
    """Produce a full Obsidian note with YAML frontmatter and gemini content."""
    today = date.today().isoformat()
    date_str = upload_date if isinstance(upload_date, str) else str(upload_date)
    lang = (output_language or "english").strip().lower()
    if lang not in ("english", "greek"):
        lang = "english"

    src_code = (source_language or subtitle_lang or "").strip().lower()
    src_name = source_language_name or lang_display_name(src_code)
    note_lang_label = "Greek" if lang == "greek" else "English"
    lang_line = ""
    if src_name and src_name != "Unknown":
        lang_line = f" | 🌐 Original: {src_name} → Notes: {note_lang_label}"

    frontmatter = f"""---
title: "{title.replace('"', '\\"')}"
source: youtube
playlist: "{playlist_title.replace('"', '\\"')}"
url: "{url}"
video_id: "{video_id}"
uploader: "{uploader.replace('"', '\\"')}"
upload_date: {date_str}
duration: "{duration}"
note_language: {lang}
transcript_language: {src_code or "unknown"}
transcript_language_name: "{src_name.replace('"', '\\"')}"
subtitle_language: {subtitle_lang or src_code or "unknown"}
processed: {today}
notebooklm_notebook: "{notebook_id}"
tags:
  - youtube
  - {lang}
  - {playlist_slug}
  - inbox
---

# {title}

> 🎥 [Watch]({url}) | ⏱ {duration} | 📅 {date_str} | 👤 {uploader}{lang_line}

---

{gemini_notes}
"""
    transcript_block = format_transcript_section(transcript)
    if key_visuals.strip():
        frontmatter += f"\n---\n\n{key_visuals.strip()}\n"
    if transcript_block.strip():
        frontmatter += f"\n---\n\n{transcript_block.strip()}\n"
    frontmatter += f"\n---\n{note_language_footer(src_code, src_name, lang)}\n"
    return frontmatter
