# PROMPT.md — Master Cursor Prompt

> Copy everything below this line and paste it into Cursor's chat as your first message.

---

## PASTE THIS INTO CURSOR:

```
You are a senior Python developer. Build me a complete automated pipeline project.

Read AGENTS.md and SKILLS.md fully before writing any code.

## What this project does
Automates this full workflow for a Greek YouTube playlist of 50 videos:
1. Extracts Greek transcripts from YouTube using yt-dlp
2. Enriches each transcript with Gemini 1.5 Flash (summaries, key ideas, quotes, wikilinks) — output in English
3. Creates a NotebookLM notebook, adds all 50 YouTube video URLs as sources using notebooklm-py, then generates Audio Overview + Mind Map + Quiz + Flashcards
4. Writes structured Obsidian Markdown notes for every video + a master MOC index note to my Obsidian vault

## Playlist
https://www.youtube.com/watch?v=383CnQdrGsM&list=PLAQ71P0f2W3nJq8WD_Y9kRHZrHwg5c9tB

## Project structure to create
- `pipeline.py` — main orchestrator with --resume and --only flags
- `agents/transcript_agent.py` — yt-dlp transcript extraction
- `agents/gemini_agent.py` — Gemini enrichment
- `agents/notebooklm_agent.py` — NotebookLM notebook creation + artifact generation
- `agents/obsidian_agent.py` — Obsidian vault writer
- `utils/vtt_cleaner.py` — VTT subtitle → plain text
- `utils/note_formatter.py` — Obsidian markdown formatter with YAML frontmatter
- `utils/logger.py` — shared logging with rich
- `.env.example` — all config variables documented
- `requirements.txt` — all dependencies pinned
- `README.md` — setup instructions

## Critical requirements
1. Greek subtitle language code is `el` — always try `el` first, then `en` fallback
2. Gemini prompt must say "The transcript is in Greek. Respond in English."
3. notebooklm-py uses async — wrap all NotebookLM calls in asyncio properly
4. Add 3 second delay between NotebookLM source additions (rate limit safety)
5. Never crash full pipeline for single video failure — log and continue
6. Support --resume flag: skip videos that already have files in ./data/
7. Show rich progress bars in terminal throughout
8. Every Obsidian note must have full YAML frontmatter including notebooklm_notebook_id
9. Create a MOC index note linking all 50 video notes + NotebookLM artifacts
10. Save run report to ./data/run_report.md at the end

## Gemini prompt to use for each video
Use this exact prompt structure in gemini_agent.py:

"""
The following is a transcript from a Greek YouTube video titled: "{title}"
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
"""

## Obsidian note template to use
Each note must follow this structure exactly:
```markdown
---
title: "{title}"
source: youtube
playlist: "{playlist_title}"
url: "{url}"
video_id: "{id}"
uploader: "{uploader}"
upload_date: {date}
duration: "{duration}"
language: greek
processed: {today}
notebooklm_notebook: "{notebook_id}"
tags:
  - youtube
  - greek
  - {playlist_slug}
  - inbox
---

# {title}

> 🎥 [Watch]({url}) | ⏱ {duration} | 📅 {date} | 👤 {uploader}

---

{gemini_notes}

---
*Auto-generated from Greek transcript using Gemini AI*
```

## .env variables needed
```
PLAYLIST_URL=https://www.youtube.com/watch?v=383CnQdrGsM&list=PLAQ71P0f2W3nJq8WD_Y9kRHZrHwg5c9tB
GEMINI_API_KEY=your_key_here
OBSIDIAN_VAULT_PATH=/Users/yourname/Obsidian/MyVault
OBSIDIAN_SUBFOLDER=YouTube Playlists
OUTPUT_LANGUAGE=english
API_DELAY_SECONDS=2
NOTEBOOKLM_NOTEBOOK_NAME=Greek Playlist Research
NOTEBOOKLM_SOURCE_DELAY=3
```

## After building the code, give me:
1. Exact terminal commands to install all dependencies
2. How to do the one-time NotebookLM login
3. How to get a free Gemini API key
4. The exact command to run the full pipeline
5. The exact command to run with --resume if it crashes halfway

Start by reading AGENTS.md and SKILLS.md, then build all files.
```
