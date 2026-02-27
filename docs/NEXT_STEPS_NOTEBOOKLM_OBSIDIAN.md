# Next steps: NotebookLM and Obsidian

You’ve already run **transcripts** and **enrichment** (50 videos). Here’s how to run **NotebookLM** and **Obsidian**.

---

## 1. NotebookLM (optional)

NotebookLM will create a notebook, add your 50 YouTube video URLs as sources, then generate and download: **Audio Overview**, **Mind Map**, **Quiz**, **Flashcards**.

### One-time setup

1. **Install the NotebookLM client** (with browser auth):
   ```bash
   pip install 'notebooklm-py[browser]'
   ```

2. **Log in** (opens browser; use your Google account):
   ```bash
   notebooklm login
   ```
   Session is stored under `~/.notebooklm/`. You only need to run this again if the session expires.

3. **Optional:** set notebook name in `.env`:
   ```env
   NOTEBOOKLM_NOTEBOOK_NAME=Ολ Ιν
   ```
   (Default is "Greek Playlist Research" if unset.)

### Run

```bash
python pipeline.py --only notebooklm
```

- Creates a new notebook with the name above.
- Adds all 50 video URLs as sources (with a short delay between each to avoid rate limits).
- Generates and downloads artifacts to `./data/notebooklm_outputs/` (podcast.mp3, mindmap.json, quiz.json, flashcards.json).
- Saves the notebook ID into `data/manifest.json` for the Obsidian step.

**Note:** Adding 50 sources and generating 4 artifacts can take a while (tens of minutes). If something fails, check the logs; you can run `--only notebooklm` again (it will create a *new* notebook each time).

---

## 2. Obsidian (or local Markdown export)

The Obsidian step turns your **enriched** JSON into Markdown notes and an index. It does **not** require NotebookLM to have run first; it will just omit NotebookLM artifact links if those files aren’t there.

### Option A: Export to a folder (no Obsidian required)

- Leave `OBSIDIAN_VAULT_PATH` **unset** or set to the example path in `.env.example`.
- Notes are written to:
  ```text
  ./data/obsidian_export/YouTube Playlists/
  ```
- You can open that folder in Obsidian later (“Open folder as vault”) or use the Markdown files anywhere.

### Option B: Write directly into your Obsidian vault

1. In `.env`, set your real vault path and subfolder:
   ```env
   OBSIDIAN_VAULT_PATH=/Users/dimitriosgeorgiou/Desktop/MyVault
   OBSIDIAN_SUBFOLDER=YouTube Playlists
   ```
   (Use your actual vault path; avoid the placeholder `/Users/yourname/...`.)

2. Run:
   ```bash
   python pipeline.py --only obsidian
   ```

Notes will be created under:
`<OBSIDIAN_VAULT_PATH>/<OBSIDIAN_SUBFOLDER>/`.

### What gets written

- **One note per video** (from `data/enriched/*.json`): title, summary, key ideas, takeaways, quotes, `[[wikilinks]]`, YAML frontmatter (url, playlist, etc.).
- **Index note** (e.g. `00 - Index.md`) with links to all video notes.
- If you ran NotebookLM, **NotebookLM artifacts** are copied into a `notebooklm/` subfolder and linked from the index (Audio Overview, Mind Map, Quiz, Flashcards).

---

## Order of commands

```bash
# 1) One-time: NotebookLM login
notebooklm login

# 2) Create notebook + add sources + generate artifacts (optional, can take a while)
python pipeline.py --only notebooklm

# 3) Generate Obsidian/local Markdown notes (works with or without NotebookLM)
python pipeline.py --only obsidian
```

You can run **only obsidian** anytime after enrichment; you’ll get all video notes and the index. Run **notebooklm** first only if you want the podcast, mind map, quiz, and flashcards included and linked from the export.
