"""Orchestrate single-video ingest: transcript → enrich → screenshots → vault note."""
from __future__ import annotations

import json
import shutil
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from agents.gemini_agent import run_gemini_agent
from agents.screenshot_agent import run_screenshot_agent
from agents.transcript_agent import _video_id_from_url, run_single_video_transcript
from dashboard.services.single_video_writer import resolve_data_dir_for_vault, write_single_video_note
from dashboard.services.vault_factory import (
    create_vault,
    create_vault_from_profile,
    generate_vault_profile_from_enriched,
    write_vault_meta,
)
from dashboard.services.vault_scanner import decode_vault_id, PROJECT_ROOT
from utils.progress_helpers import (
    INGEST_STEP_LABELS,
    INGEST_STEPS,
    ingest_progress_percent,
    ingest_step_index,
)

_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


@dataclass
class IngestJob:
    job_id: str
    status: str  # queued | running | done | failed
    step: str = ""
    video_url: str = ""
    vault_id: str = ""
    vault_mode: str = "existing"
    progress_percent: int = 0
    progress_label: str = ""
    progress_detail: str = ""
    step_index: int = 0
    steps_total: int = 0
    result: dict = field(default_factory=dict)
    error: str = ""
    created_at: str = ""
    updated_at: str = ""


def _set_job_progress(job: IngestJob, step: str, sub_percent: float = 0.0, detail: str = "") -> None:
    job.step = step
    job.progress_percent = ingest_progress_percent(job.vault_mode, step, sub_percent)
    job.progress_label = INGEST_STEP_LABELS.get(step, step.replace("_", " ").title())
    job.progress_detail = detail
    job.step_index, job.steps_total = ingest_step_index(job.vault_mode, step)
    job.updated_at = _now()


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _save_job(job: IngestJob) -> None:
    with _LOCK:
        _JOBS[job.job_id] = asdict(job)
    jobs_dir = PROJECT_ROOT / ".dashboard" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    (jobs_dir / f"{job.job_id}.json").write_text(json.dumps(asdict(job), indent=2), encoding="utf-8")


def get_job(job_id: str) -> dict | None:
    with _LOCK:
        if job_id in _JOBS:
            return dict(_JOBS[job_id])
    path = PROJECT_ROOT / ".dashboard" / "jobs" / f"{job_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _copy_staging_pipeline(staging: Path, data_dir: Path) -> None:
    for sub in ("transcripts", "enriched", "manifest.json"):
        src = staging / sub if sub != "manifest.json" else staging / "manifest.json"
        if not src.exists():
            continue
        if src.is_dir():
            dest = data_dir / sub
            dest.mkdir(parents=True, exist_ok=True)
            for f in src.glob("*"):
                if f.is_file():
                    shutil.copy2(f, dest / f.name)
        else:
            shutil.copy2(src, data_dir / "manifest.json")


def run_single_video_ingest(
    video_url: str,
    vault_id: str | None = None,
    *,
    vault_mode: str = "existing",
    vault_name: str | None = None,
    vault_description: str | None = None,
    job_id: str | None = None,
) -> dict:
    """Synchronous full pipeline. vault_mode: existing | manual | auto."""
    job_id = job_id or str(uuid.uuid4())
    job = IngestJob(
        job_id=job_id,
        status="running",
        step="transcript",
        video_url=video_url,
        vault_id=vault_id or "",
        vault_mode=vault_mode,
        steps_total=len(INGEST_STEPS.get(vault_mode, INGEST_STEPS["existing"])),
        created_at=_now(),
        updated_at=_now(),
    )
    _save_job(job)

    staging_dir: Path | None = None
    try:
        if vault_mode == "manual":
            if not (vault_name or "").strip():
                raise ValueError("Vault name is required for manual new vault")
            _set_job_progress(job, "create_vault", 50, "Setting up folders & index notes")
            _save_job(job)
            created = create_vault(
                name=vault_name.strip(),
                description=(vault_description or "").strip(),
                source="manual",
            )
            vault_id = created["id"]
            job.vault_id = vault_id
            job.result["vault_created"] = created
            _save_job(job)

        if vault_mode == "auto":
            staging_dir = PROJECT_ROOT / ".dashboard" / "ingest" / f"staging-{job_id}"
            staging_dir.mkdir(parents=True, exist_ok=True)
            data_dir = staging_dir
        else:
            if not vault_id:
                raise ValueError("vault_id is required for existing vault mode")
            vault_path = decode_vault_id(vault_id).resolve()
            if not vault_path.is_dir():
                raise FileNotFoundError(f"Vault not found: {vault_path}")
            data_dir = resolve_data_dir_for_vault(vault_path)
            data_dir.mkdir(parents=True, exist_ok=True)

        def _transcript_progress(detail: str) -> None:
            _set_job_progress(job, "transcript", 50, detail)
            _save_job(job)

        _set_job_progress(job, "transcript", 5, "Fetching subtitles…")
        _save_job(job)
        manifest = run_single_video_transcript(
            video_url,
            data_dir=data_dir,
            resume=False,
            on_progress=_transcript_progress,
        )

        ingest_video_id = _video_id_from_url(video_url)
        if not ingest_video_id:
            raise ValueError("Could not parse YouTube video ID from URL")

        video_entry = next(
            (v for v in manifest.get("videos", []) if v.get("id") == ingest_video_id),
            None,
        )
        if not video_entry or video_entry.get("status") != "ok":
            failed = video_entry or next(
                (v for v in manifest.get("videos", []) if v.get("id") == ingest_video_id),
                {},
            )
            raise RuntimeError(failed.get("reason") or "Transcript failed")

        video_id = ingest_video_id

        _set_job_progress(job, "enrichment", 20, "Summarizing transcript")
        _save_job(job)
        run_gemini_agent(manifest, resume=False, data_dir=data_dir, only_video_ids=[video_id])

        enriched_path = data_dir / "enriched" / f"{video_id}.json"
        if not enriched_path.exists():
            raise RuntimeError("Enrichment produced no output")

        enriched = json.loads(enriched_path.read_text(encoding="utf-8"))

        if vault_mode == "auto":
            _set_job_progress(job, "vault_profile", 30, "Generating name, description & themes")
            _save_job(job)
            profile = generate_vault_profile_from_enriched(enriched)
            created = create_vault_from_profile(profile)
            vault_id = created["id"]
            job.vault_id = vault_id
            job.result["vault_created"] = created
            vault_path = Path(created["path"])
            final_data_dir = vault_path.parent
            _copy_staging_pipeline(staging_dir, final_data_dir)
            enriched_path = final_data_dir / "enriched" / f"{video_id}.json"
            data_dir = final_data_dir
            _save_job(job)
        else:
            vault_path = decode_vault_id(vault_id).resolve()

        def _screenshot_progress(done: int, total: int, caption: str) -> None:
            pct = (done / total * 100.0) if total else 0
            _set_job_progress(job, "screenshots", pct, f"Frame {done}/{total}: {caption[:60]}")
            _save_job(job)

        _set_job_progress(job, "screenshots", 0, "Picking timestamps & extracting frames")
        _save_job(job)
        frames: list[dict] = []
        try:
            frames = run_screenshot_agent(
                enriched, vault_path, data_dir=data_dir, on_progress=_screenshot_progress
            )
        except Exception as exc:
            job.result["screenshot_warning"] = str(exc)

        _set_job_progress(job, "vault", 80, "Saving Markdown note & updating index")
        _save_job(job)
        note_result = write_single_video_note(vault_path, enriched_path, frames)

        try:
            from dashboard.services.vault_cover import ensure_vault_cover

            ensure_vault_cover(vault_path, force=True)
        except Exception:
            pass

        if vault_mode == "auto" and job.result.get("vault_created"):
            meta = {
                "name": job.result["vault_created"]["name"],
                "slug": job.result["vault_created"]["slug"],
                "description": job.result["vault_created"].get("description", ""),
                "themes": job.result["vault_created"].get("themes", []),
                "source": "auto",
                "seed_video_id": video_id,
                "seed_video_title": enriched.get("title"),
            }
            write_vault_meta(data_dir, meta)

        job.status = "done"
        _set_job_progress(job, "complete", 100, "Finished")
        job.result = {
            **job.result,
            **note_result,
            "vault_id": vault_id,
            "vault_path": str(vault_path),
            "data_dir": str(data_dir),
        }
        job.updated_at = _now()
        _save_job(job)
        return asdict(job)

    except Exception as e:
        job.status = "failed"
        job.error = str(e)
        job.updated_at = _now()
        _save_job(job)
        raise
    finally:
        if staging_dir and staging_dir.is_dir():
            shutil.rmtree(staging_dir, ignore_errors=True)


def start_single_video_ingest_async(
    video_url: str,
    vault_id: str | None = None,
    *,
    vault_mode: str = "existing",
    vault_name: str | None = None,
    vault_description: str | None = None,
) -> str:
    """Start ingest in background thread; return job_id."""
    job_id = str(uuid.uuid4())
    job = IngestJob(
        job_id=job_id,
        status="queued",
        step="queued",
        video_url=video_url,
        vault_id=vault_id or "",
        vault_mode=vault_mode,
        progress_percent=0,
        progress_label="Queued",
        steps_total=len(INGEST_STEPS.get(vault_mode, INGEST_STEPS["existing"])),
        created_at=_now(),
        updated_at=_now(),
    )
    _save_job(job)

    def _worker() -> None:
        try:
            run_single_video_ingest(
                video_url,
                vault_id,
                vault_mode=vault_mode,
                vault_name=vault_name,
                vault_description=vault_description,
                job_id=job_id,
            )
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()
    return job_id
