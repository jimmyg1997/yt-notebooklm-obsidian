"""NotebookLM: create notebook, add YouTube sources (with delay), generate audio/mindmap/quiz/flashcards."""
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from utils.logger import setup_logger, log_failure

load_dotenv()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MANIFEST_PATH = DATA_DIR / "manifest.json"
NOTEBOOKLM_OUTPUTS = DATA_DIR / "notebooklm_outputs"

NOTEBOOKLM_SOURCE_DELAY = 3  # seconds between source additions


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


def run_notebooklm_agent(manifest: dict | None = None) -> dict:
    """
    Create NotebookLM notebook, add all video URLs, generate artifacts, download to data/notebooklm_outputs/.
    Uses asyncio for notebooklm-py. Returns manifest (unchanged) and saves notebook id to env hint.
    """
    logger = setup_logger()
    notebook_name = os.environ.get("NOTEBOOKLM_NOTEBOOK_NAME", "Greek Playlist Research").strip()
    source_delay = int(os.environ.get("NOTEBOOKLM_SOURCE_DELAY", str(NOTEBOOKLM_SOURCE_DELAY)))

    if manifest is None:
        if not MANIFEST_PATH.exists():
            raise FileNotFoundError(f"Manifest not found: {MANIFEST_PATH}. Run transcript agent first.")
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

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
            else:
                nb = await client.notebooks.create(notebook_name)
                notebook_id = nb.id
                logger.info("Created notebook: %s (id=%s)", notebook_name, notebook_id)

                # Add sources with delay (only when we just created the notebook)
                if video_urls:
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
                        task = progress.add_task("Adding sources to NotebookLM...", total=len(video_urls))
                        for url in video_urls:
                            try:
                                await client.sources.add_url(notebook_id, url, wait=True)
                            except Exception as e:
                                logger.warning("Failed to add %s: %s", url, e)
                            progress.advance(task)
                            await asyncio.sleep(source_delay)

            NOTEBOOKLM_OUTPUTS.mkdir(parents=True, exist_ok=True)

            # 1. Audio Overview (50 sources often take 15–20+ min on NotebookLM's side)
            audio_timeout = float(os.environ.get("NOTEBOOKLM_AUDIO_TIMEOUT", "1200"))
            logger.info("Generating Audio Overview... (timeout=%ss)", audio_timeout)
            try:
                status = await client.artifacts.generate_audio(
                    notebook_id,
                    instructions="Create an engaging overview in English",
                )
                await client.artifacts.wait_for_completion(
                    notebook_id, status.task_id, timeout=audio_timeout
                )
                out_audio = NOTEBOOKLM_OUTPUTS / "podcast.mp3"
                await client.artifacts.download_audio(notebook_id, str(out_audio))
            except Exception as e:
                logger.warning("Audio overview failed: %s", e)

            # 2. Mind Map
            logger.info("Generating Mind Map...")
            try:
                await client.artifacts.generate_mind_map(notebook_id)
                # Wait and download if API supports it
                out_mindmap = NOTEBOOKLM_OUTPUTS / "mindmap.json"
                if hasattr(client.artifacts, "download_mind_map"):
                    await client.artifacts.download_mind_map(notebook_id, str(out_mindmap))
            except Exception as e:
                logger.warning("Mind map failed: %s", e)

            # 3. Quiz (use library enums: QuizDifficulty.HARD, not string "hard")
            logger.info("Generating Quiz...")
            try:
                status = await client.artifacts.generate_quiz(
                    notebook_id, difficulty=QuizDifficulty.HARD
                )
                await client.artifacts.wait_for_completion(notebook_id, status.task_id)
                out_quiz = NOTEBOOKLM_OUTPUTS / "quiz.json"
                await client.artifacts.download_quiz(notebook_id, str(out_quiz), output_format="json")
            except Exception as e:
                logger.warning("Quiz failed: %s", e)

            # 4. Flashcards (use QuizQuantity.MORE enum)
            logger.info("Generating Flashcards...")
            try:
                status = await client.artifacts.generate_flashcards(
                    notebook_id, quantity=QuizQuantity.MORE
                )
                await client.artifacts.wait_for_completion(notebook_id, status.task_id)
                out_cards = NOTEBOOKLM_OUTPUTS / "flashcards.json"
                await client.artifacts.download_flashcards(notebook_id, str(out_cards), output_format="json")
            except Exception as e:
                logger.warning("Flashcards failed: %s", e)

            return notebook_id

    try:
        notebook_id = asyncio.run(_run())
    except Exception as e:
        logger.exception("NotebookLM agent failed: %s", e)
        raise

    if notebook_id:
        manifest["notebooklm_notebook_id"] = notebook_id
        MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("NotebookLM notebook id saved to manifest: %s", notebook_id)

    return manifest
