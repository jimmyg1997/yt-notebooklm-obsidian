"""Write a single enriched video note into an existing vault."""
from __future__ import annotations

import json
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from dashboard.services.topic_sync import sync_topics_after_ingest
from dashboard.services.vault_factory import read_vault_meta
from utils.note_formatter import format_key_visuals_section, format_note, safe_filename

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INDEX_NOTE = "00 - Index.md"
_PREFIX_RE = re.compile(r"^(\d{2,3})\s*-\s*.+\.md$", re.IGNORECASE)


def _playlist_slug(name: str) -> str:
    s = re.sub(r"[^\w\s-]", "", name or "single-video")
    return re.sub(r"[-\s]+", "-", s).strip().lower() or "single-video"


def resolve_data_dir_for_vault(vault_path: Path) -> Path:
    """Pipeline data dir: sibling of vault/ for experiments, else .dashboard/ingest/."""
    vault_path = vault_path.resolve()
    if vault_path.name == "vault" and (PROJECT_ROOT / "data") in vault_path.parents:
        return vault_path.parent
    slug = re.sub(r"[^\w-]", "-", vault_path.name.lower())[:48] or "vault"
    ingest = PROJECT_ROOT / ".dashboard" / "ingest" / slug
    ingest.mkdir(parents=True, exist_ok=True)
    return ingest


def next_note_index(vault_dir: Path) -> int:
    """Next NN prefix for numbered episode notes in vault root."""
    max_n = 0
    for p in vault_dir.glob("*.md"):
        m = _PREFIX_RE.match(p.name)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def find_note_by_video_id(vault_dir: Path, video_id: str) -> Path | None:
    for p in vault_dir.glob("*.md"):
        if p.name.startswith("00 -"):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if f'video_id: "{video_id}"' in text or f"video_id: {video_id}" in text:
            return p
    return None


def append_to_index(vault_dir: Path, note_stem: str, title: str, index_num: int) -> None:
    index_path = vault_dir / INDEX_NOTE
    if not index_path.exists():
        return
    line = f"- ✅ [[{note_stem}|{index_num}. {title}]]"
    content = index_path.read_text(encoding="utf-8")
    if note_stem in content or f"|{index_num}. {title}]]" in content:
        return
    marker = "## Videos"
    if marker in content:
        parts = content.split(marker, 1)
        rest = parts[1]
        insert_at = rest.find("\n## ")
        if insert_at == -1:
            new_rest = rest.rstrip() + "\n" + line + "\n"
        else:
            new_rest = rest[:insert_at].rstrip() + "\n" + line + "\n" + rest[insert_at:]
        index_path.write_text(parts[0] + marker + new_rest, encoding="utf-8")
    else:
        index_path.write_text(content.rstrip() + f"\n\n## Videos\n\n{line}\n", encoding="utf-8")


def write_single_video_note(
    vault_dir: Path,
    enriched_path: Path,
    frames: list[dict],
    *,
    output_language: str = "english",
) -> dict:
    """Create or update one video note in vault_dir. Returns {path, title, created}."""
    import os

    data = json.loads(enriched_path.read_text(encoding="utf-8"))
    title = data.get("title", "Unknown")
    video_id = data.get("video_id", "")
    url = data.get("url", f"https://www.youtube.com/watch?v={video_id}")
    uploader = data.get("uploader", "")
    duration_raw = data.get("duration", 0)
    if isinstance(duration_raw, (int, float)) and duration_raw:
        m, s = divmod(int(duration_raw), 60)
        duration = f"{m}:{s:02d}"
    else:
        duration = str(duration_raw)
    upload_date = data.get("upload_date", "")
    gemini_notes = data.get("gemini_notes", "")
    playlist_title = data.get("playlist_title") or "Single video ingest"
    playlist_slug = _playlist_slug(playlist_title)
    output_lang = (output_language or os.environ.get("OUTPUT_LANGUAGE") or "english").strip().lower()

    key_visuals = format_key_visuals_section(frames, video_id)
    body = format_note(
        title=title,
        playlist_title=playlist_title,
        url=url,
        video_id=video_id,
        uploader=uploader,
        upload_date=upload_date,
        duration=duration,
        notebook_id="",
        gemini_notes=gemini_notes,
        playlist_slug=playlist_slug,
        output_language=output_lang,
        key_visuals=key_visuals,
        source_language=data.get("source_language", ""),
        source_language_name=data.get("source_language_name", ""),
        subtitle_lang=data.get("subtitle_lang", ""),
        transcript=data.get("transcript", ""),
    )

    existing = find_note_by_video_id(vault_dir, video_id)
    created = existing is None
    if existing:
        note_path = existing
        index_num = 0
        if m := _PREFIX_RE.match(existing.name):
            index_num = int(m.group(1))
    else:
        index_num = next_note_index(vault_dir)
        filename = safe_filename(index_num, title)
        note_path = vault_dir / filename

    note_path.write_text(body, encoding="utf-8")
    if created:
        append_to_index(vault_dir, note_path.stem, title, index_num)

    meta = read_vault_meta(vault_dir) or {}
    vault_name = meta.get("name") or playlist_title
    themes = meta.get("themes") or []
    try:
        sync_topics_after_ingest(
            vault_dir,
            enriched_path,
            note_path.stem,
            vault_name=vault_name,
            vault_themes=themes,
        )
    except Exception:
        pass  # topic sync must not fail the ingest

    return {
        "path": note_path.relative_to(vault_dir).as_posix(),
        "title": title,
        "video_id": video_id,
        "created": created,
        "screenshots": len(frames),
    }
