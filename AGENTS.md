# AGENTS.md — YouTube → Gemini → NotebookLM → Obsidian Pipeline

## Project Overview
This project automates the full pipeline:
1. **Extract** Greek transcripts from a YouTube playlist (50 videos)
2. **Enrich** each transcript with Gemini AI (summaries, key ideas, wikilinks)
3. **Push** all YouTube URLs as sources into a NotebookLM notebook
4. **Generate** NotebookLM artifacts (audio overview, mind map, quiz, flashcards)
5. **Save** structured Markdown notes to Obsidian vault

---

## Agent Architecture

### Agent 1 — `transcript_agent.py`
**Role:** YouTube Playlist Extractor  
**Responsibility:**
- Accept a YouTube playlist URL
- Use `yt-dlp` to extract metadata + subtitles for all videos
- Prioritize Greek (`el`) subtitles, fallback to English (`en`)
- Clean VTT subtitle files into plain text
- Save raw transcripts as JSON to `./data/transcripts/`
- Return a manifest of all videos with transcript status

**Tools used:** `yt-dlp`  
**Input:** `PLAYLIST_URL` from `.env`  
**Output:** `./data/transcripts/{video_id}.json` per video + `./data/manifest.json`

---

### Agent 2 — `gemini_agent.py`
**Role:** AI Enrichment Engine  
**Responsibility:**
- Read transcripts from `./data/transcripts/`
- For each video, call Gemini 1.5 Flash API
- Parse structured response (Summary, Key Ideas, Takeaways, Quotes, Wikilinks)
- Handle Greek transcripts — always output notes in English (or Greek, per config)
- Save enriched notes as JSON to `./data/enriched/`
- Respect API rate limits with configurable delay

**Tools used:** `google-generativeai`  
**Input:** `./data/transcripts/*.json`  
**Output:** `./data/enriched/{video_id}.json` per video

---

### Agent 3 — `notebooklm_agent.py`
**Role:** NotebookLM Source Manager  
**Responsibility:**
- Authenticate with NotebookLM using `notebooklm-py` (browser cookie auth)
- Create a new notebook named after the playlist
- Add all 50 YouTube video URLs as sources (batch with retry logic)
- Wait for source processing to complete
- Generate artifacts in this order:
  1. Audio Overview (podcast)
  2. Mind Map
  3. Quiz (hard difficulty)
  4. Flashcards
- Download all artifacts to `./data/notebooklm_outputs/`
- Save notebook ID to `.env` for future runs

**Tools used:** `notebooklm-py`  
**Input:** `./data/manifest.json` (video URLs)  
**Output:** `./data/notebooklm_outputs/` (audio, mindmap, quiz, flashcards)

---

### Agent 4 — `obsidian_agent.py`
**Role:** Obsidian Vault Writer  
**Responsibility:**
- Read enriched data from `./data/enriched/`
- Format each video as a structured Obsidian Markdown note
- Include YAML frontmatter (title, url, date, tags, playlist, notebooklm_id)
- Add `[[wikilinks]]` from Gemini's concept extraction
- Create a master MOC (Map of Content) index note
- Create a playlist-level summary note referencing NotebookLM artifacts
- Write all notes directly to the configured Obsidian vault path

**Tools used:** Python `pathlib`, `yaml`  
**Input:** `./data/enriched/*.json` + `./data/notebooklm_outputs/`  
**Output:** Markdown files in `OBSIDIAN_VAULT_PATH/SUBFOLDER/`

---

### Agent 5 — `pipeline.py`
**Role:** Orchestrator  
**Responsibility:**
- Run all 4 agents in sequence
- Handle errors gracefully (skip failed videos, log issues)
- Show real-time progress in terminal with rich progress bars
- Generate a final run report in `./data/run_report.md`
- Support `--resume` flag to skip already-processed videos
- Support `--only` flag to run individual agents (e.g. `--only obsidian`)

**Tools used:** All agents above + `rich` for terminal UI  
**Input:** `.env` config  
**Output:** Complete pipeline run

---

## File Structure
```
project/
├── AGENTS.md              ← You are here
├── SKILLS.md              ← How each tool works
├── PROMPT.md              ← Master Cursor prompt
├── .env.example           ← Config template
├── .env                   ← Your actual config (gitignored)
├── requirements.txt       ← All dependencies
├── pipeline.py            ← Main orchestrator (run this)
├── agents/
│   ├── transcript_agent.py
│   ├── gemini_agent.py
│   ├── notebooklm_agent.py
│   └── obsidian_agent.py
├── utils/
│   ├── vtt_cleaner.py     ← VTT → plain text
│   ├── note_formatter.py  ← Obsidian markdown formatter
│   └── logger.py          ← Shared logging
└── data/                  ← Generated at runtime (gitignored)
    ├── manifest.json
    ├── transcripts/
    ├── enriched/
    └── notebooklm_outputs/
```

---

## Error Handling Rules (all agents must follow)
1. Never crash the full pipeline for a single failed video
2. Log failures to `./data/errors.log` with video ID and reason
3. Mark failed videos in manifest with `status: failed`
4. At the end, print a summary of successes vs failures
5. Support re-running — skip videos that already have output files

---

## Environment Variables (see `.env.example`)
```
PLAYLIST_URL=
GEMINI_API_KEY=
OBSIDIAN_VAULT_PATH=
OBSIDIAN_SUBFOLDER=
OUTPUT_LANGUAGE=english     # or: greek
API_DELAY_SECONDS=2
NOTEBOOKLM_NOTEBOOK_NAME=
```
