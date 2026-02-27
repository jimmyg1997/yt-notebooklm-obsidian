"""Obsidian vault writer: one note per video + MOC index + NotebookLM artifacts reference."""
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from utils.logger import setup_logger

load_dotenv()
from utils.note_formatter import format_note, safe_filename

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ENRICHED_DIR = DATA_DIR / "enriched"
MANIFEST_PATH = DATA_DIR / "manifest.json"
NOTEBOOKLM_OUTPUTS = DATA_DIR / "notebooklm_outputs"
LOCAL_EXPORT_DIR = DATA_DIR / "obsidian_export"  # used when no Obsidian vault configured


def _playlist_slug(playlist_title: str) -> str:
    """Safe tag from playlist title."""
    s = re.sub(r"[^\w\s-]", "", playlist_title)
    return re.sub(r"[-\s]+", "-", s).strip().lower() or "playlist"


def _mindmap_to_markdown(data: dict, indent: int = 0) -> str:
    """Turn NotebookLM mindmap.json (name/children) into a Markdown outline."""
    lines = []
    name = data.get("name", "")
    if name:
        lines.append("  " * indent + "- " + name)
    for child in data.get("children", []):
        lines.append(_mindmap_to_markdown(child, indent + 1))
    return "\n".join(lines) if lines else ""


def _is_vault_configured(vault_path: str) -> bool:
    """True if user has set a real Obsidian vault path (not empty or example placeholder)."""
    if not vault_path:
        return False
    # Example from .env.example uses /Users/yourname/...
    if "yourname" in vault_path or vault_path == "/Users/yourname/Obsidian/MyVault":
        return False
    return True


def run_obsidian_agent(manifest: dict | None = None) -> dict:
    """
    Write Obsidian notes for each enriched video and a MOC index.
    If OBSIDIAN_VAULT_PATH is set to a real path, writes there; otherwise writes to ./data/obsidian_export/
    so you get all markdown files without needing Obsidian. You can open that folder in Obsidian later if you want.
    """
    logger = setup_logger()
    vault_path = os.environ.get("OBSIDIAN_VAULT_PATH", "").strip()
    subfolder = os.environ.get("OBSIDIAN_SUBFOLDER", "YouTube Playlists").strip()

    if _is_vault_configured(vault_path):
        out_dir = Path(vault_path) / subfolder
        logger.info("Writing notes to Obsidian vault: %s", out_dir)
    else:
        out_dir = LOCAL_EXPORT_DIR / subfolder
        logger.info(
            "OBSIDIAN_VAULT_PATH not set or still the example path — writing notes to %s (no Obsidian needed)",
            out_dir,
        )

    if manifest is None:
        if not MANIFEST_PATH.exists():
            raise FileNotFoundError(f"Manifest not found: {MANIFEST_PATH}. Run transcript agent first.")
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    playlist_title = manifest.get("playlist_title", "YouTube Playlist")
    notebook_id = manifest.get("notebooklm_notebook_id", "")
    playlist_slug = _playlist_slug(playlist_title)

    out_dir.mkdir(parents=True, exist_ok=True)
    notebooklm_subdir = out_dir / "notebooklm"
    notebooklm_subdir.mkdir(parents=True, exist_ok=True)

    # Copy NotebookLM artifacts into vault subfolder if they exist
    for name in ["podcast.mp3", "mindmap.json", "quiz.json", "flashcards.json"]:
        src = NOTEBOOKLM_OUTPUTS / name
        if src.exists():
            dest = notebooklm_subdir / name
            try:
                dest.write_bytes(src.read_bytes())
            except Exception as e:
                logger.warning("Could not copy %s: %s", name, e)

    # Write a readable "NotebookLM Artifacts" note explaining how to use each file + mind map outline
    try:
        artifact_note_lines = [
            "# NotebookLM Artifacts",
            "",
            "This folder contains outputs from **NotebookLM** (audio overview, mind map, quiz, flashcards).",
            "",
            "## How to use",
            "",
            "| File | What it is | How to use in Obsidian |",
            "|------|------------|------------------------|",
            "| [podcast.mp3](./podcast.mp3) | Audio overview of the whole playlist | Click the link to play in Obsidian or your system player.",
            "| [Mind Map (outline below)](./mindmap.json) | NotebookLM’s topic tree | Read the outline in this note; raw data is in `mindmap.json`.",
            "| [quiz.json](./quiz.json) | Quiz questions (JSON) | Open in a text editor or a quiz plugin; or use in [NotebookLM](https://notebooklm.google.com).",
            "| [flashcards.json](./flashcards.json) | Flashcards (JSON) | Open in a flashcard plugin (e.g. **Obsidian Flashcards**) or in NotebookLM.",
            "",
            "---",
            "",
            "## Mind map (outline)",
            "",
        ]
        mindmap_src = NOTEBOOKLM_OUTPUTS / "mindmap.json"
        if mindmap_src.exists():
            try:
                mm = json.loads(mindmap_src.read_text(encoding="utf-8"))
                artifact_note_lines.append(_mindmap_to_markdown(mm))
                artifact_note_lines.append("")
            except Exception as e:
                logger.warning("Could not parse mind map for outline: %s", e)
                artifact_note_lines.append("*Could not parse mindmap.json.*")
        else:
            artifact_note_lines.append("*Run the NotebookLM step to generate the mind map.*")
        (notebooklm_subdir / "NotebookLM Artifacts.md").write_text(
            "\n".join(artifact_note_lines), encoding="utf-8"
        )
    except Exception as e:
        logger.warning("Could not write NotebookLM Artifacts note: %s", e)

    enriched_files = list(ENRICHED_DIR.glob("*.json"))
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.console import Console
    console = Console()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
    ) as progress:
        task = progress.add_task("Writing Obsidian notes...", total=len(enriched_files))
        for i, path in enumerate(sorted(enriched_files), 1):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Skip %s: %s", path.name, e)
                progress.advance(task)
                continue

            title = data.get("title", "Unknown")
            video_id = data.get("video_id", "")
            url = data.get("url", f"https://www.youtube.com/watch?v={video_id}")
            uploader = data.get("uploader", "")
            duration_raw = data.get("duration", 0)
            duration = str(duration_raw) if isinstance(duration_raw, (int, float)) else duration_raw
            if isinstance(duration_raw, (int, float)) and duration_raw:
                m, s = divmod(int(duration_raw), 60)
                duration = f"{m}:{s:02d}"
            upload_date = data.get("upload_date", "")
            gemini_notes = data.get("gemini_notes", "")

            body = format_note(
                title=title,
                playlist_title=playlist_title,
                url=url,
                video_id=video_id,
                uploader=uploader,
                upload_date=upload_date,
                duration=duration,
                notebook_id=notebook_id,
                gemini_notes=gemini_notes,
                playlist_slug=playlist_slug,
            )
            filename = safe_filename(i, title)
            note_path = out_dir / filename
            note_path.write_text(body, encoding="utf-8")
            progress.advance(task)

    # MOC index note
    index_lines = [
        "# " + playlist_title + " — Index",
        "",
        "> 50 videos | NotebookLM notebook id: `" + notebook_id + "`",
        "",
        "## Videos",
        "",
    ]
    for i, path in enumerate(sorted(enriched_files), 1):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            title = data.get("title", "Unknown")
            filename = safe_filename(i, title)
            index_lines.append(f"- ✅ [[{filename.replace('.md', '')}|{i}. {title}]]")
        except Exception:
            index_lines.append(f"- ❌ {i}. (read error)")
    index_lines.extend([
        "",
        "## NotebookLM Artifacts",
        "",
        "- 🎧 [Audio Overview](./notebooklm/podcast.mp3)",
        "- 📄 [NotebookLM Artifacts (how to use)](./notebooklm/NotebookLM%20Artifacts.md) — podcast, mind map outline, quiz, flashcards",
        "- 🧠 [Mind Map (raw)](./notebooklm/mindmap.json) · 📝 [Quiz](./notebooklm/quiz.json) · 🃏 [Flashcards](./notebooklm/flashcards.json)",
        "",
    ])
    index_path = out_dir / "00 - Index.md"
    index_path.write_text("\n".join(index_lines), encoding="utf-8")

    logger.info("Obsidian agent finished. Notes in %s", out_dir)
    return manifest
