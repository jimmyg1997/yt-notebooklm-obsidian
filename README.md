# YouTube → NotebookLM → Obsidian 📺✨

Turn any YouTube playlist into **searchable, linked notes** with summaries, key ideas, and NotebookLM artifacts – ready for Obsidian or any Markdown editor.

This project started from a real use case: a 51‑video Greek business podcast playlist. As a Greek investor and long‑time follower of local finance creators, this repo is also a small “thank you” to **Chris Tsounis** and the wider Greek financial community for sharing so much practical knowledge.

You can reuse the same pipeline for **any playlist** – but to make it concrete, here’s the real example it was built on.

---

## Example: 51‑video Greek business playlist 💼🇬🇷

- **Playlist**: Ολ Ιν (business / career podcast) – part of the Greek finance / business creator ecosystem  
- **Videos**: 51 (50 with usable subtitles)  
- **Approx. cost**: ~**$0.13** for enrichment with `gpt-4o-mini`  
- **Output**:
  - 50 enriched JSON files in `data/enriched/`
  - 50 Markdown notes + index in your vault
  - NotebookLM notebook with all 50 sources
  - `podcast.mp3`, `mindmap.json`, `quiz.json`, `flashcards.json` downloaded and linked from Obsidian

### Obsidian navigation demo (GIF) 🧭

Short walkthrough of the example playlist vault – opening the index, jumping into individual episode notes, and exploring the graph:

![Obsidian demo](examples/greek-business-playlist/obsidian-demo.gif)

### Graph views

- **High‑level graph (all notes + artifacts)** 🌐  
  ![Obsidian graph view example](examples/greek-business-playlist/images/graph.png)

- **Zoomed‑in example graph** 🔍  
  ![Obsidian example graph](examples/greek-business-playlist/example-obsidian-graph.png)

Your own vault and notes stay local; these visuals come from the documented example playlist.

### Inspired by Greek financial creators

[![Ολ Ιν / Greek finance playlist thumbnail](https://i.ytimg.com/vi/383CnQdrGsM/hqdefault.jpg)](https://www.youtube.com/watch?v=383CnQdrGsM&list=PLAQ71P0f2W3nJq8WD_Y9kRHZrHwg5c9tB)

Special thanks to **Christos (Chris) Tsounis** and **Spyros Andrianos**, along with the wider Greek finance / business community, for sharing so much practical knowledge — this repo is one way to turn that content into a living knowledge graph. 💚  

- **Christos Tsounis** – YouTube: [`Chris Tsounis`](https://www.youtube.com/channel/UCthUKUdCLSe0P-wyVLE9XeQ) · Site: [`christsounis.com`](https://christsounis.com/)  
- **Spyros Andrianos** – Site / bio: [`Men Of Style – Spyros Andrianos`](https://menofstyle.gr/spyros-andrianos-biografiko/)

---

## Features 🚀

- **End‑to‑end automation**
  - `YouTube playlist or whole channel → transcripts → enrichment → NotebookLM artifacts → Obsidian notes`
- **Language‑aware transcripts**
  - Prefers Greek subtitles (`el`), falls back to English (`en`) automatically.
- **Affordable transcript enrichment**
  - Default: **OpenAI `gpt-4o-mini`** (~$0.13 for 51 videos, see `docs/COST_51_VIDEOS.md`).
  - Optional: Gemini (`gemini-2.0-flash`) if you prefer Google’s API.
- **NotebookLM integration (optional)**
  - Creates/reuses a notebook, adds all video URLs as sources.
  - Generates **Audio Overview (podcast)**, **Mind Map**, **Quiz**, **Flashcards**.
- **Obsidian‑ready notes**
  - One Markdown note per video with summary, key ideas, takeaways, quotes, and `[[wikilinks]]`.
  - `00 - Index.md` with links to all video notes and NotebookLM artifacts.
  - Works with or without Obsidian (notes live in a normal folder).
- **Resume‑safe**
  - `--resume` and idempotent steps: if the run crashes halfway, you can resume without redoing everything.

---

## Who is this for? 👇

- **Solo learners & investors** who want to turn long playlists (business, tech, finance, anything) into a personal “mini‑MBA” knowledge base.
- **Creators & educators** who publish playlists and want to ship Obsidian‑ready notes + NotebookLM artifacts for their audience.
- **Knowledge workers / teams** who onboard via YouTube courses and want linked notes, quizzes, and audio overviews instead of raw videos.

## Requirements 🧱

- **Python 3.10+**
- **YouTube playlist URL** (with `list=...`) **or whole channel URL** (e.g. `https://www.youtube.com/@ChannelName`) — the pipeline analyses all videos from the playlist or channel
- **OpenAI API key** (recommended) or **Gemini API key**
- **Obsidian** optional — notes can be written to a normal folder and opened in Obsidian later.  
  See **`docs/OBSIDIAN_USAGE.md`** for how to use the vault and the NotebookLM artifacts.

---

## Quick start ⚡

### 1. Clone and install

```bash
git clone https://github.com/jimmyg1997/yt-notebooklm-obsidian.git
cd yt-notebooklm-obsidian
pip install -r requirements.txt
playwright install chromium   # used by notebooklm-py for login
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with at least:

```env
# Required: playlist URL (with list=...) or channel URL (all uploads)
PLAYLIST_URL=https://www.youtube.com/watch?v=...&list=PLxxxxx
# Or use a whole channel, e.g.:
# PLAYLIST_URL=https://www.youtube.com/@ChannelName

# Enrichment: OpenAI (default) or Gemini
OPENAI_API_KEY=sk-...          # preferred; uses gpt-4o-mini
OPENAI_MODEL=gpt-4o-mini       # default

# Optional: use Gemini instead (only if OPENAI_API_KEY is not set)
# GEMINI_API_KEY=...
```

Optional:

```env
# Obsidian: if set, notes are mirrored here; primary output is always data/<name>/vault/
OBSIDIAN_VAULT_PATH=/Users/you/Documents/MyVault
OBSIDIAN_SUBFOLDER=YouTube Playlists

# NotebookLM notebook name (only used if you run the notebooklm step)
NOTEBOOKLM_NOTEBOOK_NAME=My Playlist

# Optional: reuse a specific NotebookLM notebook instead of creating a new one
# NOTEBOOKLM_NOTEBOOK_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

OUTPUT_LANGUAGE=english
```

### 3. Run the pipeline

**Option A — one script (setup + run, optional URL and args):**

```bash
./run_pipeline.sh                                    # use PLAYLIST_URL from .env
./run_pipeline.sh "https://youtube.com/@Channel"     # channel URL (all uploads)
./run_pipeline.sh "https://youtube.com/playlist?list=PLxxxx" --limit 20   # playlist, first 20 videos
./run_pipeline.sh "https://youtube.com/@Channel" --limit 10 --resume
./run_pipeline.sh --resume                           # skip already-processed videos
./run_pipeline.sh --update                           # incremental update (resume + add only missing NotebookLM sources)
./run_pipeline.sh --skip-notebooklm                  # run without NotebookLM step
./run_pipeline.sh --setup-only                       # only install deps and check .env
```

The script:

- creates `.env` from `.env.example` if missing,
- checks Python,
- installs Python dependencies and Playwright chromium,
- ensures `PLAYLIST_URL` is set,
- then runs the pipeline.

**Option B — run steps manually:**

**Full run (all four steps):**

```bash
python pipeline.py
```

**Step by step (recommended for the first run):**

```bash
# 1) Get transcripts (Greek/English subtitles)
python pipeline.py --only transcripts

# 2) Enrich transcripts (OpenAI gpt-4o-mini by default)
python pipeline.py --only enrichment --resume

# 3) Optional: NotebookLM (create/reuse notebook, add sources if new, generate podcast + mind map + quiz + flashcards)
notebooklm login   # one-time: sign in with Google; session saved under ~/.notebooklm/
python pipeline.py --only notebooklm

# 4) Write Obsidian (or local) Markdown notes
python pipeline.py --only obsidian
```

**Incremental update mode (recommended for recurring playlists):**

```bash
# Uses PLAYLIST_URL from .env
python pipeline.py --update

# or via helper script
./run_pipeline.sh --update
```

`--update` does three things:
- implies `--resume` (skip already processed transcript/enrichment files),
- reuses your existing NotebookLM notebook (if configured/saved),
- adds **only** YouTube sources that are not already in that notebook.

**Resume after a crash or interrupt:** skips videos that already have output files.

```bash
python pipeline.py --resume
# or
python pipeline.py --only enrichment --resume
```

---

## Configuration reference (`.env`)

| Variable | Required | Description |
|---------|----------|-------------|
| `EXPERIMENT_NAME` | No | Short slug for this run (e.g. `metabolomic-medicine`). Creates `data/NAME/` and vault subfolder so you can run multiple experiments. |
| `PLAYLIST_URL` | **Yes** | YouTube playlist URL (with `list=...`) or **whole channel URL** (e.g. `https://www.youtube.com/@ChannelName`) to analyse all uploads. |
| `OPENAI_API_KEY` | Recommended | OpenAI key; if set, OpenAI is used for enrichment. |
| `OPENAI_MODEL` | No | OpenAI model, default `gpt-4o-mini`. |
| `GEMINI_API_KEY` | Optional | Used if `OPENAI_API_KEY` is not set. |
| `GEMINI_MODEL` | No | Gemini model, default `gemini-2.0-flash`. |
| `OBSIDIAN_VAULT_PATH` | Optional | If set, notes are mirrored here (under `OBSIDIAN_SUBFOLDER/experiment-name`). Primary output is always `data/<name>/vault/`. |
| `OBSIDIAN_SUBFOLDER` | Optional | Subfolder inside your vault for the mirror, default `YouTube Playlists`. |
| `OUTPUT_LANGUAGE` | Optional | Enrichment output language (`english` or `greek`). |
| `API_DELAY_SECONDS` | Optional | Delay between enrichment API calls (OpenAI default 2s; Gemini may need more). |
| `TRANSCRIPT_DELAY_SECONDS` | Optional | Delay between subtitle downloads to avoid YouTube 429s. |
| `NOTEBOOKLM_NOTEBOOK_NAME` | Optional | Name for new NotebookLM notebooks. |
| `NOTEBOOKLM_NOTEBOOK_ID` | Optional | If set (or present in `data/manifest.json`), the pipeline **reuses** this notebook instead of creating a new one. |
| `NOTEBOOKLM_SOURCE_DELAY` | Optional | Delay between adding NotebookLM sources (seconds). |
| `NOTEBOOKLM_AUDIO_TIMEOUT` | Optional | Max seconds to wait for the Audio Overview generation (default 1200). |

---

## NotebookLM integration 🎧🧠

- On the **first** NotebookLM run, the pipeline:
  - logs in via your existing `notebooklm-py` browser session,
  - creates a notebook named `NOTEBOOKLM_NOTEBOOK_NAME`,
  - adds each `status == "ok"` video URL as a source (with delay between calls),
  - generates **Audio Overview**, **Mind Map**, **Quiz**, **Flashcards**,
  - downloads them into `data/notebooklm_outputs/`,
  - and stores the notebook id in `data/manifest.json` as `notebooklm_notebook_id`.

- On **later** runs:
  - if `NOTEBOOKLM_NOTEBOOK_ID` is set in `.env` or `notebooklm_notebook_id` exists in `manifest.json`,
  - the pipeline **reuses** that notebook,
  - and performs source sync by adding **only missing** YouTube URLs (no duplicates).

To force a **new** notebook:

- remove `notebooklm_notebook_id` from `data/manifest.json`, and
- unset `NOTEBOOKLM_NOTEBOOK_ID` in `.env`.

---

## Output layout 🗂️

**All output for a run lives in one folder** (with or without an experiment name). Notes are always written into `data/.../vault/` so you can open that folder directly in Obsidian.

**With an experiment name** (e.g. `EXPERIMENT_NAME=metabolomic-medicine` or `--name metabolomic-medicine`):

```text
data/metabolomic-medicine/
├── transcripts/               # Raw transcript JSON per video
├── enriched/                  # Enrichment output JSON per video
├── notebooklm_outputs/        # Podcast, mindmap, quiz, flashcards
├── vault/                     # ← Open this folder in Obsidian (File → Open folder as vault)
│   ├── 00 - Index.md
│   ├── 01 - Video Title.md
│   ├── ...
│   └── notebooklm/
├── manifest.json
└── run_report.md
```

**Without an experiment name** (single default run):

```text
data/
├── transcripts/
├── enriched/
├── notebooklm_outputs/
├── vault/                     # ← Obsidian notes
├── manifest.json
└── run_report.md
```

If `OBSIDIAN_VAULT_PATH` is set, notes are also mirrored into your main vault under `YouTube Playlists/<experiment-name>/` so they appear in your existing Obsidian app.

For how to use all of this **inside Obsidian** (graph view, NotebookLM artifacts, etc.), see **`docs/OBSIDIAN_USAGE.md`**.

---

## Enrichment backends: OpenAI vs Gemini

| | OpenAI (default) | Gemini |
|--|------------------|--------|
| **Model** | `gpt-4o-mini` | `gemini-2.0-flash` |
| **Cost (≈51 videos)** | ~**$0.13** total | Free tier (quota limits; may 429) |
| **Context** | 128k (full transcript) | 1M (full transcript) |

Set `OPENAI_API_KEY` in `.env` to use OpenAI; leave it unset and set `GEMINI_API_KEY` to use Gemini.  
See `docs/COST_51_VIDEOS.md` for the cost breakdown we measured on a 51‑video playlist.

---

## Run a single step 🧪

```bash
python pipeline.py --only transcripts
python pipeline.py --only enrichment
python pipeline.py --only notebooklm
python pipeline.py --only obsidian
```

Use `--resume` with `enrichment` (and the full pipeline) to skip videos that already have enriched files.

---

## CLI arguments (argument-based control) 🎛️

You can drive the pipeline from the command line instead of (or together with) `.env`:

| Argument | Short | Description |
|----------|--------|-------------|
| `--name` | `-m` | **Experiment/run name.** Creates `data/NAME/` (transcripts, enriched, manifest, etc.) so you can run multiple experiments without overwriting. Use a short slug (e.g. `metabolomic-medicine`). From env: `EXPERIMENT_NAME`. |
| `--url` | `-u` | Playlist or channel URL. Overrides `PLAYLIST_URL` from `.env`. |
| `--source` | | Treat URL as `auto` (detect), `channel`, or `playlist`. Default: `auto`. |
| `--limit` | `-n` | Max number of videos to process (e.g. `--limit 20`). No limit if omitted. |
| `--resume` | | Skip videos that already have transcripts/enriched output. |
| `--update` | | Incremental update mode: implies `--resume`, reuses NotebookLM notebook, adds only missing sources. |
| `--only` | | Run only one step: `transcripts`, `enrichment`, `notebooklm`, `obsidian`. |

**Examples:**

```bash
# Most common recurring run (playlist already in .env):
python pipeline.py --update

# Channel URL, first 30 videos only
python pipeline.py --url "https://www.youtube.com/@MetabolomicMedicine" --limit 30

# Playlist URL from CLI, then resume later
python pipeline.py -u "https://www.youtube.com/playlist?list=PLxxxx" -n 50
python pipeline.py --resume

# Incremental update with explicit URL override
python pipeline.py --update --url "https://www.youtube.com/playlist?list=PLxxxx"

# Force URL to be treated as channel (e.g. if auto-detect fails)
python pipeline.py --url "https://www.youtube.com/c/SomeChannel" --source channel --limit 10
```

If you omit `--url`, the pipeline uses `PLAYLIST_URL` from `.env`.

**Per-experiment folders:** Set `EXPERIMENT_NAME` in `.env` or pass `--name my-experiment` so this run uses `data/my-experiment/` for transcripts, enriched files, manifest, and run report. Obsidian notes go to `OBSIDIAN_VAULT_PATH/YouTube Playlists/my-experiment/`. Run another experiment with a different `--name` and they stay separate.

**Opening the vault for an experiment:** All notes are in **`data/<experiment-name>/vault/`**. In Obsidian: **File → Open folder as vault** → choose that folder (e.g. `.../yt-notebooklm-obsidian/data/metabolomic-medicine/vault`). Start from `00 - Index.md`. If you set `OBSIDIAN_VAULT_PATH`, the same notes are mirrored into your main vault under **YouTube Playlists / &lt;experiment-name&gt;**.

---

## Vault Dashboard (local web UI)

Browse all vaults and explore notes in the browser — folder tree, search, backlinks, bilingual UI (EL/EN), and scoped graph views.

**Full walkthrough:** [`docs/USER_WALKTHROUGH.md`](docs/USER_WALKTHROUGH.md)

```bash
pip install -r requirements.txt   # includes fastapi + uvicorn
./run_dashboard.sh                # http://127.0.0.1:8787
```

### Dashboard screenshots

**Start here:** [`docs/USER_WALKTHROUGH.md`](docs/USER_WALKTHROUGH.md) — full visual tour with 18 annotated screenshots.

| Home — ingest + vault library | Vault cards (covers & themes) | Ingest — create new vault |
|:---:|:---:|:---:|
| ![Home](docs/screenshots/01-dashboard-home.png) | ![Cards](docs/screenshots/06-vault-cards.png) | ![Ingest](docs/screenshots/05-ingest-new-vault-form.png) |

| Explorer — Topics tree | Index note | Video note + frame captures |
|:---:|:---:|:---:|
| ![Tree](docs/screenshots/08-explorer-topics-tree.png) | ![Index](docs/screenshots/09-explorer-index-note.png) | ![Video](docs/screenshots/11-explorer-video-note-frames.png) |

| Graph overview | Graph — one theme | Graph — full vault |
|:---:|:---:|:---:|
| ![Graph](docs/screenshots/03-explorer-graph.png) | ![Theme graph](docs/screenshots/04-graph-theme-scope.png) | ![Full graph](docs/screenshots/13-graph-full-scope.png) |

| Large playlist (Ολ Ιν) — index | Large playlist — graph |
|:---:|:---:|
| ![Ol In index](docs/screenshots/14-ol-in-index-note.png) | ![Ol In graph](docs/screenshots/15-ol-in-graph.png) |

Regenerate screenshots anytime (dashboard must be running):

```bash
.venv/bin/python scripts/capture_dashboard_screenshots.py
```

**Discovers vaults from:**
- `data/*/vault/` (pipeline experiments)
- `Vaults/*/` (local Obsidian vault roots)
- `OBSIDIAN_VAULT_PATH` in `.env` (if set to a real path)

Optional: `DASHBOARD_PORT=8787` in `.env` to change the port.

**Single-video ingest:** On the dashboard home page, paste one YouTube URL and choose:

- **Existing vault** — add to a vault you already have
- **New vault — I'll name it** — enter name + optional description, then ingest
- **New vault — auto from first video** — vault name, description, and starter theme notes are inferred after the first video is enriched

Requires `ffmpeg` on your PATH and an OpenAI or Gemini API key in `.env`.

**Progress bars:** Long-running steps show progress in the dashboard and CLI (`pipeline.py`, ingest jobs).

**Vault editing:** Click ✎ on a vault card or **Edit vault** in explorer — change name, description, themes.

**Graph view:** In explorer, open the **Graph** tab. Scopes: **overview** (fast, theme-level), **theme**, **subtopic**, or **full**. Click nodes to open notes.

**Topics:** Hierarchy is **theme → cluster → subtopic** under `Topics/`. Each theme note lists **Mentioned in** episodes and **Related topics**. Use **Sync topics** in explorer to regenerate topic notes for existing vaults.

**Language:** UI strings and note section headers switch between Greek and English; episode body text stays in the source output language unless re-ingested with `OUTPUT_LANGUAGE=greek`.

**Docs:** [`docs/USER_WALKTHROUGH.md`](docs/USER_WALKTHROUGH.md) · [`docs/OBSIDIAN_USAGE.md`](docs/OBSIDIAN_USAGE.md) · [`docs/USER_TEST_SCENARIOS.md`](docs/USER_TEST_SCENARIOS.md) · automated checks: `pytest tests/`

---

## Troubleshooting

- **yt-dlp: “No supported JavaScript runtime could be found”**  
  This is a warning. Transcript extraction usually still works. To silence it or improve compatibility, install Node.js or [Deno](https://deno.land/) and ensure it’s on your `PATH`; yt-dlp will use it automatically.

- **No subtitles for some videos**  
  Those videos stay as `status: "failed"` in `manifest.json`; only videos with transcripts get enriched and written to Obsidian.

- **NotebookLM login expired**  
  Run:
  ```bash
  notebooklm login
  ```

- **OpenAI “module not found”**  
  ```bash
  pip install openai
  ```

- **YouTube 429 (rate limit)**  
  The pipeline already spaces out requests, but you can increase `TRANSCRIPT_DELAY_SECONDS` in `.env` if needed.

- **Audio overview keeps timing out**  
  Increase `NOTEBOOKLM_AUDIO_TIMEOUT` (seconds) in `.env` and re‑run `python pipeline.py --only notebooklm`.  
  Even if our wait times out, the NotebookLM task may still finish in the web UI.

---

## Contributing / forking

- This repo is intended as a **template** you can fork:
  - swap in different enrichment models or prompts,
  - change the note format,
  - integrate with other tools (Logseq, Notion, etc.).
- If you publish a fork or add integrations, consider mentioning the original project so others can find it.

---

## License

MIT. Use at your own risk – NotebookLM uses unofficial APIs under the hood and may change without notice.

