"""YouTube playlist transcript extraction using yt-dlp. Greek (el) first, then en fallback."""
import json
import os
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv
import yt_dlp

load_dotenv()

from utils.vtt_cleaner import clean_vtt
from utils.logger import setup_logger, log_failure

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
MANIFEST_PATH = DATA_DIR / "manifest.json"

# One language per request to avoid 429 (YouTube rate-limits multi-lang subtitle fetches)
SUBTITLE_LANGS_ORDER = ["el", "en", "en-US"]


def _get_playlist_info(playlist_url: str) -> tuple[list[dict], str]:
    """Fetch playlist metadata and video list (no download). Use in_playlist so entries is a list."""
    ydl_opts = {"quiet": True, "extract_flat": "in_playlist"}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(playlist_url, download=False)
    entries = info.get("entries")
    if entries is None:
        entries = []
    else:
        entries = list(entries)
    entries = [e for e in entries if e and isinstance(e, dict)]
    playlist_title = info.get("title") or "YouTube Playlist"
    return entries, playlist_title


def _download_subs_for_video(video_id: str, video_url: str, out_dir: Path, logger=None) -> str | None:
    """Try one language at a time (el then en) to reduce 429. Retries once on 429."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_tmpl = str(out_dir / video_id)

    def try_one_lang(lang: str) -> bool:
        opts = {
            "quiet": True,
            "skip_download": True,
            "writeautomaticsub": True,
            "writesubtitles": True,
            "subtitleslangs": [lang],
            "subtitlesformat": "vtt",
            "outtmpl": out_tmpl,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([video_url])
        return Path(out_tmpl + f".{lang}.vtt").exists() or Path(out_tmpl + ".vtt").exists()

    got_subs = False
    for lang in SUBTITLE_LANGS_ORDER:
        for attempt in range(2):
            try:
                if try_one_lang(lang):
                    got_subs = True
                    break
                break  # no subs for this lang, try next
            except Exception as e:
                err_msg = str(e).lower()
                if "429" in err_msg or "too many requests" in err_msg:
                    if attempt == 0 and logger:
                        logger.warning("Rate limited (429), waiting 90s then retrying for %s", video_id)
                    time.sleep(90)
                    continue
                break
        else:
            continue
        if got_subs:
            break
    if not got_subs:
        return None

    for ext in [".el.vtt", ".en.vtt", ".en-US.vtt", ".vtt"]:
        vtt_path = Path(out_tmpl + ext)
        if vtt_path.exists():
            return clean_vtt(vtt_path.read_text(encoding="utf-8", errors="replace"))
    return None


def run_transcript_agent(resume: bool = False) -> dict:
    """
    Extract transcripts for all playlist videos. Save JSON per video and manifest.
    If resume=True, skip videos that already have a transcript JSON.
    Returns manifest dict (videos, playlist_title, status per video).
    """
    logger = setup_logger()
    playlist_url = os.environ.get("PLAYLIST_URL", "").strip()
    if not playlist_url:
        raise ValueError("PLAYLIST_URL is not set in environment")

    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    entries, playlist_title = _get_playlist_info(playlist_url)
    manifest = {
        "playlist_url": playlist_url,
        "playlist_title": playlist_title,
        "videos": [],
    }
    tmp_dir = Path(tempfile.mkdtemp())

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
        task = progress.add_task("Extracting transcripts...", total=len(entries))
        for i, entry in enumerate(entries):
            video_id = entry.get("id") or entry.get("url", "").split("?v=")[-1].split("&")[0]
            if not video_id:
                manifest["videos"].append({"id": None, "title": "?", "status": "failed", "reason": "no_id"})
                progress.advance(task)
                continue

            title = entry.get("title") or "Unknown"
            video_url = entry.get("url") or f"https://www.youtube.com/watch?v={video_id}"
            transcript_path = TRANSCRIPTS_DIR / f"{video_id}.json"

            if resume and transcript_path.exists():
                try:
                    data = json.loads(transcript_path.read_text(encoding="utf-8"))
                    manifest["videos"].append({
                        "id": video_id,
                        "title": title,
                        "url": video_url,
                        "status": "ok",
                        "transcript_path": str(transcript_path),
                    })
                except Exception:
                    manifest["videos"].append({
                        "id": video_id,
                        "title": title,
                        "url": video_url,
                        "status": "failed",
                        "reason": "resume_read_error",
                    })
                progress.advance(task)
                continue

            transcript_text = _download_subs_for_video(video_id, video_url, tmp_dir, logger)
            if transcript_text is None or not transcript_text.strip():
                log_failure(logger, video_id, "no subtitles available")
                manifest["videos"].append({
                    "id": video_id,
                    "title": title,
                    "url": video_url,
                    "status": "failed",
                    "reason": "no_subtitles",
                })
                progress.advance(task)
                delay = float(os.environ.get("TRANSCRIPT_DELAY_SECONDS", "3"))
                if delay > 0:
                    time.sleep(delay)
                continue

            # Get full metadata for this video for duration, uploader, etc.
            try:
                ydl_opts = {"quiet": True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    full_info = ydl.extract_info(video_url, download=False)
            except Exception:
                full_info = {}

            payload = {
                "video_id": video_id,
                "title": title,
                "url": video_url,
                "transcript": transcript_text,
                "playlist_title": playlist_title,
                "uploader": full_info.get("uploader") or "",
                "duration": full_info.get("duration") or 0,
                "upload_date": full_info.get("upload_date") or "",
            }
            try:
                transcript_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                manifest["videos"].append({
                    "id": video_id,
                    "title": title,
                    "url": video_url,
                    "status": "ok",
                    "transcript_path": str(transcript_path),
                })
            except Exception as e:
                log_failure(logger, video_id, str(e))
                manifest["videos"].append({
                    "id": video_id,
                    "title": title,
                    "url": video_url,
                    "status": "failed",
                    "reason": str(e),
                })
            progress.advance(task)
            # Delay between videos to avoid YouTube 429 rate limit
            delay = float(os.environ.get("TRANSCRIPT_DELAY_SECONDS", "3"))
            if delay > 0:
                time.sleep(delay)

    # Cleanup temp dir
    try:
        for f in tmp_dir.glob("*"):
            f.unlink(missing_ok=True)
        tmp_dir.rmdir()
    except Exception:
        pass

    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Transcript agent finished. Manifest: %s", MANIFEST_PATH)
    return manifest
