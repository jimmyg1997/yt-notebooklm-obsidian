#!/usr/bin/env python3
"""
Orchestrator: run transcript → enrichment (OpenAI/Gemini) → notebooklm → obsidian.
Supports --resume (skip existing files), --only <agent>, and --name <experiment> for per-run folders.
"""
import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from rich.console import Console
from rich.table import Table

from utils.logger import setup_logger
from utils.progress_helpers import make_cli_progress

DATA_DIR = Path(__file__).resolve().parent / "data"


def _planned_agents(args) -> list[str]:
    """Agents that will run for this invocation."""
    if args.only:
        return [args.only]
    return ["transcripts", "enrichment", "notebooklm", "obsidian"]


AGENT_LABELS = {
    "transcripts": "Transcripts",
    "enrichment": "Enrichment",
    "notebooklm": "NotebookLM",
    "obsidian": "Obsidian vault",
}


def _sanitize_experiment_name(name: str) -> str:
    """Safe folder name from experiment/playlist name."""
    if not name or not name.strip():
        return ""
    s = re.sub(r"[^\w\s-]", "", name.strip())
    s = re.sub(r"[-\s]+", "-", s).strip().lower()
    return s or ""


def parse_args():
    p = argparse.ArgumentParser(
        description="YouTube → OpenAI/Gemini → NotebookLM → Obsidian pipeline",
        epilog="Examples: pipeline.py --url 'https://youtube.com/@Channel' --limit 20  |  pipeline.py --url 'https://youtube.com/playlist?list=PLxxx' --resume",
    )
    p.add_argument(
        "--url",
        "-u",
        metavar="URL",
        default=None,
        help="Playlist or channel URL (overrides PLAYLIST_URL from .env). Accepts playlist (list=...) or channel (@Handle, /channel/UC..., /c/name).",
    )
    p.add_argument(
        "--source",
        choices=["auto", "channel", "playlist"],
        default="auto",
        help="Treat --url as: auto (detect from URL), channel, or playlist. Default: auto.",
    )
    p.add_argument(
        "--limit",
        "-n",
        metavar="N",
        type=int,
        default=None,
        help="Max number of videos to process (default: no limit). Applied at transcript step.",
    )
    p.add_argument(
        "--name",
        "-m",
        metavar="NAME",
        default=None,
        help="Experiment/run name. Creates data/NAME/ for this run (transcripts, enriched, etc.). Enables multiple experiments. From env: EXPERIMENT_NAME.",
    )
    p.add_argument("--resume", action="store_true", help="Skip videos that already have output files")
    p.add_argument(
        "--update",
        action="store_true",
        help="Incremental update mode: implies --resume and adds only missing NotebookLM sources.",
    )
    p.add_argument(
        "--only",
        choices=["transcripts", "enrichment", "notebooklm", "obsidian"],
        default=None,
        help="Run only this agent (enrichment = OpenAI or Gemini)",
    )
    return p.parse_args()


def main():
    args = parse_args()
    if args.update:
        args.resume = True
    console = Console()
    logger = setup_logger()

    experiment_name = (args.name or os.environ.get("EXPERIMENT_NAME", "")).strip()
    if _sanitize_experiment_name(experiment_name):
        data_dir = DATA_DIR / _sanitize_experiment_name(experiment_name)
        logger.info("Experiment name %r -> data dir: %s", experiment_name, data_dir)
    else:
        data_dir = DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = data_dir / "manifest.json"
    run_report_path = data_dir / "run_report.md"

    manifest = None

    agents_run = []
    errors = []
    planned = _planned_agents(args)
    pipeline_progress = None
    pipeline_task = None

    def run(name: str, fn, *a, **kw):
        agents_run.append(name)
        if pipeline_progress and pipeline_task is not None:
            pipeline_progress.update(
                pipeline_task,
                description=AGENT_LABELS.get(name, name),
            )
        try:
            result = fn(*a, **kw)
            if pipeline_progress and pipeline_task is not None:
                pipeline_progress.advance(pipeline_task)
            return result
        except Exception as e:
            errors.append((name, str(e)))
            logger.exception("Agent %s failed: %s", name, e)
            raise

    try:
        with make_cli_progress(console) as pipeline_progress:
            pipeline_task = pipeline_progress.add_task("Pipeline", total=len(planned))

            # 1. Transcripts
            if args.only is None or args.only == "transcripts":
                from agents.transcript_agent import run_transcript_agent
                manifest = run(
                    "transcripts",
                    run_transcript_agent,
                    args.resume,
                    source_url=args.url,
                    source_type=args.source,
                    max_videos=args.limit,
                    data_dir=data_dir,
                )
            elif manifest_path.exists():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            if manifest is None and (args.only in ("enrichment", "notebooklm", "obsidian") or args.only is None):
                if not manifest_path.exists():
                    console.print("[red]No manifest found. Run without --only or run transcripts first.[/red]")
                    return 1
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            # 2. Enrichment (OpenAI or Gemini)
            if args.only is None or args.only == "enrichment":
                from agents.gemini_agent import run_gemini_agent
                manifest = run("enrichment", run_gemini_agent, manifest, args.resume, data_dir=data_dir)

            # 3. NotebookLM
            if args.only is None or args.only == "notebooklm":
                from agents.notebooklm_agent import run_notebooklm_agent
                manifest = run("notebooklm", run_notebooklm_agent, manifest, data_dir=data_dir, update_mode=args.update)

            # 4. Obsidian
            if args.only is None or args.only == "obsidian":
                from agents.obsidian_agent import run_obsidian_agent
                run("obsidian", run_obsidian_agent, manifest, data_dir=data_dir)

            if pipeline_task is not None:
                pipeline_progress.update(pipeline_task, description="Complete")

    except Exception:
        console.print("[red]Pipeline stopped due to an error.[/red]")
        # Still write report if we have partial manifest
        if manifest is None and manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Run report
    report_lines = [
        "# Pipeline Run Report",
        "",
        f"**Date:** {datetime.now().isoformat()}",
        f"**Resume:** {args.resume}",
        f"**Update mode:** {args.update}",
        f"**Only:** {args.only or 'all'}",
    ]
    if experiment_name:
        report_lines.append(f"**Experiment:** {experiment_name}")
    if args.url:
        report_lines.append(f"**URL (override):** {args.url}")
    if args.source != "auto":
        report_lines.append(f"**Source:** {args.source}")
    if args.limit is not None:
        report_lines.append(f"**Limit:** {args.limit} videos")
    report_lines.extend(["", "## Agents run", ""])
    for a in agents_run:
        report_lines.append(f"- {a}")
    report_lines.append("")

    if manifest:
        videos = manifest.get("videos", [])
        ok = sum(1 for v in videos if v.get("status") == "ok")
        failed = sum(1 for v in videos if v.get("status") == "failed")
        report_lines.extend([
            "## Summary",
            "",
            f"- **Videos in playlist:** {len(videos)}",
            f"- **OK:** {ok}",
            f"- **Failed:** {failed}",
            "",
        ])
        if failed:
            report_lines.append("### Failed videos")
            report_lines.append("")
            for v in videos:
                if v.get("status") == "failed":
                    report_lines.append(f"- {v.get('id', '?')} — {v.get('reason', 'unknown')}")
            report_lines.append("")

    if errors:
        report_lines.append("## Errors")
        report_lines.append("")
        for name, msg in errors:
            report_lines.append(f"- **{name}:** {msg}")
        report_lines.append("")

    run_report_path.write_text("\n".join(report_lines), encoding="utf-8")
    console.print(f"[dim]Run report saved to {run_report_path}[/dim]")

    # Summary table
    if manifest:
        videos = manifest.get("videos", [])
        ok = sum(1 for v in videos if v.get("status") == "ok")
        failed = len(videos) - ok
        table = Table(title="Pipeline summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green")
        table.add_row("Videos", str(len(videos)))
        table.add_row("OK", str(ok))
        table.add_row("Failed", str(failed))
        console.print(table)

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
