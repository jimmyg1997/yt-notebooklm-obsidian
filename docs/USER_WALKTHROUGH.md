# Vault Dashboard — User Walkthrough

Step-by-step guide for using the **local Vault Dashboard** (`http://127.0.0.1:8787`) to browse playlist notes, ingest new videos, and explore topic graphs.

---

## 1. Start the dashboard

From the project folder:

```bash
pip install -r requirements.txt
./run_dashboard.sh
```

Open **http://127.0.0.1:8787** in your browser.

To run in the background (macOS/Linux):

```bash
./run_dashboard_daemon.sh start
./run_dashboard_daemon.sh status
./run_dashboard_daemon.sh restart   # after code updates
```

Optional: set `DASHBOARD_PORT=8787` in `.env` to change the port.

![Dashboard home — vault list and ingest form](screenshots/01-dashboard-home.png)

---

## 2. What you see on the home page

| Area | Purpose |
|------|---------|
| **Add one YouTube video** | Paste a single video URL and add it to an existing vault or create a new one |
| **Your vaults** | Cards for every vault the dashboard finds on disk |
| **Language (Γλώσσα)** | Switch UI between Greek and English |

The dashboard discovers vaults from:

- `data/*/vault/` — output of the batch pipeline (`pipeline.py`)
- `Vaults/*/` — local Obsidian vault roots you keep in the repo
- `OBSIDIAN_VAULT_PATH` in `.env` — your main Obsidian vault (if configured)

Each card shows the vault name, description, note count, and a cover thumbnail when available.

---

## 3. Ingest a single YouTube video

1. Paste a YouTube URL (watch or youtu.be link).
2. Choose a **vault target**:
   - **Existing vault** — pick from the dropdown.
   - **New vault — I'll name it** — enter name and optional description.
   - **New vault — auto from first video** — name, description, and starter themes are suggested after enrichment.
3. Click **Ingest video**.

Requirements:

- `ffmpeg` on your PATH (for optional frame screenshots in notes).
- `OPENAI_API_KEY` or `GEMINI_API_KEY` in `.env` for transcript enrichment.

Progress appears under the form. When finished, the new note appears in the vault and the card list refreshes.

---

## 4. Open a vault (Explorer)

Click a vault card (anywhere except ✎ or Delete).

The **Explorer** has three columns:

| Column | What it does |
|--------|----------------|
| **Folders** | Tree of vault folders — click a folder to filter notes |
| **Notes** | Searchable list of Markdown notes in the current folder |
| **Note / Graph** | Read or edit the selected note, or view the link graph |

![Explorer — reading a note](screenshots/02-explorer-note.png)

### Reading notes

- Click a note in the list to open it.
- **Wikilinks** `[[like this]]` are clickable — unresolved links are highlighted.
- Images in notes load from the vault assets folder.
- **Backlinks** appear at the bottom when other notes link here.

Start with **`00 - Index.md`** or **`00 - Topic Index.md`** when you open a vault for the first time.

### Editing notes

1. Open a note (not protected index files).
2. Click **Edit** → change Markdown in the editor → **Save**.
3. **Delete** removes the note (with confirmation).

### Vault metadata

- **Edit vault** (header) — change name, description, comma-separated themes.
- **Sync topics** — rebuild topic notes under `Topics/` from episode wikilinks (useful after bulk imports).

---

## 5. Graph view

Click the **Graph** tab in the right pane.

![Graph — overview scope](screenshots/03-explorer-graph.png)

### Scope dropdown

| Scope | Best for |
|-------|----------|
| **Overview (fast)** | Whole vault at theme level — good default |
| **Current theme** | Focus on the theme folder you selected in the tree |
| **Current subtopic** | One subtopic note and its neighbours |
| **Full (heavy)** | All notes and links — slow on large vaults |

![Graph — theme scope](screenshots/04-graph-theme-scope.png)

### Graph controls

- **＋ / －** — zoom in and out  
- **Fit** — fit the whole graph in view  
- **Unfreeze layout** — toggle physics so nodes settle or stay draggable  

**Click a node** to jump back to the **Note** tab and open that note.

Tip: select a folder under `Topics/YourTheme/` before switching to **Current theme** or **Current subtopic** scope.

---

## 6. Language (Greek / English)

Use the **Γλώσσα / Language** dropdown in the header (home and explorer).

- UI labels, buttons, and section headers in notes switch between Greek and English.
- Episode body text stays in the language chosen at ingest time (`OUTPUT_LANGUAGE` in `.env`).

---

## 7. Batch pipeline vs dashboard

| Task | Tool |
|------|------|
| Whole playlist or channel (50+ videos) | `python pipeline.py` or `./run_pipeline.sh` |
| One video at a time, quick add | Dashboard ingest form |
| NotebookLM podcast / quiz / flashcards | `python pipeline.py --only notebooklm` |
| Browse, search, graph, light edits | Dashboard explorer |

After a batch run, vaults appear automatically on the dashboard home page under **Your vaults**.

---

## 8. Open the same notes in Obsidian

Notes live as plain Markdown on disk. You do not need the dashboard to use them in Obsidian.

1. In Obsidian: **File → Open folder as vault**.
2. Choose `data/<experiment-name>/vault/` (or your `Vaults/...` folder).
3. See **`docs/OBSIDIAN_USAGE.md`** for index pages, NotebookLM artifacts, and Obsidian’s own graph view.

The dashboard graph and Obsidian’s graph are different: the dashboard graph is scoped and colour-coded by note type (video, theme, subtopic); Obsidian shows all `[[wikilinks]]` in your vault.

---

## 9. Troubleshooting

| Problem | Fix |
|---------|-----|
| Graph tab does nothing | Hard refresh (`Cmd+Shift+R`) or `./run_dashboard_daemon.sh restart` |
| “Graph library failed to load” | Check internet (vis-network loads from CDN) and refresh |
| Empty graph for theme scope | Select a `Topics/...` folder first, then choose **Current theme** |
| Ingest fails | Check `.env` API key, `ffmpeg`, and the dashboard log (`.dashboard/dashboard.log`) |
| Vault missing on home | Confirm folder exists under `data/*/vault/` or `Vaults/` and restart dashboard |

---

## 10. Quick checklist for new users

1. [ ] Copy `.env.example` → `.env` and add API key + optional `PLAYLIST_URL`
2. [ ] Run `./run_dashboard.sh` and open http://127.0.0.1:8787
3. [ ] Ingest one test video with **New vault — auto**
4. [ ] Open the vault → read `00 - Index.md`
5. [ ] Open **Graph** tab → try **Overview** then **Current theme**
6. [ ] Optional: run full playlist with `./run_pipeline.sh`
7. [ ] Optional: open the same folder in Obsidian

For automated checks: `pytest tests/` (includes graph tab browser test when Playwright is installed).
