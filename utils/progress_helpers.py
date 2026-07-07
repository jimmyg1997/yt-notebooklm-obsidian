"""Shared progress step maps and Rich CLI progress factory."""
from __future__ import annotations

from typing import Callable

# Dashboard ingest pipelines (ordered steps per vault_mode)
INGEST_STEPS: dict[str, list[str]] = {
    "existing": ["transcript", "enrichment", "screenshots", "vault"],
    "manual": ["create_vault", "transcript", "enrichment", "screenshots", "vault"],
    "auto": ["transcript", "enrichment", "vault_profile", "screenshots", "vault"],
}

INGEST_STEP_LABELS: dict[str, str] = {
    "queued": "Queued",
    "create_vault": "Creating vault",
    "transcript": "Transcript",
    "enrichment": "Enrichment",
    "vault_profile": "Vault profile (AI)",
    "screenshots": "Screenshots",
    "vault": "Writing note",
    "complete": "Complete",
}

PIPELINE_AGENTS = ["transcripts", "enrichment", "notebooklm", "obsidian"]

NOTEBOOKLM_ARTIFACT_STEPS = [
    "Adding sources",
    "Audio overview",
    "Mind map",
    "Quiz",
    "Flashcards",
]


def ingest_progress_percent(vault_mode: str, step: str, sub_percent: float = 0.0) -> int:
    """Overall 0–100 percent for dashboard ingest jobs. sub_percent is 0–100 within current step."""
    steps = INGEST_STEPS.get(vault_mode, INGEST_STEPS["existing"])
    if step == "complete":
        return 100
    if step == "queued":
        return 0
    try:
        idx = steps.index(step)
    except ValueError:
        return 0
    slice_size = 100.0 / len(steps)
    base = idx * slice_size
    within = (max(0.0, min(100.0, sub_percent)) / 100.0) * slice_size
    return min(99, int(base + within))


def ingest_step_index(vault_mode: str, step: str) -> tuple[int, int]:
    steps = INGEST_STEPS.get(vault_mode, INGEST_STEPS["existing"])
    if step not in steps:
        return 0, len(steps)
    return steps.index(step) + 1, len(steps)


def make_cli_progress(console=None):
    """Rich Progress bar with percentage for terminal tools."""
    from rich.console import Console
    from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=32),
        TaskProgressColumn(),
        TextColumn("•"),
        TextColumn("[cyan]{task.percentage:>3.0f}%"),
        console=console or Console(),
    )


ProgressCallback = Callable[[int, int, str], None]
