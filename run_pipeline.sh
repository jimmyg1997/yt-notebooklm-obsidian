#!/usr/bin/env bash
#
# YouTube → AI → NotebookLM → Obsidian: full setup + pipeline runner.
#
# 1) Set the parameters below (or pass them on the command line).
# 2) Run: ./run_pipeline.sh
#
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# =============================================================================
# CONFIGURATION — edit these, or override with command-line arguments
# =============================================================================

# Experiment/run name: all output for this run goes under data/NAME/
#   data/NAME/transcripts/  data/NAME/enriched/  data/NAME/notebooklm_outputs/
#   data/NAME/vault/  ← Obsidian notes (open this folder as vault in Obsidian)
#   data/NAME/manifest.json  data/NAME/run_report.md
# Use a short slug, e.g. metabolomic-medicine, greek-playlist (no spaces).
EXPERIMENT_NAME="metabolomic-medicine"

# YouTube playlist or channel URL (leave empty to use PLAYLIST_URL from .env)
# Examples:
#   URL="https://www.youtube.com/@MetabolomicMedicine"
#   URL="https://www.youtube.com/playlist?list=PLxxxx"
URL=""
LIMIT="200"              # Max number of videos to process (leave empty for no limit)
SOURCE="auto"           # How to treat URL: auto (detect) | channel | playlist
RESUME="false"          # Skip videos that already have transcripts/enriched output
UPDATE_MODE="false"     # Incremental update mode: implies resume + add only missing NotebookLM sources
SKIP_NOTEBOOKLM="false" # Run without NotebookLM step (transcripts → enrichment → obsidian only)
SETUP_ONLY="false"      # Only install dependencies and check .env; do not run the pipeline

# =============================================================================
# (Optional) Run only one step: transcripts | enrichment | notebooklm | obsidian
# Leave empty to run the full pipeline.
# ONLY_STEP=""
ONLY_STEP=""

# =============================================================================
# End of configuration
# =============================================================================

# --- Parse command-line overrides ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --name|-m)
      EXPERIMENT_NAME="$2"
      shift 2
      ;;
    --url|-u)
      URL="$2"
      shift 2
      ;;
    --limit|-n)
      LIMIT="$2"
      shift 2
      ;;
    --source)
      SOURCE="$2"
      shift 2
      ;;
    --resume)
      RESUME="true"
      shift
      ;;
    --update)
      UPDATE_MODE="true"
      RESUME="true"
      shift
      ;;
    --skip-notebooklm)
      SKIP_NOTEBOOKLM="true"
      shift
      ;;
    --setup-only)
      SETUP_ONLY="true"
      shift
      ;;
    --only)
      ONLY_STEP="$2"
      shift 2
      ;;
    --help|-h)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Options override the configuration block at the top of this script:"
      echo "  --name, -m NAME   Experiment name (data/NAME/ for this run; enables multiple experiments)"
      echo "  --url, -u URL     Playlist or channel URL"
      echo "  --limit, -n N      Max number of videos"
      echo "  --source TYPE      auto | channel | playlist"
      echo "  --resume           Skip already-processed videos"
      echo "  --update           Incremental update mode (implies --resume)"
      echo "  --skip-notebooklm  Omit NotebookLM step"
      echo "  --setup-only       Only install deps and check .env"
      echo "  --only STEP        Run only: transcripts | enrichment | notebooklm | obsidian"
      echo ""
      echo "You can also edit the CONFIGURATION section at the top of $0"
      exit 0
      ;;
    *)
      if [[ "$1" == https* ]]; then
        URL="$1"
      else
        echo "Unrecognized option: $1" >&2
        exit 1
      fi
      shift
      ;;
  esac
done

# --- Build pipeline arguments from config ---
BASE_ARGS=()
[[ -n "$EXPERIMENT_NAME" ]] && BASE_ARGS+=(--name "$EXPERIMENT_NAME")
[[ -n "$URL" ]] && BASE_ARGS+=(--url "$URL")
[[ -n "$LIMIT" ]] && BASE_ARGS+=(--limit "$LIMIT")
[[ -n "$SOURCE" ]] && BASE_ARGS+=(--source "$SOURCE")
RESUME_ARGS=()
[[ "$RESUME" == "true" ]] && RESUME_ARGS+=(--resume)
[[ "$UPDATE_MODE" == "true" ]] && RESUME_ARGS+=(--update)

PIPELINE_ARGS=("${BASE_ARGS[@]}" "${RESUME_ARGS[@]}")
[[ -n "$ONLY_STEP" ]] && PIPELINE_ARGS+=(--only "$ONLY_STEP")

# --- Setup: .env ---
if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    echo "[setup] No .env found; copying from .env.example. Edit .env and add your API key."
    cp .env.example .env
  else
    echo "[error] No .env or .env.example found." >&2
    exit 1
  fi
fi

# --- Update .env with URL if set in config ---
if [[ -n "$URL" ]]; then
  if grep -q '^PLAYLIST_URL=' .env 2>/dev/null; then
    if [[ "$(uname)" == "Darwin" ]]; then
      sed -i '' "s|^PLAYLIST_URL=.*|PLAYLIST_URL=${URL}|" .env
    else
      sed -i "s|^PLAYLIST_URL=.*|PLAYLIST_URL=${URL}|" .env
    fi
    echo "[setup] Updated .env PLAYLIST_URL"
  else
    echo "PLAYLIST_URL=$URL" >> .env
    echo "[setup] Appended PLAYLIST_URL to .env"
  fi
fi

# --- Ensure URL is set ---
PLAYLIST_IN_ENV=$(grep -E '^PLAYLIST_URL=' .env 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'" || true)
if [[ -z "$URL" ]] && [[ -z "$PLAYLIST_IN_ENV" ]]; then
  echo "[error] No URL. Set URL in the CONFIGURATION block at the top of $0 or PLAYLIST_URL in .env" >&2
  exit 1
fi

# --- Setup: use your existing venv (YT_VENV, venv_youtube_lm in project, or activated VIRTUAL_ENV) ---
# Script runs in a subshell and often does not see your interactive shell's PATH, so we need an explicit venv path.
if [[ -n "$YT_VENV" ]] && [[ -x "$YT_VENV/bin/python" ]]; then
  PYTHON="$YT_VENV/bin/python"
  echo "[setup] Using YT_VENV: $PYTHON $($PYTHON --version 2>&1)"
elif [[ -x "$SCRIPT_DIR/venv_youtube_lm/bin/python" ]]; then
  PYTHON="$SCRIPT_DIR/venv_youtube_lm/bin/python"
  echo "[setup] Using venv_youtube_lm: $PYTHON $($PYTHON --version 2>&1)"
elif [[ -n "$VIRTUAL_ENV" ]] && [[ -x "$VIRTUAL_ENV/bin/python" ]]; then
  PYTHON="$VIRTUAL_ENV/bin/python"
  echo "[setup] Using VIRTUAL_ENV: $PYTHON $($PYTHON --version 2>&1)"
else
  echo "[error] This script must use a virtual environment (to avoid 'externally-managed-environment' errors)." >&2
  echo "" >&2
  echo "Do one of the following:" >&2
  echo "  1. Put your venv in this project:  $SCRIPT_DIR/venv_youtube_lm/" >&2
  echo "  2. Or set and export your venv path:" >&2
  echo "     export YT_VENV=\$(dirname \$(dirname \$(which python)))" >&2
  echo "     ./run_pipeline.sh" >&2
  echo "     (Run the 'export' line in the same terminal where you activated venv_youtube_lm.)" >&2
  exit 1
fi

# --- Setup: install dependencies (inside venv) ---
echo "[setup] Installing Python dependencies..."
"$PYTHON" -m pip install -q -r requirements.txt
echo "[setup] Installing Playwright browser (chromium)..."
"$PYTHON" -m playwright install chromium 2>/dev/null || true

# --- Check API key ---
if ! grep -qE '^OPENAI_API_KEY=.' .env 2>/dev/null && ! grep -qE '^GEMINI_API_KEY=.' .env 2>/dev/null; then
  echo "[warn] Neither OPENAI_API_KEY nor GEMINI_API_KEY set in .env. Enrichment will fail until you add one."
fi
grep -E '^OPENAI_API_KEY=' .env 2>/dev/null | grep -q 'your_openai_key' && \
  echo "[warn] OPENAI_API_KEY looks like a placeholder. Replace it in .env for enrichment."

if [[ "$SETUP_ONLY" == "true" ]]; then
  echo "[setup] Setup complete. Run without --setup-only to run the pipeline."
  exit 0
fi

# --- Run pipeline ---
echo ""
echo "========== Pipeline =========="
echo "  Experiment: ${EXPERIMENT_NAME:-<default>}"
echo "  URL:    ${URL:-$PLAYLIST_IN_ENV}"
echo "  Limit:  ${LIMIT:-all}"
echo "  Source: $SOURCE"
echo "  Resume: $RESUME"
echo "  Update: $UPDATE_MODE"
echo "=============================="
echo ""

if [[ "$SKIP_NOTEBOOKLM" == "true" ]]; then
  echo "[1/3] Transcripts..."
  "$PYTHON" pipeline.py --only transcripts "${BASE_ARGS[@]}" "${RESUME_ARGS[@]}"
  echo "[2/3] Enrichment..."
  "$PYTHON" pipeline.py --only enrichment "${RESUME_ARGS[@]}"
  echo "[3/3] Obsidian..."
  "$PYTHON" pipeline.py --only obsidian "${BASE_ARGS[@]}"
  echo ""
  echo "Done (transcripts → enrichment → obsidian). NotebookLM skipped."
else
  if [[ -n "$ONLY_STEP" ]]; then
    echo "[only] Running step: $ONLY_STEP"
    "$PYTHON" pipeline.py "${PIPELINE_ARGS[@]}"
  else
    echo "[full] Running full pipeline (transcripts → enrichment → notebooklm → obsidian)..."
    "$PYTHON" pipeline.py "${PIPELINE_ARGS[@]}"
  fi
  echo ""
  echo "Done."
fi

echo ""
echo "=============================================="
echo "  OUTPUT (everything for this run)"
echo "=============================================="
if [[ -n "$EXPERIMENT_NAME" ]]; then
  ROOT="data/$EXPERIMENT_NAME"
  echo "  $ROOT/"
  echo "  ├── transcripts/       (raw transcript JSON per video)"
  echo "  ├── enriched/        (LLM-enriched JSON per video)"
  echo "  ├── notebooklm_outputs/  (podcast, mindmap, quiz, flashcards)"
  echo "  ├── vault/           ← Obsidian notes (open this folder in Obsidian)"
  echo "  │   ├── 00 - Index.md"
  echo "  │   ├── 01 - ... .md"
  echo "  │   └── notebooklm/"
  echo "  ├── manifest.json"
  echo "  └── run_report.md"
  echo ""
  echo "  Open in Obsidian:  File → Open folder as vault  →  $SCRIPT_DIR/$ROOT/vault"
else
  echo "  data/"
  echo "  ├── transcripts/"
  echo "  ├── enriched/"
  echo "  ├── notebooklm_outputs/"
  echo "  ├── vault/           ← Obsidian notes"
  echo "  ├── manifest.json"
  echo "  └── run_report.md"
  echo ""
  echo "  Open in Obsidian:  File → Open folder as vault  →  $SCRIPT_DIR/data/vault"
fi
echo "=============================================="
