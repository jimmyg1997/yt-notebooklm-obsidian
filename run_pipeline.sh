#!/usr/bin/env bash
#
# YouTube → AI → NotebookLM → Obsidian: full setup + pipeline runner.
# Usage:
#   ./run_pipeline.sh                    # run full pipeline (playlist from .env)
#   ./run_pipeline.sh "https://youtube.com/playlist?list=XXX"   # set playlist and run
#   ./run_pipeline.sh --resume           # run with --resume (skip existing files)
#   ./run_pipeline.sh --skip-notebooklm # run without NotebookLM step
#   ./run_pipeline.sh --setup-only       # only install deps and check env
#
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- Parse args ---
PLAYLIST_URL_ARG=""
RESUME=""
SKIP_NOTEBOOKLM=""
SETUP_ONLY=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --resume)
      RESUME="--resume"
      shift
      ;;
    --skip-notebooklm)
      SKIP_NOTEBOOKLM=1
      shift
      ;;
    --setup-only)
      SETUP_ONLY=1
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [PLAYLIST_URL] [--resume] [--skip-notebooklm] [--setup-only]"
      echo ""
      echo "  PLAYLIST_URL    Optional. YouTube playlist URL (with list=...). If omitted, uses .env"
      echo "  --resume        Skip videos that already have transcripts/enriched output"
      echo "  --skip-notebooklm  Run transcripts → enrichment → obsidian only (no NotebookLM)"
      echo "  --setup-only    Only install dependencies and check .env; do not run pipeline"
      exit 0
      ;;
    *)
      if [[ "$1" == https* ]] && [[ "$1" == *list=* ]]; then
        PLAYLIST_URL_ARG="$1"
      else
        echo "Unrecognized option or invalid playlist URL: $1" >&2
        exit 1
      fi
      shift
      ;;
  esac
done

# --- Setup: .env ---
if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    echo "[setup] No .env found; copying from .env.example. Edit .env and add your API key and playlist."
    cp .env.example .env
  else
    echo "[error] No .env or .env.example found." >&2
    exit 1
  fi
fi

# --- Update .env with playlist URL if provided ---
if [[ -n "$PLAYLIST_URL_ARG" ]]; then
  if grep -q '^PLAYLIST_URL=' .env 2>/dev/null; then
    if [[ "$(uname)" == "Darwin" ]]; then
      sed -i '' "s|^PLAYLIST_URL=.*|PLAYLIST_URL=${PLAYLIST_URL_ARG}|" .env
    else
      sed -i "s|^PLAYLIST_URL=.*|PLAYLIST_URL=${PLAYLIST_URL_ARG}|" .env
    fi
    echo "[setup] Updated .env PLAYLIST_URL"
  else
    echo "PLAYLIST_URL=$PLAYLIST_URL_ARG" >> .env
    echo "[setup] Appended PLAYLIST_URL to .env"
  fi
fi

# --- Ensure playlist is set ---
PLAYLIST_IN_ENV=$(grep -E '^PLAYLIST_URL=' .env 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'" || true)
if [[ -z "$PLAYLIST_URL_ARG" ]] && [[ -z "$PLAYLIST_IN_ENV" ]]; then
  echo "[error] PLAYLIST_URL is not set in .env. Add it or run: $0 'https://youtube.com/watch?v=...&list=PLxxxx'" >&2
  exit 1
fi

# --- Setup: Python ---
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
  echo "[error] Python not found. Install Python 3.10+." >&2
  exit 1
fi
PYTHON=$(command -v python3 2>/dev/null || command -v python)
echo "[setup] Using: $PYTHON $($PYTHON --version 2>&1)"

# --- Setup: install dependencies ---
echo "[setup] Installing Python dependencies..."
"$PYTHON" -m pip install -q -r requirements.txt
echo "[setup] Installing Playwright browser (chromium)..."
"$PYTHON" -m playwright install chromium 2>/dev/null || true

# --- Check API key (don't source whole .env to avoid side effects) ---
if ! grep -qE '^OPENAI_API_KEY=.' .env 2>/dev/null && ! grep -qE '^GEMINI_API_KEY=.' .env 2>/dev/null; then
  echo "[warn] Neither OPENAI_API_KEY nor GEMINI_API_KEY set in .env. Enrichment will fail until you add one."
fi
grep -E '^OPENAI_API_KEY=' .env 2>/dev/null | grep -q 'your_openai_key' && \
  echo "[warn] OPENAI_API_KEY looks like a placeholder. Replace it in .env for enrichment."

if [[ -n "$SETUP_ONLY" ]]; then
  echo "[setup] Setup complete. Run without --setup-only to run the pipeline."
  exit 0
fi

# --- Run pipeline ---
echo ""
echo "========== Pipeline: PLAYLIST from .env =========="
echo ""

if [[ -n "$SKIP_NOTEBOOKLM" ]]; then
  echo "[1/3] Transcripts..."
  "$PYTHON" pipeline.py --only transcripts $RESUME
  echo "[2/3] Enrichment..."
  "$PYTHON" pipeline.py --only enrichment $RESUME
  echo "[3/3] Obsidian..."
  "$PYTHON" pipeline.py --only obsidian
  echo ""
  echo "Done (transcripts → enrichment → obsidian). NotebookLM skipped."
else
  echo "[full] Running full pipeline (transcripts → enrichment → notebooklm → obsidian)..."
  "$PYTHON" pipeline.py $RESUME
  echo ""
  echo "Done."
fi

echo ""
echo "Output: data/transcripts, data/enriched, data/notebooklm_outputs (if ran NotebookLM), and your Obsidian vault or data/obsidian_export/"
echo "Report: data/run_report.md"
