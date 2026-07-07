"""NotebookLM: create notebook, add only missing YouTube sources, generate artifacts."""
import asyncio
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from utils.logger import setup_logger, log_failure

load_dotenv()

_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

NOTEBOOKLM_SOURCE_DELAY = 3  # seconds between source additions


def _extract_video_id(url: str) -> str | None:
    """Normalize YouTube URL to video id for robust dedupe."""
    if not url:
        return None
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{6,})", url)
    if m:
        return m.group(1)
    return None


def _collect_urls_from_source_obj(source) -> set[str]:
    """Best-effort extraction for different notebooklm-py source shapes."""
    values = set()
    if source is None:
        return values
    if isinstance(source, str):
        values.add(source.strip())
        return values

    for key in ("url", "source_url", "link", "uri"):
        val = getattr(source, key, None)
        if isinstance(val, str) and val.strip():
            values.add(val.strip())

    if isinstance(source, dict):
        for key in ("url", "source_url", "link", "uri"):
            val = source.get(key)
            if isinstance(val, str) and val.strip():
                values.add(val.strip())

    return values


async def _get_existing_notebook_urls(client, notebook_id: str, logger) -> set[str]:
    """
    Fetch existing source URLs from NotebookLM.
    Handles multiple notebooklm-py API shapes defensively.
    """
    existing = set()
    list_methods = [
        ("list", getattr(client.sources, "list", None)),
        ("list_sources", getattr(client.sources, "list_sources", None)),
        ("list_by_notebook", getattr(client.sources, "list_by_notebook", None)),
    ]

    for name, method in list_methods:
        if not callable(method):
            continue
        try:
            sources = await method(notebook_id)
            for src in sources or []:
                existing.update(_collect_urls_from_source_obj(src))
            if existing:
                return existing
        except Exception as e:
            logger.debug("Could not fetch existing sources via sources.%s: %s", name, e)

    # Last fallback: try notebook details that may include sources
    try:
        nb = await client.notebooks.get(notebook_id)
        for key in ("sources", "source_documents", "documents"):
            items = getattr(nb, key, None)
            if items is None and isinstance(nb, dict):
                items = nb.get(key)
            for src in items or []:
                existing.update(_collect_urls_from_source_obj(src))
    except Exception as e:
        logger.debug("Could not fetch existing sources via notebooks.get: %s", e)

    return existing


async def _add_sources_batch(client, notebook_id: str, video_urls: list[str], delay: int) -> list[str]:
    """Add YouTube URLs as sources with retry; return list of failed URLs."""
    failed = []
    for i, url in enumerate(video_urls, 1):
        try:
            await client.sources.add_url(notebook_id, url, wait=True)
        except Exception as e:
            setup_logger().warning("Failed to add source %s: %s", url, e)
            failed.append(url)
        await asyncio.sleep(delay)
    return failed


def run_notebooklm_agent(
    manifest: dict | None = None,
    data_dir: Path | None = None,
    update_mode: bool = False,
) -> dict:
    """
    Create/reuse NotebookLM notebook, add only missing video URLs, generate artifacts, download outputs.
    Uses asyncio for notebooklm-py. Returns manifest (unchanged) and saves notebook id to env hint.
    """
    logger = setup_logger()
    data_dir = data_dir or _DEFAULT_DATA_DIR
    manifest_path = data_dir / "manifest.json"
    notebooklm_outputs = data_dir / "notebooklm_outputs"

    notebook_name = os.environ.get("NOTEBOOKLM_NOTEBOOK_NAME", "Greek Playlist Research").strip()
    source_delay = int(os.environ.get("NOTEBOOKLM_SOURCE_DELAY", "3"))

    if manifest is None:
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}. Run transcript agent first.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    video_urls = [v["url"] for v in manifest.get("videos", []) if v.get("status") == "ok" and v.get("url")]
    # Reuse existing notebook: env override, or last run's id from manifest
    existing_id = (os.environ.get("NOTEBOOKLM_NOTEBOOK_ID") or "").strip() or manifest.get("notebooklm_notebook_id")
    if not video_urls and not existing_id:
        logger.warning("No video URLs to add to NotebookLM and no existing notebook id")
        return manifest

    try:
        from notebooklm import NotebookLMClient, QuizDifficulty, QuizQuantity
    except ImportError:
        raise ImportError("notebooklm-py is required. Install with: pip install 'notebooklm-py[browser]'")

    async def _run() -> str | None:
        async with await NotebookLMClient.from_storage() as client:
            if existing_id:
                notebook_id = existing_id
                logger.info("Using existing notebook: %s", notebook_id)
                existing_urls = await _get_existing_notebook_urls(client, notebook_id, logger)
                existing_video_ids = {_extract_video_id(u) for u in existing_urls if _extract_video_id(u)}
                missing_urls = []
                for u in video_urls:
                    vid = _extract_video_id(u)
                    if vid and vid in existing_video_ids:
                        continue
                    if u in existing_urls:
                        continue
                    missing_urls.append(u)
                logger.info(
                    "NotebookLM source sync: existing=%d, candidate=%d, missing=%d%s",
                    len(existing_urls),
                    len(video_urls),
                    len(missing_urls),
                    " [update mode]" if update_mode else "",
                )
            else:
                nb = await client.notebooks.create(notebook_name)
                notebook_id = nb.id
                logger.info("Created notebook: %s (id=%s)", notebook_name, notebook_id)
                missing_urls = video_urls

            # Always attempt incremental source sync (new notebook -> all, existing notebook -> missing only).
            if missing_urls:
                from rich.console import Console
                from utils.progress_helpers import make_cli_progress

                console = Console()
                with make_cli_progress(console) as progress:
                    task = progress.add_task("Adding missing sources to NotebookLM...", total=len(missing_urls))
                    for url in missing_urls:
                        try:
                            await client.sources.add_url(notebook_id, url, wait=True)
                        except Exception as e:
                            logger.warning("Failed to add %s: %s", url, e)
                        progress.advance(task)
                        await asyncio.sleep(source_delay)
            else:
                logger.info("No new NotebookLM sources to add.")

            notebooklm_outputs.mkdir(parents=True, exist_ok=True)

            from rich.console import Console
            from utils.progress_helpers import make_cli_progress

            artifact_console = Console()
            with make_cli_progress(artifact_console) as artifact_progress:
                art_task = artifact_progress.add_task("NotebookLM artifacts", total=4)

                # 1. Audio Overview
                audio_timeout = float(os.environ.get("NOTEBOOKLM_AUDIO_TIMEOUT", "1200"))
                logger.info("Generating Audio Overview... (timeout=%ss)", audio_timeout)
                artifact_progress.update(art_task, description="Audio overview")
                try:
                    status = await client.artifacts.generate_audio(
                        notebook_id,
                        instructions="Create an engaging overview in English",
                    )
                    await client.artifacts.wait_for_completion(
                        notebook_id, status.task_id, timeout=audio_timeout
                    )
                    out_audio = notebooklm_outputs / "podcast.mp3"
                    await client.artifacts.download_audio(notebook_id, str(out_audio))
                except Exception as e:
                    logger.warning("Audio overview failed: %s", e)
                artifact_progress.advance(art_task)

                # 2. Mind Map
                artifact_progress.update(art_task, description="Mind map")
                logger.info("Generating Mind Map...")
                try:
                    await client.artifacts.generate_mind_map(notebook_id)
                    out_mindmap = notebooklm_outputs / "mindmap.json"
                    if hasattr(client.artifacts, "download_mind_map"):
                        await client.artifacts.download_mind_map(notebook_id, str(out_mindmap))
                except Exception as e:
                    logger.warning("Mind map failed: %s", e)
                artifact_progress.advance(art_task)

                # 3. Quiz
                artifact_progress.update(art_task, description="Quiz")
                logger.info("Generating Quiz...")
                try:
                    status = await client.artifacts.generate_quiz(
                        notebook_id, difficulty=QuizDifficulty.HARD
                    )
                    await client.artifacts.wait_for_completion(notebook_id, status.task_id)
                    out_quiz = notebooklm_outputs / "quiz.json"
                    await client.artifacts.download_quiz(notebook_id, str(out_quiz), output_format="json")
                except Exception as e:
                    logger.warning("Quiz failed: %s", e)
                artifact_progress.advance(art_task)

                # 4. Flashcards
                artifact_progress.update(art_task, description="Flashcards")
                logger.info("Generating Flashcards...")
                try:
                    status = await client.artifacts.generate_flashcards(
                        notebook_id, quantity=QuizQuantity.MORE
                    )
                    await client.artifacts.wait_for_completion(notebook_id, status.task_id)
                    out_cards = notebooklm_outputs / "flashcards.json"
                    await client.artifacts.download_flashcards(notebook_id, str(out_cards), output_format="json")
                except Exception as e:
                    logger.warning("Flashcards failed: %s", e)
                artifact_progress.advance(art_task)

            return notebook_id

    try:
        notebook_id = asyncio.run(_run())
    except Exception as e:
        logger.exception("NotebookLM agent failed: %s", e)
        raise

    if notebook_id:
        manifest["notebooklm_notebook_id"] = notebook_id
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("NotebookLM notebook id saved to manifest: %s", notebook_id)

    return manifest
