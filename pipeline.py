#!/usr/bin/env python3
"""
Orchestrator: run transcript → enrichment (OpenAI/Gemini) → notebooklm → obsidian.
Supports --resume (skip existing files) and --only <agent>.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from rich.console import Console
from rich.table import Table

from utils.logger import setup_logger

DATA_DIR = Path(__file__).resolve().parent / "data"
MANIFEST_PATH = DATA_DIR / "manifest.json"
RUN_REPORT_PATH = DATA_DIR / "run_report.md"


def parse_args():
    p = argparse.ArgumentParser(description="YouTube → OpenAI/Gemini → NotebookLM → Obsidian pipeline")
    p.add_argument("--resume", action="store_true", help="Skip videos that already have output files")
    p.add_argument(
        "--only",
        choices=["transcripts", "enrichment", "notebooklm", "obsidian"],
        default=None,
        help="Run only this agent (enrichment = OpenAI or Gemini)",
    )
    return p.parse_args()


def main():
    args = parse_args()
    console = Console()
    logger = setup_logger()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    manifest = None

    agents_run = []
    errors = []

    def run(name: str, fn, *a, **kw):
        agents_run.append(name)
        try:
            return fn(*a, **kw)
        except Exception as e:
            errors.append((name, str(e)))
            logger.exception("Agent %s failed: %s", name, e)
            raise

    try:
        # 1. Transcripts
        if args.only is None or args.only == "transcripts":
            from agents.transcript_agent import run_transcript_agent
            manifest = run("transcripts", run_transcript_agent, args.resume)
        elif MANIFEST_PATH.exists():
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

        if manifest is None and (args.only in ("enrichment", "notebooklm", "obsidian") or args.only is None):
            if not MANIFEST_PATH.exists():
                console.print("[red]No manifest found. Run without --only or run transcripts first.[/red]")
                return 1
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

        # 2. Enrichment (OpenAI or Gemini)
        if args.only is None or args.only == "enrichment":
            from agents.gemini_agent import run_gemini_agent
            manifest = run("enrichment", run_gemini_agent, manifest, args.resume)

        # 3. NotebookLM
        if args.only is None or args.only == "notebooklm":
            from agents.notebooklm_agent import run_notebooklm_agent
            manifest = run("notebooklm", run_notebooklm_agent, manifest)

        # 4. Obsidian
        if args.only is None or args.only == "obsidian":
            from agents.obsidian_agent import run_obsidian_agent
            run("obsidian", run_obsidian_agent, manifest)

    except Exception:
        console.print("[red]Pipeline stopped due to an error.[/red]")
        # Still write report if we have partial manifest
        if manifest is None and MANIFEST_PATH.exists():
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    # Run report
    report_lines = [
        "# Pipeline Run Report",
        "",
        f"**Date:** {datetime.now().isoformat()}",
        f"**Resume:** {args.resume}",
        f"**Only:** {args.only or 'all'}",
        "",
        "## Agents run",
        "",
    ]
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

    RUN_REPORT_PATH.write_text("\n".join(report_lines), encoding="utf-8")
    console.print(f"[dim]Run report saved to {RUN_REPORT_PATH}[/dim]")

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
