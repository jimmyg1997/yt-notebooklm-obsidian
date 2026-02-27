# Using the pipeline output in Obsidian

This guide explains what lands in your vault and how to use it day to day.

---

## What you have after the pipeline

- **One note per video** — Summary, key ideas, takeaways, quotes, and `[[wikilinks]]` from the AI.
- **00 - Index.md** — A single entry point: links to every video note and to the NotebookLM artifacts.
- **notebooklm/** folder — Podcast (MP3), mind map (JSON + readable outline), quiz and flashcards (JSON).

The **mind map** is **not** Obsidian’s built-in graph. Obsidian’s graph shows connections between your notes (your `[[links]]`). The NotebookLM mind map is a **topic tree** (big themes and sub-themes from the playlist). You get:
- **mindmap.json** — Raw data (name/children).
- A **readable outline** of that tree in **NotebookLM Artifacts.md** in the same folder, so you can read it like a note.

---

## How to use Obsidian with this

### 1. Open the vault

- If you set `OBSIDIAN_VAULT_PATH` in `.env`, open that folder in Obsidian: **File → Open folder as vault**.
- If you didn’t, notes are in `./data/obsidian_export/YouTube Playlists/`. Open **that** folder as a vault if you want to use Obsidian.

### 2. Start from the index

- Open **00 - Index.md** (or “Index” from the file list).
- Use the links to jump to any video note or to the NotebookLM artifacts.

### 3. Use the video notes

- Each note has a title, summary, key ideas, takeaways, quotes, and `[[wikilinks]]`.
- Click any `[[link]]` to open that note (or create it). That’s how you build your own knowledge graph in Obsidian: as you add notes and link them, the **Graph view** (left sidebar or command palette → “Open graph view”) will show connections between notes.

### 4. Use the NotebookLM artifacts

- **Podcast** — In the index, click **Audio Overview** (or open `notebooklm/podcast.mp3`). Obsidian or your system will play the MP3.
- **Mind map** — Open **NotebookLM Artifacts** in the `notebooklm` folder. The note explains each file and includes the **mind map as a Markdown outline** so you can read it like any other note. The raw tree is in `mindmap.json` if you need it.
- **Quiz / Flashcards** — Stored as JSON. You can:
  - Open them in [NotebookLM](https://notebooklm.google.com) in the same notebook, or
  - Use an Obsidian plugin (e.g. **Obsidian Flashcards**) if it supports your format, or
  - Open the JSON in a text editor and use them manually.

---

## Obsidian “knowledge graph” vs NotebookLM mind map

| | Obsidian graph | NotebookLM mind map |
|---|----------------|----------------------|
| **What it is** | A graph of your **notes** and **[[wikilinks]]**. | A **topic tree** (themes/subthemes) generated from the playlist. |
| **Where** | Graph view in Obsidian (sidebar or command). | In the vault: `notebooklm/NotebookLM Artifacts.md` (outline) and `mindmap.json` (data). |
| **How to grow it** | Create and link more notes; the graph updates automatically. | Fixed for this playlist; re-run NotebookLM to regenerate. |

So: the **knowledge graph** in Obsidian is the one you build by linking notes. The **mind map** from NotebookLM is a separate, readable outline of the playlist’s main topics, living in the `notebooklm` folder.

---

## Quick reference

- **Open vault** → Your `OBSIDIAN_VAULT_PATH` or `data/obsidian_export/YouTube Playlists/`.
- **Entry point** → **00 - Index.md**.
- **Video notes** → Click from index; use `[[links]]` to connect ideas.
- **Podcast** → Click “Audio Overview” in index or open `notebooklm/podcast.mp3`.
- **Mind map** → Read **notebooklm/NotebookLM Artifacts.md** (outline + how to use each file).
- **Quiz / Flashcards** → Use in NotebookLM web or an Obsidian plugin that supports JSON.

After the next `python pipeline.py --only obsidian` run, the new **NotebookLM Artifacts.md** note will appear in your vault’s `notebooklm` folder.
