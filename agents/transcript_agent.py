"""YouTube playlist or channel transcript extraction using yt-dlp. Auto-detect subtitle language."""
import json
import os
import re
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from dotenv import load_dotenv
import yt_dlp

load_dotenv()

from utils.language_utils import (
    build_subtitle_lang_order,
    lang_display_name,
    normalize_lang_code,
    resolve_source_language,
)
from utils.vtt_cleaner import clean_vtt
from utils.logger import setup_logger, log_failure

_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

TranscriptProgressCallback = Callable[[str], None]


class SubtitleResult(NamedTuple):
    text: str
    lang: str
    cues: list[dict]


def _read_downloaded_vtt(out_tmpl: str, lang: str, out_dir: Path) -> tuple[str, list[dict]] | None:
    """Read cleaned text + timed cues from the VTT file yt-dlp wrote."""
    from utils.vtt_cleaner import clean_vtt, parse_vtt_cues

    candidates = [
        Path(out_tmpl + f".{lang}.vtt"),
        Path(out_tmpl + ".vtt"),
    ]
    base = lang.split("-")[0]
    if base != lang:
        candidates.insert(1, Path(out_tmpl + f".{base}.vtt"))

    for path in candidates:
        if path.exists():
            raw = path.read_text(encoding="utf-8", errors="replace")
            return clean_vtt(raw), parse_vtt_cues(raw)

    stem = Path(out_tmpl).name
    for path in sorted(out_dir.glob(f"{stem}*.vtt")):
        raw = path.read_text(encoding="utf-8", errors="replace")
        return clean_vtt(raw), parse_vtt_cues(raw)
    return None


def _is_channel_url(url: str) -> bool:
    """True if URL looks like a YouTube channel (no playlist list=)."""
    url = (url or "").strip().lower()
    if not url or "youtube.com" not in url and "youtu.be" not in url:
        return False
    if "list=" in url:
        return False
    return bool(re.search(r"youtube\.com/(@[\w.-]+|channel/[\w-]+|c/[\w-]+)", url))


def _channel_url_to_uploads_playlist_url(channel_url: str) -> str:
    """Resolve channel URL to the channel's uploads playlist URL (UU + channel_id).
    Uses extract_flat so we only fetch channel metadata, not every video (fast).
    """
    channel_url = channel_url.strip()
    ydl_opts = {"quiet": True, "extract_flat": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
    # Channel ID is typically UCxxxxxxxxxx; uploads playlist is UUxxxxxxxxxx
    channel_id = (info.get("channel_id") or info.get("id") or "").strip()
    if not channel_id:
        raise ValueError("Could not get channel ID from URL: " + channel_url)
    if channel_id.startswith("UC") and len(channel_id) >= 24:
        playlist_id = "UU" + channel_id[2:]
    else:
        playlist_id = channel_id
    return f"https://www.youtube.com/playlist?list={playlist_id}"


def _resolve_to_playlist_url(url: str, source_hint: str = "auto") -> tuple[str, str]:
    """
    Resolve to (playlist_url, source_type).
    source_hint: 'auto' (detect), 'channel' (treat url as channel), 'playlist' (treat as playlist).
    """
    url = url.strip()
    if source_hint == "channel":
        playlist_url = _channel_url_to_uploads_playlist_url(url)
        return playlist_url, "channel"
    if source_hint == "playlist":
        return url, "playlist"
    # auto
    if _is_channel_url(url):
        playlist_url = _channel_url_to_uploads_playlist_url(url)
        return playlist_url, "channel"
    return url, "playlist"


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


def _subtitle_lang_order(title: str = "", prefer: list[str] | None = None, info: dict | None = None) -> list[str]:
    """Pick subtitle languages — delegates to language_utils when no explicit prefer list."""
    if prefer:
        return [normalize_lang_code(x) or x for x in prefer if x]
    return build_subtitle_lang_order(title, info)


def _find_cached_transcript(video_id: str, dest: Path) -> Path | None:
    """Reuse transcript JSON from a prior pipeline run (any experiment under data/)."""
    data_root = _DEFAULT_DATA_DIR
    if not data_root.is_dir():
        return None
    dest_resolved = dest.resolve()
    for candidate in data_root.rglob(f"transcripts/{video_id}.json"):
        try:
            if candidate.resolve() == dest_resolved:
                continue
            if candidate.stat().st_size < 50:
                continue
            return candidate
        except OSError:
            continue
    return None


def _download_subs_for_video(
    video_id: str,
    video_url: str,
    out_dir: Path,
    logger=None,
    *,
    langs: list[str] | None = None,
    on_progress: TranscriptProgressCallback | None = None,
) -> SubtitleResult | None:
    """Try one language at a time to reduce 429. Returns text + language code used."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_tmpl = str(out_dir / video_id)
    lang_order = langs or build_subtitle_lang_order()

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
        return _read_downloaded_vtt(out_tmpl, lang, out_dir) is not None

    got_lang: str | None = None
    got_text: str | None = None
    got_cues: list[dict] = []
    for lang_idx, lang in enumerate(lang_order):
        is_last_lang = lang_idx == len(lang_order) - 1
        for attempt in range(2):
            try:
                if on_progress:
                    on_progress(f"Fetching {lang} subtitles…")
                if try_one_lang(lang):
                    parsed = _read_downloaded_vtt(out_tmpl, lang, out_dir)
                    if parsed and parsed[0].strip():
                        got_lang = normalize_lang_code(lang) or lang
                        got_text = parsed[0]
                        got_cues = parsed[1]
                        break
                break  # no subs for this lang, try next
            except Exception as e:
                err_msg = str(e).lower()
                if "429" in err_msg or "too many requests" in err_msg:
                    if not is_last_lang:
                        if logger:
                            logger.warning(
                                "Rate limited (429) for %s lang=%s — trying next language",
                                video_id,
                                lang,
                            )
                        if on_progress:
                            on_progress(f"YouTube rate-limited ({lang}) — trying next language…")
                        break
                    if attempt == 0:
                        wait_s = 45
                        if logger:
                            logger.warning(
                                "Rate limited (429), waiting %ss then retrying %s for %s",
                                wait_s,
                                lang,
                                video_id,
                            )
                        if on_progress:
                            on_progress(f"YouTube rate-limited — waiting {wait_s}s, then retry…")
                        time.sleep(wait_s)
                        continue
                    break
                if logger:
                    logger.warning("Subtitle fetch failed for %s lang=%s: %s", video_id, lang, e)
                break
        if got_text:
            break
    if not got_text or not got_lang:
        return None
    return SubtitleResult(text=got_text, lang=got_lang, cues=got_cues)


def _normalize_single_video_url(url: str) -> str:
    url = (url or "").strip()
    if "youtu.be/" in url:
        vid = url.split("youtu.be/")[-1].split("?")[0].split("&")[0]
        return f"https://www.youtube.com/watch?v={vid}"
    return url


def _is_single_video_url(url: str) -> bool:
    url = _normalize_single_video_url(url)
    if "list=" in url and "watch?v=" in url:
        return False
    return bool(re.search(r"(?:youtube\.com/watch\?v=|youtu\.be/)[\w-]+", url))


def _video_id_from_url(video_url: str) -> str | None:
    url = _normalize_single_video_url(video_url)
    m = re.search(r"(?:youtube\.com/watch\?v=|youtu\.be/)([\w-]+)", url)
    return m.group(1) if m else None


def run_single_video_transcript(
    video_url: str,
    data_dir: Path | None = None,
    resume: bool = False,
    on_progress: TranscriptProgressCallback | None = None,
) -> dict:
    """Extract transcript for one YouTube video. Updates or creates manifest.json."""
    logger = setup_logger()
    data_dir = data_dir or _DEFAULT_DATA_DIR
    transcripts_dir = data_dir / "transcripts"
    manifest_path = data_dir / "manifest.json"
    video_url = _normalize_single_video_url(video_url)

    if not _is_single_video_url(video_url):
        raise ValueError("Not a single-video YouTube URL")

    transcripts_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    video_id_guess = _video_id_from_url(video_url)
    transcript_path_guess = transcripts_dir / f"{video_id_guess}.json" if video_id_guess else None
    cached_early = (
        _find_cached_transcript(video_id_guess, transcript_path_guess)
        if video_id_guess and transcript_path_guess
        else None
    )
    if cached_early and not (resume and transcript_path_guess.exists()):
        if on_progress:
            on_progress(f"Reusing cached transcript from {cached_early.parent.parent.name}")
        shutil.copy2(cached_early, transcript_path_guess)
        payload = json.loads(transcript_path_guess.read_text(encoding="utf-8"))
        title = payload.get("title") or "Unknown"
        video_id = video_id_guess
        transcript_path = transcript_path_guess
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            manifest = {
                "playlist_url": video_url,
                "source_url": video_url,
                "source_type": "single_video",
                "playlist_title": payload.get("playlist_title") or title,
                "videos": [],
            }
        videos = [v for v in manifest.get("videos", []) if v.get("id") != video_id]
        videos.append(
            {
                "id": video_id,
                "title": title,
                "url": video_url,
                "status": "ok",
                "transcript_path": str(transcript_path),
                "transcript_cached": True,
            }
        )
        manifest["videos"] = videos
        manifest["source_type"] = "single_video"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Reused cached transcript for %s from %s (skipped YouTube fetch)", video_id, cached_early)
        return manifest

    ydl_opts = {"quiet": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        full_info = ydl.extract_info(video_url, download=False)

    video_id = full_info.get("id") or video_url.split("v=")[-1].split("&")[0]
    title = full_info.get("title") or "Unknown"
    transcript_path = transcripts_dir / f"{video_id}.json"

    cached = _find_cached_transcript(video_id, transcript_path)
    if cached and not (resume and transcript_path.exists()):
        if on_progress:
            on_progress(f"Reusing cached transcript from {cached.parent.parent.name}")
        shutil.copy2(cached, transcript_path)
        payload = json.loads(transcript_path.read_text(encoding="utf-8"))
        transcript_text = payload.get("transcript") or ""
        if transcript_text.strip():
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            else:
                manifest = {
                    "playlist_url": video_url,
                    "source_url": video_url,
                    "source_type": "single_video",
                    "playlist_title": payload.get("playlist_title") or title,
                    "videos": [],
                }
            videos = [v for v in manifest.get("videos", []) if v.get("id") != video_id]
            videos.append(
                {
                    "id": video_id,
                    "title": title,
                    "url": video_url,
                    "status": "ok",
                    "transcript_path": str(transcript_path),
                    "transcript_cached": True,
                }
            )
            manifest["videos"] = videos
            manifest["source_type"] = "single_video"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("Reused cached transcript for %s from %s", video_id, cached)
            return manifest

    if resume and transcript_path.exists():
        manifest = {}
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            manifest = {
                "playlist_url": video_url,
                "source_url": video_url,
                "source_type": "single_video",
                "playlist_title": "Single video ingest",
                "videos": [],
            }
        entry = next((v for v in manifest.get("videos", []) if v.get("id") == video_id), None)
        if not entry:
            manifest.setdefault("videos", []).append(
                {
                    "id": video_id,
                    "title": title,
                    "url": video_url,
                    "status": "ok",
                    "transcript_path": str(transcript_path),
                }
            )
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest

    tmp_dir = Path(tempfile.mkdtemp())
    lang_order = _subtitle_lang_order(title, info=full_info)
    available = build_subtitle_lang_order(title, full_info)
    if on_progress:
        preview = "/".join(lang_order[:3])
        if len(lang_order) > 3:
            preview += "…"
        on_progress(f"Downloading subtitles ({preview})…")
    sub_result = _download_subs_for_video(
        video_id,
        video_url,
        tmp_dir,
        logger,
        langs=lang_order,
        on_progress=on_progress,
    )
    try:
        for f in tmp_dir.glob("*"):
            f.unlink(missing_ok=True)
        tmp_dir.rmdir()
    except OSError:
        pass

    if not sub_result or not sub_result.text.strip():
        raise ValueError(f"No subtitles available for video {video_id}")

    transcript_text = sub_result.text
    subtitle_lang = sub_result.lang
    video_lang = normalize_lang_code(full_info.get("language") or "")
    source_lang, source_lang_name = resolve_source_language(
        transcript_text,
        subtitle_lang=subtitle_lang,
        video_lang=video_lang,
    )

    playlist_title = full_info.get("playlist_title") or full_info.get("channel") or "Single video ingest"
    payload = {
        "video_id": video_id,
        "title": title,
        "url": video_url,
        "transcript": transcript_text,
        "playlist_title": playlist_title,
        "uploader": full_info.get("uploader") or full_info.get("channel") or "",
        "duration": full_info.get("duration") or 0,
        "upload_date": full_info.get("upload_date") or "",
        "subtitle_lang": subtitle_lang,
        "video_lang": video_lang,
        "source_language": source_lang,
        "source_language_name": source_lang_name,
        "available_subtitle_langs": available[:20],
        "transcript_cues": sub_result.cues,
    }
    transcript_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {
            "playlist_url": video_url,
            "source_url": video_url,
            "source_type": "single_video",
            "playlist_title": playlist_title,
            "videos": [],
        }

    videos = [v for v in manifest.get("videos", []) if v.get("id") != video_id]
    videos.append(
        {
            "id": video_id,
            "title": title,
            "url": video_url,
            "status": "ok",
            "transcript_path": str(transcript_path),
        }
    )
    manifest["videos"] = videos
    manifest["source_type"] = "single_video"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Single-video transcript saved: %s", transcript_path)
    return manifest


def run_transcript_agent(
    resume: bool = False,
    source_url: str | None = None,
    source_type: str = "auto",
    max_videos: int | None = None,
    data_dir: Path | None = None,
) -> dict:
    """
    Extract transcripts for playlist/channel videos. Save JSON per video and manifest.
    Args:
        resume: Skip videos that already have a transcript JSON.
        source_url: Playlist or channel URL (overrides PLAYLIST_URL from env if set).
        source_type: 'auto' (detect), 'channel', or 'playlist'.
        max_videos: Cap the number of videos to process (None = no limit).
        data_dir: Base dir for this run (transcripts/, manifest.json). If None, uses data/.
    Returns manifest dict (videos, playlist_title, status per video).
    """
    logger = setup_logger()
    data_dir = data_dir or _DEFAULT_DATA_DIR
    transcripts_dir = data_dir / "transcripts"
    manifest_path = data_dir / "manifest.json"

    input_url = (source_url or os.environ.get("PLAYLIST_URL", "")).strip()
    if not input_url:
        raise ValueError(
            "No URL provided. Set PLAYLIST_URL in .env or pass --url (playlist or channel URL)."
        )

    transcripts_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    playlist_url, resolved_source = _resolve_to_playlist_url(input_url, source_hint=source_type)
    if resolved_source == "channel":
        logger.info("Channel URL detected; using channel uploads playlist: %s", playlist_url)

    entries, playlist_title = _get_playlist_info(playlist_url)
    if max_videos is not None and max_videos > 0:
        entries = entries[:max_videos]
        logger.info("Limiting to first %d videos (--limit %d)", len(entries), max_videos)

    manifest = {
        "playlist_url": playlist_url,
        "source_url": input_url,
        "source_type": resolved_source,
        "playlist_title": playlist_title,
        "max_videos_applied": max_videos,
        "videos": [],
    }
    tmp_dir = Path(tempfile.mkdtemp())

    from rich.console import Console
    from utils.progress_helpers import make_cli_progress

    console = Console()

    with make_cli_progress(console) as progress:
        task = progress.add_task("Extracting transcripts...", total=len(entries))
        for i, entry in enumerate(entries):
            video_id = entry.get("id") or entry.get("url", "").split("?v=")[-1].split("&")[0]
            if not video_id:
                manifest["videos"].append({"id": None, "title": "?", "status": "failed", "reason": "no_id"})
                progress.advance(task)
                continue

            title = entry.get("title") or "Unknown"
            video_url = entry.get("url") or f"https://www.youtube.com/watch?v={video_id}"
            transcript_path = transcripts_dir / f"{video_id}.json"

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

            try:
                ydl_opts = {"quiet": True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    full_info = ydl.extract_info(video_url, download=False)
            except Exception:
                full_info = {}

            lang_order = _subtitle_lang_order(title, info=full_info)
            sub_result = _download_subs_for_video(
                video_id, video_url, tmp_dir, logger, langs=lang_order
            )
            if sub_result is None or not sub_result.text.strip():
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

            transcript_text = sub_result.text
            subtitle_lang = sub_result.lang

            # Get full metadata for this video for duration, uploader, etc.
            if not full_info:
                try:
                    ydl_opts = {"quiet": True}
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        full_info = ydl.extract_info(video_url, download=False)
                except Exception:
                    full_info = {}

            video_lang = normalize_lang_code(full_info.get("language") or "")
            source_lang, source_lang_name = resolve_source_language(
                transcript_text,
                subtitle_lang=subtitle_lang,
                video_lang=video_lang,
            )

            payload = {
                "video_id": video_id,
                "title": title,
                "url": video_url,
                "transcript": transcript_text,
                "playlist_title": playlist_title,
                "uploader": full_info.get("uploader") or "",
                "duration": full_info.get("duration") or 0,
                "upload_date": full_info.get("upload_date") or "",
                "subtitle_lang": subtitle_lang,
                "video_lang": video_lang,
                "source_language": source_lang,
                "source_language_name": source_lang_name,
                "transcript_cues": sub_result.cues,
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

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Transcript agent finished. Manifest: %s", manifest_path)
    return manifest
