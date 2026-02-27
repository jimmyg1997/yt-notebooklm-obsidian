"""Obsidian markdown formatter with YAML frontmatter."""
import re
from datetime import date
from typing import Any


def safe_filename(index: int, title: str, max_len: int = 80) -> str:
    """Build a safe filename: '01 - Title Here.md'."""
    safe = re.sub(r'[\\/*?:"<>|]', "", title)
    safe = re.sub(r"\s+", " ", safe).strip()
    return f"{index:02d} - {safe[:max_len]}.md"


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
) -> str:
    """Produce a full Obsidian note with YAML frontmatter and gemini content."""
    today = date.today().isoformat()
    date_str = upload_date if isinstance(upload_date, str) else str(upload_date)

    frontmatter = f"""---
title: "{title.replace('"', '\\"')}"
source: youtube
playlist: "{playlist_title.replace('"', '\\"')}"
url: "{url}"
video_id: "{video_id}"
uploader: "{uploader.replace('"', '\\"')}"
upload_date: {date_str}
duration: "{duration}"
language: greek
processed: {today}
notebooklm_notebook: "{notebook_id}"
tags:
  - youtube
  - greek
  - {playlist_slug}
  - inbox
---

# {title}

> 🎥 [Watch]({url}) | ⏱ {duration} | 📅 {date_str} | 👤 {uploader}

---

{gemini_notes}

---
*Auto-generated from Greek transcript using AI (OpenAI or Gemini)*
"""
    return frontmatter
