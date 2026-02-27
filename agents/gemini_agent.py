"""LLM enrichment: summary, key ideas, takeaways, quotes, wikilinks. Greek → English. Supports OpenAI or Gemini."""
import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from utils.logger import setup_logger, log_failure

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
ENRICHED_DIR = DATA_DIR / "enriched"
MANIFEST_PATH = DATA_DIR / "manifest.json"

PROMPT_TEMPLATE = '''The following is a transcript from a Greek YouTube video titled: "{title}"
The transcript is in Greek. Please respond entirely in English.

## Summary
Write 3-5 sentences capturing the core message.

## Key Ideas
List the 5-8 most important concepts or arguments. Each item 1-2 sentences.

## Takeaways & Action Items
List 3-5 practical things to remember or do.

## Notable Quotes
Extract 2-4 important moments from the transcript (translate to English).

## Related Concepts
List 8-12 concepts as [[wikilinks]] that could connect to other Obsidian notes.

TRANSCRIPT:
{transcript}
'''

# Max chars per transcript (only used for small-context models like gpt-3.5-turbo; gpt-4o-mini 128k can take full)
MAX_TRANSCRIPT_CHARS = 50_000


def parse_llm_response(text: str) -> dict:
    """Parse Gemini markdown response into sections."""
    sections = {}
    current = None
    for line in text.split("\n"):
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None and line.strip():
            sections[current].append(line.strip())
    return {k: "\n".join(v) for k, v in sections.items()}


def _call_openai(prompt: str, model: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    r = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return (r.choices[0].message.content or "").strip()


def _call_gemini(prompt: str, client, model_name: str) -> str:
    response = client.models.generate_content(model=model_name, contents=prompt)
    text = getattr(response, "text", None) or ""
    if not text and getattr(response, "candidates", None):
        c = response.candidates[0]
        if getattr(c, "content", None) and c.content.parts:
            text = getattr(c.content.parts[0], "text", None) or ""
    return text.strip()


def run_gemini_agent(manifest: dict | None = None, resume: bool = False) -> dict:
    """
    Enrich each transcript with an LLM (OpenAI or Gemini). Save to data/enriched/{video_id}.json.
    If OPENAI_API_KEY is set, uses OpenAI; else uses GEMINI_API_KEY. If resume=True, skips already-enriched videos.
    """
    logger = setup_logger()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    # Prefer OpenAI (default); fall back to Gemini if no OpenAI key.
    if openai_key:
        try:
            import openai  # noqa: F401
        except ImportError:
            raise ImportError("OpenAI is set but the 'openai' package is missing. Run: pip install openai")
        provider = "openai"
        model_name = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
        llm_client = None
    elif gemini_key:
        provider = "gemini"
        from google import genai
        llm_client = genai.Client(api_key=gemini_key)
        model_name = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash").strip()
    else:
        raise ValueError("Set OPENAI_API_KEY (recommended) or GEMINI_API_KEY in .env")

    # OpenAI paid tier can go faster; Gemini free needs throttle.
    delay_seconds = float(os.environ.get("API_DELAY_SECONDS", "2" if provider == "openai" else "6"))

    if manifest is None:
        if not MANIFEST_PATH.exists():
            raise FileNotFoundError(f"Manifest not found: {MANIFEST_PATH}. Run transcript agent first.")
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    ENRICHED_DIR.mkdir(parents=True, exist_ok=True)

    # Include any video that has a transcript; skip only if resume and already enriched.
    # (Don't filter by manifest "status" — it gets set to "failed" by Gemini, so we'd process 0 on retry.)
    videos = []
    for v in manifest.get("videos", []):
        vid = v.get("id")
        if not vid:
            continue
        tp = v.get("transcript_path") or TRANSCRIPTS_DIR / f"{vid}.json"
        if not Path(tp).exists():
            continue
        if resume and (ENRICHED_DIR / f"{vid}.json").exists():
            continue
        videos.append(v)
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
        task = progress.add_task(f"Enriching with {provider}...", total=len(videos))
        for v in videos:
            video_id = v.get("id")
            transcript_path = v.get("transcript_path") or str(TRANSCRIPTS_DIR / f"{video_id}.json")
            enriched_path = ENRICHED_DIR / f"{video_id}.json"

            if resume and enriched_path.exists():
                progress.advance(task)
                continue

            try:
                data = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
            except Exception as e:
                log_failure(logger, video_id, f"read transcript: {e}")
                v["status"] = "failed"
                v["reason"] = str(e)
                progress.advance(task)
                continue

            title = data.get("title", "Unknown")
            transcript = data.get("transcript", "")
            if not transcript.strip():
                log_failure(logger, video_id, "empty transcript")
                v["status"] = "failed"
                v["reason"] = "empty_transcript"
                progress.advance(task)
                continue

            # Truncate only for small-context models (e.g. gpt-3.5-turbo 16k); gpt-4o-mini 128k can take full
            if "3.5" in model_name and len(transcript) > MAX_TRANSCRIPT_CHARS:
                transcript = transcript[:MAX_TRANSCRIPT_CHARS] + "\n\n[Transcript truncated for length.]"
                logger.debug("Truncated transcript for %s to %s chars", video_id, MAX_TRANSCRIPT_CHARS)

            prompt = PROMPT_TEMPLATE.format(title=title, transcript=transcript)
            text = ""
            max_retries = 4
            for attempt in range(max_retries):
                try:
                    if provider == "openai":
                        text = _call_openai(prompt, model_name)
                    else:
                        text = _call_gemini(prompt, llm_client, model_name)
                    break
                except Exception as e:
                    err_str = str(e)
                    is_rate_limit = (
                        "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                        or "quota" in err_str.lower()
                        or "rate_limit" in err_str.lower()
                    )
                    if is_rate_limit and attempt < max_retries - 1:
                        wait_s = 60
                        match = re.search(r"retry in (\d+(?:\.\d+)?)\s*s", err_str, re.I)
                        if match:
                            wait_s = max(30, min(120, float(match.group(1))))
                        logger.warning("%s rate limit for %s, waiting %.0fs then retry (%s/%s)", provider, video_id, wait_s, attempt + 1, max_retries - 1)
                        time.sleep(wait_s)
                        continue
                    log_failure(logger, video_id, err_str)
                    v["status"] = "failed"
                    v["reason"] = err_str[:200]
                    break
            if not text:
                progress.advance(task)
                time.sleep(delay_seconds)
                continue

            sections = parse_llm_response(text)
            llm_notes = "\n\n".join(f"## {k}\n{v}" for k, v in sections.items() if v)

            out = {
                **data,
                "gemini_sections": sections,
                "gemini_notes": llm_notes,
            }
            try:
                enriched_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
                v["status"] = "ok"
            except Exception as e:
                log_failure(logger, video_id, str(e))
                v["status"] = "failed"
                v["reason"] = str(e)

            progress.advance(task)
            time.sleep(delay_seconds)

    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Enrichment agent (%s) finished. Enriched files in %s", provider, ENRICHED_DIR)
    return manifest
