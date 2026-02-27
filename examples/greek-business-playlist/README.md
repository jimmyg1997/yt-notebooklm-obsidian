# Example: Greek business playlist (51 videos) 💼🇬🇷

This example documents a real run of the pipeline on a public Greek business podcast playlist.  
As an individual investor who follows Greek finance content, this is also a way to say thank you to **Chris Tsounis** and the broader Greek financial community for the depth and generosity of their material – the resulting Obsidian graph is a snapshot of that knowledge in one place. 🙏

---

## Playlist

- **Title**: Ολ Ιν (business / career podcast)
- **Videos**: 51
- **URL** (example):  
  `https://www.youtube.com/watch?v=383CnQdrGsM&list=PLAQ71P0f2W3nJq8WD_Y9kRHZrHwg5c9tB`

### Visuals

- **Graph screenshot:** `images/graph.png` (Obsidian graph view of the playlist notes).
- **Short demo GIF:** `obsidian-demo.gif` — shows navigating the index, video notes, and graph.

#### Demo (GIF)

![Obsidian demo](obsidian-demo.gif)

In `.env`:

```env
PLAYLIST_URL=https://www.youtube.com/watch?v=383CnQdrGsM&list=PLAQ71P0f2W3nJq8WD_Y9kRHZrHwg5c9tB
OPENAI_API_KEY=sk-...           # your key
OPENAI_MODEL=gpt-4o-mini
OUTPUT_LANGUAGE=english
```

---

## Commands used

```bash
cd yt-notebooklm-obsidian

# 1) Transcripts
python pipeline.py --only transcripts

# 2) Enrichment (OpenAI gpt-4o-mini)
python pipeline.py --only enrichment --resume

# 3) NotebookLM (after `notebooklm login`)
python pipeline.py --only notebooklm

# 4) Obsidian notes
python pipeline.py --only obsidian
```

You can also do this in one shot with:

```bash
./run_pipeline.sh "https://www.youtube.com/watch?v=383CnQdrGsM&list=PLAQ71P0f2W3nJq8WD_Y9kRHZrHwg5c9tB"
```

---

## Results

- **Transcripts**
  - 51 videos in manifest.
  - 50 with usable subtitles → `data/transcripts/*.json`.
  - 1 video without subtitles → marked `status: "failed"` in `manifest.json`.

- **Enrichment (OpenAI, gpt-4o-mini)**
  - ~2.65M characters of transcript.
  - ~687k input tokens + ~41k output tokens.
  - Estimated cost: **≈ $0.13** (see `docs/COST_51_VIDEOS.md`).
  - Output JSON per video in `data/enriched/`.

- **NotebookLM**
  - One notebook created (and then reused on later runs).
  - All 50 `status == "ok"` videos added as sources.
  - Generated and downloaded:
    - `data/notebooklm_outputs/podcast.mp3`
    - `data/notebooklm_outputs/mindmap.json`
    - `data/notebooklm_outputs/quiz.json`
    - `data/notebooklm_outputs/flashcards.json`

- **Obsidian / Markdown**
  - 50 notes + `00 - Index.md` written to:
    - your Obsidian vault under `YouTube Playlists/`, **or**
    - `data/obsidian_export/YouTube Playlists/` if no vault path is set.
  - `YouTube Playlists/notebooklm/` contains:
    - `podcast.mp3`
    - `mindmap.json`
    - `quiz.json`
    - `flashcards.json`
    - `NotebookLM Artifacts.md` (explanation + mind map outline)

---

## How to adapt this example

1. Change `PLAYLIST_URL` in `.env` to your own playlist.
2. Keep `OPENAI_MODEL=gpt-4o-mini` if you want similar cost and behavior.
3. Run:
   ```bash
   ./run_pipeline.sh --resume
   ```
4. Open your vault (or `data/obsidian_export/YouTube Playlists/`) in Obsidian and start from `00 - Index.md`.

This example is only documentation – no transcripts or notes from the original playlist are committed to the repo.

