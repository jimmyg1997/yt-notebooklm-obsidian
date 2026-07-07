"""Obsidian vault writer: one note per video + MOC index + NotebookLM artifacts reference."""
import json
import os
import re
import shutil
import time
from pathlib import Path

from dotenv import load_dotenv
from utils.logger import setup_logger

load_dotenv()
from utils.concept_utils import build_concept_to_videos
from utils.note_formatter import format_note, safe_filename, safe_concept_filename

_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


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


# Categories for master topic index (hierarchy above individual topics)
TOPIC_CATEGORIES = [
    "Marketing & Sales",
    "Personal Development",
    "Finance & Investing",
    "Leadership & Management",
    "Health & Wellness",
    "Technology & Innovation",
    "Career & Skills",
    "Psychology & Mindset",
    "Ethics & Society",
    "Other",
]


def _generate_topic_summary(
    concept: str,
    mentions: list[tuple[str, str, str]],
    output_language: str,
    logger,
    max_mentions: int = 15,
) -> str:
    """Generate 2–4 paragraphs of explanatory text about the concept using LLM (Gemini or OpenAI)."""
    if not mentions:
        return ""
    lang_instruction = "Write in Greek." if output_language == "greek" else "Write in English."
    # Build context from episode one-liners (cap to avoid token overflow)
    sample = mentions[:max_mentions]
    context_lines = [f"- {title}: {one_liner}" for (_, title, one_liner) in sample if title]
    if len(mentions) > max_mentions:
        context_lines.append(f"(… and {len(mentions) - max_mentions} more episodes)")
    context = "\n".join(context_lines)
    prompt = f"""You are writing the "About this topic" section for a knowledge-base note. The concept is: "{concept}".

This concept appears in the following video summaries from a YouTube playlist:
{context}

Write 2–4 short paragraphs that explain what "{concept}" is and why it matters in this context. Use a neutral, informative tone. Do NOT list the videos or repeat the list above — that is in another section. Just give the reader something useful to read when they open this topic note.
{lang_instruction}

Output only the paragraphs, no heading and no markdown formatting."""
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    try:
        if openai_key and "your_openai" not in openai_key.lower():
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            r = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
            )
            text = (r.choices[0].message.content or "").strip()
        elif gemini_key:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            resp = model.generate_content(prompt)
            text = (getattr(resp, "text", None) or "").strip()
        else:
            logger.warning("No API key for topic summary; skipping explanatory text")
            return ""
        return text if text else ""
    except Exception as e:
        logger.warning("Topic summary failed for %s: %s", concept[:50], e)
        return ""


def _topic_summary_delay() -> None:
    """Sleep between topic summary API calls to avoid rate limits."""
    try:
        delay = float(os.environ.get("API_DELAY_SECONDS", "2"))
        if delay > 0:
            time.sleep(delay)
    except (TypeError, ValueError):
        time.sleep(1)


def _assign_concept_categories(concepts: list[str], logger) -> dict[str, str]:
    """Assign each concept to one category (LLM or fallback to Other)."""
    if not concepts:
        return {}
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    categories_str = ", ".join(TOPIC_CATEGORIES)
    prompt = f"""Assign each concept to exactly ONE of these categories: {categories_str}.
Concepts: {chr(10).join('- ' + c for c in concepts)}
Reply with a JSON object only, no markdown: {{"Concept Name": "Category Name", ...}}"""
    try:
        if openai_key and "your_openai" not in openai_key.lower():
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            r = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
            )
            text = (r.choices[0].message.content or "").strip()
        elif gemini_key:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            resp = model.generate_content(prompt)
            text = (getattr(resp, "text", None) or "").strip()
        else:
            raise ValueError("No API key")
        # Strip markdown code block if present
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text).rstrip("`").strip()
        mapping = json.loads(text)
        out = {}
        for c in concepts:
            out[c] = mapping.get(c) if isinstance(mapping.get(c), str) else "Other"
            if out[c] not in TOPIC_CATEGORIES:
                out[c] = "Other"
        return out
    except Exception as e:
        logger.warning("Category assignment failed (%s), using Other for all", e)
        return {c: "Other" for c in concepts}


def _is_vault_configured(vault_path: str) -> bool:
    """True if user has set a real Obsidian vault path (not empty or example placeholder)."""
    if not vault_path:
        return False
    # Example from .env.example uses /Users/yourname/...
    if "yourname" in vault_path or vault_path == "/Users/yourname/Obsidian/MyVault":
        return False
    return True


def run_obsidian_agent(manifest: dict | None = None, data_dir: Path | None = None) -> dict:
    """
    Write Obsidian notes into the experiment folder so everything stays in one place.
    Notes go to data_dir/vault/ (e.g. data/metabolomic-medicine/vault/). If OBSIDIAN_VAULT_PATH
    is set, we also write a copy there for your main Obsidian app.
    """
    logger = setup_logger()
    data_dir = data_dir or _DEFAULT_DATA_DIR
    manifest_path = data_dir / "manifest.json"
    enriched_dir = data_dir / "enriched"
    notebooklm_outputs = data_dir / "notebooklm_outputs"

    # Primary output: always under the experiment data folder (transparent, one place for the run)
    out_dir = data_dir / "vault"
    out_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Writing notes to %s", out_dir.resolve())

    # Optional: also write to user's Obsidian vault if configured (so it appears in their app)
    vault_path = os.environ.get("OBSIDIAN_VAULT_PATH", "").strip()
    subfolder = os.environ.get("OBSIDIAN_SUBFOLDER", "YouTube Playlists").strip()
    if data_dir != _DEFAULT_DATA_DIR and data_dir.name:
        subfolder = f"{subfolder}/{data_dir.name}"
    mirror_dir = Path(vault_path) / subfolder if _is_vault_configured(vault_path) else None
    if mirror_dir:
        logger.info("Mirroring notes to Obsidian vault: %s", mirror_dir)

    if manifest is None:
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}. Run transcript agent first.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    playlist_title = manifest.get("playlist_title", "YouTube Playlist")
    notebook_id = manifest.get("notebooklm_notebook_id", "")
    playlist_slug = _playlist_slug(playlist_title)
    output_lang = (os.environ.get("OUTPUT_LANGUAGE") or "english").strip().lower()
    if output_lang not in ("english", "greek"):
        output_lang = "english"

    out_dir.mkdir(parents=True, exist_ok=True)
    notebooklm_subdir = out_dir / "notebooklm"
    notebooklm_subdir.mkdir(parents=True, exist_ok=True)

    # Copy NotebookLM artifacts into vault subfolder if they exist
    for name in ["podcast.mp3", "mindmap.json", "quiz.json", "flashcards.json"]:
        src = notebooklm_outputs / name
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
        mindmap_src = notebooklm_outputs / "mindmap.json"
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

    enriched_files = list(enriched_dir.glob("*.json"))
    from rich.console import Console
    from utils.progress_helpers import make_cli_progress

    console = Console()

    with make_cli_progress(console) as progress:
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
                output_language=output_lang,
                source_language=data.get("source_language", ""),
                source_language_name=data.get("source_language_name", ""),
                subtitle_lang=data.get("subtitle_lang", ""),
                transcript=data.get("transcript", ""),
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

    # --- Topic notes & master category index (knowledge base) ---
    sorted_enriched = sorted(enriched_files)
    concept_to_videos, concept_to_related = build_concept_to_videos(sorted_enriched, safe_filename)
    if concept_to_videos:
        topics_dir = out_dir / "Topics"
        topics_dir.mkdir(parents=True, exist_ok=True)
        concept_to_category = _assign_concept_categories(list(concept_to_videos.keys()), logger)
        def _topic_link(concept: str) -> str:
            return safe_concept_filename(concept).replace(".md", "")

        concepts = list(concept_to_videos.items())
        from rich.console import Console
        from utils.progress_helpers import make_cli_progress

        topic_console = Console()
        with make_cli_progress(topic_console) as topic_progress:
            topic_task = topic_progress.add_task("Writing topic notes...", total=len(concepts))
            for concept, mentions in concepts:
                fname = safe_concept_filename(concept)
                note_name = _topic_link(concept)
                summary = _generate_topic_summary(concept, mentions, output_lang, logger)
                _topic_summary_delay()
                lines = [
                    "---",
                    f'title: "{concept.replace(chr(34), chr(92) + chr(34))}"',
                    "tags:",
                    "  - topic",
                    "  - concept",
                    f"  - {playlist_slug}",
                    "---",
                    "",
                    f"# {concept}",
                    "",
                ]
                if summary:
                    lines.extend([
                        "## About this topic",
                        "",
                        summary,
                        "",
                    ])
                lines.extend([
                    "## Mentioned in",
                    "",
                ])
                for note_link, title, one_liner in mentions:
                    if one_liner:
                        lines.append(f"- [[{note_link}|{title}]] — {one_liner}")
                    else:
                        lines.append(f"- [[{note_link}|{title}]]")
                related = concept_to_related.get(concept)
                if related:
                    sorted_related = sorted(related)
                    lines.extend([
                        "",
                        "## Related topics",
                        "",
                        "Concepts that often appear in the same episodes:",
                        "",
                    ] + [f"- [[Topics/{_topic_link(r)}|{r}]]" for r in sorted_related[:15]])
                lines.extend([
                    "",
                    "---",
                    "*Topic note built from playlist concepts. Use the graph view to explore connections.*",
                ])
                (topics_dir / fname).write_text("\n".join(lines), encoding="utf-8")
                topic_progress.advance(topic_task)

        # Master document: hierarchy by category (categories → topics)
        category_to_concepts: dict[str, list[str]] = {cat: [] for cat in TOPIC_CATEGORIES}
        for concept, cat in concept_to_category.items():
            if cat in category_to_concepts:
                category_to_concepts[cat].append(concept)
        topic_index_lines = [
            "# Topics by Category",
            "",
            "> Master index: **categories → topics → episodes**. Open a topic to read **About this topic** and which videos mention it.",
            "",
            "## How to use",
            "",
            "- Browse categories below, or use the **graph** to explore topic ↔ episode links.",
            "- Each topic note has an **About this topic** summary, **episodes** that mention it, and **related topics**.",
            "",
            "---",
            "",
        ]
        for cat in TOPIC_CATEGORIES:
            concepts_in_cat = category_to_concepts.get(cat, [])
            if not concepts_in_cat:
                continue
            topic_index_lines.append(f"## {cat}")
            topic_index_lines.append("")
            for c in sorted(concepts_in_cat):
                topic_index_lines.append(f"- [[Topics/{_topic_link(c)}|{c}]]")
            topic_index_lines.append("")
        topic_index_lines.append("---")
        topic_index_lines.append("*Auto-generated from playlist concepts. Categories assigned from content analysis.*")
        (out_dir / "00 - Topic Index.md").write_text("\n".join(topic_index_lines), encoding="utf-8")

        # Link from playlist index to topic index
        existing_index = index_path.read_text(encoding="utf-8")
        if "## Topic Index" not in existing_index:
            insert = [
                "",
                "## Topic Index",
                "",
                "- 📂 [[00 - Topic Index|Topics by Category]] — master hierarchy of all concepts",
                "- 📖 [[00 - How to use this vault]] — structure and how to navigate",
                "",
            ]
            idx = existing_index.find("## NotebookLM Artifacts")
            if idx != -1:
                existing_index = existing_index[:idx] + "\n".join(insert) + "\n" + existing_index[idx:]
            else:
                existing_index = existing_index.rstrip() + "\n" + "\n".join(insert) + "\n"
            index_path.write_text(existing_index, encoding="utf-8")

        # Short "How to use this vault" note
        howto_path = out_dir / "00 - How to use this vault.md"
        howto_content = """---
title: "How to use this vault"
tags:
  - meta
  - help
---

# How to use this vault

This folder is a **knowledge base** generated from a YouTube playlist: one note per video plus **topic notes** and a **master topic index**.

## Structure

| Note | Purpose |
|------|--------|
| **00 - Index** | Playlist index: all videos + links to NotebookLM artifacts |
| **00 - Topic Index** | **Categories → Topics**: high-level hierarchy of all concepts |
| **01 - … , 02 - …** | One note per video (summary, key ideas, quotes, [[wikilinks]]) |
| **Topics/…** | One note per concept: which episodes mention it + related topics |

## Navigating

- **Graph view**: See how topics and episodes connect (backlinks and [[wikilinks]]).
- **Topic Index**: Start from a category (e.g. "Marketing & Sales") and open topic notes to find episodes.
- **Topic notes**: Each has an **About this topic** section (short explanation) plus **Mentioned in** (which episodes) and **Related topics**.
- **Video notes**: Open any video note and follow its [[Related Concepts]] to explore the topic graph.

## NotebookLM

Audio overview, mind map, quiz, and flashcards are in the `notebooklm/` subfolder and linked from the main Index.
"""
        howto_path.write_text(howto_content.strip(), encoding="utf-8")

    # Optional: mirror to user's Obsidian vault so it appears in their app
    if mirror_dir:
        mirror_dir.mkdir(parents=True, exist_ok=True)
        for item in out_dir.rglob("*"):
            if item.is_file():
                rel = item.relative_to(out_dir)
                dest = mirror_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)
        logger.info("Mirrored to vault: %s", mirror_dir)

    logger.info("Obsidian agent finished. Notes in %s", out_dir)
    return manifest
