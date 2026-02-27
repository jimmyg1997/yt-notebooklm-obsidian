"""Shared logging with rich for the pipeline."""
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

# Ensure data dir exists for log file
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
ERROR_LOG = DATA_DIR / "errors.log"


def setup_logger(name: str = "youtube_lm", level: int = logging.INFO) -> logging.Logger:
    """Configure and return a logger with rich console + file handler for errors."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    console_handler = RichHandler(console=Console(stderr=True), show_path=False)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(ERROR_LOG, encoding="utf-8")
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(file_handler)

    return logger


def log_failure(logger: logging.Logger, video_id: str, reason: str) -> None:
    """Log a video failure to stderr and errors.log."""
    logger.warning("Video %s failed: %s", video_id, reason)
