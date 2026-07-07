"""Extract meaningful video frames with transcript-matched captions."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from utils.logger import setup_logger
from utils.progress_helpers import ProgressCallback
from utils.vtt_cleaner import cue_text_at_second

_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def compute_frame_budget(duration_sec: int, enriched: dict) -> int:
    """Screenshot count — default at least 20 per video (configurable)."""
    min_count = int(os.environ.get("SCREENSHOT_MIN_COUNT", "20"))
    max_count = int(os.environ.get("SCREENSHOT_MAX_COUNT", "24"))
    duration_sec = max(int(duration_sec or 0), 60)
    # Scale slightly for very long videos but cap cost
    if duration_sec > 3600:
        target = min(max_count, min_count + 4)
    else:
        target = min_count
    return max(min_count, min(target, max_count))


def _format_timestamp(seconds: int) -> str:
    m, s = divmod(max(0, int(seconds)), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _excerpt_at_ratio(transcript: str, ratio: float, words_each_side: int = 30) -> str:
    words = transcript.split()
    if not words:
        return ""
    idx = int(len(words) * max(0.0, min(1.0, ratio)))
    chunk = words[max(0, idx - words_each_side) : idx + words_each_side]
    return " ".join(chunk).strip()


def _call_llm_for_timestamps(
    transcript: str,
    duration_sec: int,
    count: int,
    title: str,
    cues: list[dict],
) -> list[dict]:
    """Return [{seconds, caption, transcript_excerpt}, ...] spread across the video."""
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    excerpt = transcript[:16000]
    prompt = f"""You pick screenshot moments for a YouTube video note.

Video: "{title}"
Duration: {duration_sec} seconds
Pick exactly {count} timestamps spread across the full video (topic changes, products named, demos, data on screen).
Avoid the first/last 8 seconds. Space them evenly enough to cover beginning, middle, and end.

For each moment, the caption must describe what is ON SCREEN or what is being said (specific, not generic).

Reply with JSON only, no markdown:
[{{"seconds": 120, "caption": "short on-screen label"}}, ...]

Transcript:
{excerpt}
"""
    text = ""
    try:
        if openai_key and "your_openai" not in openai_key.lower():
            from openai import OpenAI

            client = OpenAI(api_key=openai_key)
            r = client.chat.completions.create(
                model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role": "user", "content": prompt}],
            )
            text = (r.choices[0].message.content or "").strip()
        elif gemini_key:
            from google import genai

            client = genai.Client(api_key=gemini_key)
            model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
            resp = client.models.generate_content(model=model, contents=prompt)
            text = (getattr(resp, "text", None) or "").strip()
        else:
            raise ValueError("No API key for screenshot timestamps")
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text).rstrip("`").strip()
        picks = json.loads(text)
        out = []
        for item in picks[:count]:
            sec = int(item.get("seconds", 0))
            sec = max(8, min(sec, max(duration_sec - 8, 8)))
            caption = str(item.get("caption", "Frame")).strip()[:160]
            spoken = cue_text_at_second(cues, sec) if cues else ""
            if not spoken:
                spoken = _excerpt_at_ratio(transcript, sec / max(duration_sec, 1))
            out.append(
                {
                    "seconds": sec,
                    "caption": caption,
                    "transcript_excerpt": spoken[:500],
                }
            )
        return out
    except Exception:
        step = max(duration_sec // (count + 1), 20)
        return [
            {
                "seconds": step * (i + 1),
                "caption": f"Moment {i + 1}",
                "transcript_excerpt": (
                    cue_text_at_second(cues, step * (i + 1))
                    if cues
                    else _excerpt_at_ratio(transcript, (i + 1) / (count + 1))
                )[:500],
            }
            for i in range(count)
        ]


def _get_direct_stream_url(video_url: str) -> str:
    import yt_dlp

    opts = {"quiet": True, "format": "best[height<=720]/best"}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
        url = info.get("url")
        if not url:
            raise RuntimeError("Could not resolve video stream URL")
        return url


def _extract_frame_ffmpeg(stream_url: str, seconds: int, out_path: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH. Install ffmpeg to capture screenshots.")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        str(seconds),
        "-i",
        stream_url,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return proc.returncode == 0 and out_path.is_file() and out_path.stat().st_size > 0


def run_screenshot_agent(
    enriched: dict,
    vault_dir: Path,
    data_dir: Path | None = None,
    on_progress: ProgressCallback | None = None,
) -> list[dict]:
    """
    Extract screenshots into vault_dir/assets/{video_id}/.
    Returns list with caption + transcript_excerpt matched to each frame.
    """
    logger = setup_logger()
    data_dir = data_dir or _DEFAULT_DATA_DIR
    video_id = enriched.get("video_id") or "unknown"
    video_url = enriched.get("url") or f"https://www.youtube.com/watch?v={video_id}"
    title = enriched.get("title") or "Video"
    duration_raw = enriched.get("duration") or 0
    duration_sec = int(duration_raw) if duration_raw else 600
    transcript = enriched.get("transcript") or ""
    cues = enriched.get("transcript_cues") or []

    count = compute_frame_budget(duration_sec, enriched)
    logger.info("Screenshot budget for %s: %d frames (duration %ds)", video_id, count, duration_sec)

    timestamps = _call_llm_for_timestamps(transcript, duration_sec, count, title, cues)
    assets_dir = vault_dir / "assets" / video_id
    assets_dir.mkdir(parents=True, exist_ok=True)

    try:
        stream_url = _get_direct_stream_url(video_url)
    except Exception as e:
        logger.warning("Stream URL failed (%s); skipping screenshots", e)
        return []

    frames: list[dict] = []
    total = len(timestamps)
    for i, pick in enumerate(timestamps, 1):
        sec = pick["seconds"]
        filename = f"frame_{i:02d}.jpg"
        out_path = assets_dir / filename
        if on_progress:
            on_progress(i - 1, total, pick.get("caption", ""))
        try:
            ok = _extract_frame_ffmpeg(stream_url, sec, out_path)
        except Exception as e:
            logger.warning("Frame extract failed at %ss: %s", sec, e)
            ok = False
        if not ok:
            continue
        excerpt = (pick.get("transcript_excerpt") or "").strip()
        if not excerpt and cues:
            excerpt = cue_text_at_second(cues, sec)
        if not excerpt:
            excerpt = _excerpt_at_ratio(transcript, sec / max(duration_sec, 1))
        rel = f"assets/{video_id}/{filename}"
        frames.append(
            {
                "filename": filename,
                "caption": pick["caption"],
                "transcript_excerpt": excerpt[:500],
                "seconds": sec,
                "timestamp_label": _format_timestamp(sec),
                "rel_path": rel,
            }
        )
    if on_progress:
        on_progress(total, total, "Done")
    logger.info("Captured %d/%d screenshots for %s", len(frames), count, video_id)
    return frames
