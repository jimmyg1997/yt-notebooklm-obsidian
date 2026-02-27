# SKILLS.md — Tool Reference for All Agents

## Skill 1 — yt-dlp (Transcript Extraction)

### Install
```bash
pip install yt-dlp
```

### Get all videos from a playlist (metadata only, no download)
```python
import yt_dlp

ydl_opts = {
    'quiet': True,
    'extract_flat': True,
}
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(PLAYLIST_URL, download=False)
    videos = info['entries']
    playlist_title = info['title']
```

### Download Greek subtitles for a single video
```python
ydl_opts = {
    'quiet': True,
    'skip_download': True,
    'writeautomaticsub': True,
    'writesubtitles': True,
    'subtitleslangs': ['el', 'en', 'en-US'],  # Greek first!
    'subtitlesformat': 'vtt',
    'outtmpl': f'/tmp/transcripts/{video_id}',
}
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    ydl.download([video_url])
```

### Clean VTT to plain text
```python
import re

def clean_vtt(vtt_text: str) -> str:
    lines = vtt_text.split('\n')
    seen = set()
    result = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith('WEBVTT') or '-->' in line or line.isdigit():
            continue
        line = re.sub(r'<[^>]+>', '', line)
        line = re.sub(r'&amp;', '&', line)
        line = re.sub(r'&#39;', "'", line)
        if line not in seen:
            seen.add(line)
            result.append(line)
    return ' '.join(result)
```

### Notes on Greek transcripts
- Language code for Greek is `el`
- YouTube auto-generates Greek captions for most Greek-language videos
- If no `el` captions exist, fall back to `en` if available
- VTT cleaning works the same for Greek text

---

## Skill 2 — Gemini API (AI Enrichment)

### Install
```bash
pip install google-generativeai
```

### Basic usage
```python
import google.generativeai as genai

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

response = model.generate_content(prompt)
text = response.text
```

### Best model choices
- `gemini-1.5-flash` — fast, cheap, great for summaries (recommended)
- `gemini-1.5-pro` — more powerful, 1M token context, slower

### Greek transcript handling
Gemini reads Greek natively. Just add to your prompt:
```
The transcript is in Greek. Please respond entirely in English.
```
Or to keep notes in Greek:
```
The transcript is in Greek. Please respond entirely in Greek.
```

### Rate limits (free tier)
- gemini-1.5-flash: 15 requests/minute
- Add `time.sleep(2)` between calls to be safe
- For 50 videos this takes ~2-3 minutes total

### Parsing structured output
Ask Gemini to use consistent headers, then parse with string splitting:
```python
def parse_gemini_response(text: str) -> dict:
    sections = {}
    current = None
    for line in text.split('\n'):
        if line.startswith('## '):
            current = line[3:].strip()
            sections[current] = []
        elif current and line.strip():
            sections[current].append(line.strip())
    return {k: '\n'.join(v) for k, v in sections.items()}
```

---

## Skill 3 — notebooklm-py (NotebookLM Automation)

### Install
```bash
pip install "notebooklm-py[browser]"
playwright install chromium
```

### First-time authentication (one time only!)
```bash
notebooklm login
# Opens browser → log in with your Google account → done
# Saves session cookies locally
```

### Python async API
```python
import asyncio
from notebooklm import NotebookLMClient

async def main():
    async with await NotebookLMClient.from_storage() as client:
        # Create notebook
        nb = await client.notebooks.create("My Playlist Notes")
        notebook_id = nb.id
        
        # Add YouTube URL as source
        await client.sources.add_url(notebook_id, video_url, wait=True)
        
        # Generate audio overview
        status = await client.artifacts.generate_audio(
            notebook_id, 
            instructions="Create an engaging overview in Greek"
        )
        await client.artifacts.wait_for_completion(notebook_id, status.task_id)
        await client.artifacts.download_audio(notebook_id, "podcast.mp3")
        
        # Generate mind map
        await client.artifacts.generate_mind_map(notebook_id)
        
        # Generate quiz
        status = await client.artifacts.generate_quiz(notebook_id, difficulty="hard")
        await client.artifacts.wait_for_completion(notebook_id, status.task_id)
        await client.artifacts.download_quiz(notebook_id, "quiz.json", output_format="json")
        
        # Generate flashcards
        await client.artifacts.generate_flashcards(notebook_id, quantity="more")
        await client.artifacts.download_flashcards(notebook_id, "flashcards.json", output_format="json")

asyncio.run(main())
```

### Adding 50 YouTube URLs (batch with retry)
```python
import asyncio

async def add_sources_batch(client, notebook_id, video_urls, delay=3):
    failed = []
    for i, url in enumerate(video_urls, 1):
        try:
            print(f"  Adding source {i}/{len(video_urls)}: {url}")
            await client.sources.add_url(notebook_id, url, wait=True)
            await asyncio.sleep(delay)  # be gentle with the API
        except Exception as e:
            print(f"  ❌ Failed to add {url}: {e}")
            failed.append(url)
    return failed
```

### IMPORTANT: notebooklm-py limitations
- Uses undocumented Google APIs — may break if Google changes internals
- Requires a valid Google account with NotebookLM access
- Browser authentication stores session in `~/.notebooklm/`
- Not for production use — personal/research projects only
- Check GitHub for latest version: `pip install --upgrade notebooklm-py`

---

## Skill 4 — Obsidian Markdown Format

### YAML Frontmatter (required for Dataview plugin)
```yaml
---
title: "Video Title Here"
source: youtube
playlist: "Playlist Name"
url: "https://youtube.com/watch?v=..."
video_id: "abc123"
uploader: "Channel Name"
upload_date: 2024-01-15
duration: "12:34"
language: greek
processed: 2025-02-26
notebooklm_notebook: "notebook_id_here"
tags:
  - youtube
  - greek
  - inbox
status: processed
---
```

### Wikilinks for graph view connections
```markdown
## Related Concepts
- [[Concept One]]
- [[Concept Two]]  
- [[Playlist Index]]
```

### MOC (Map of Content) note structure
```markdown
# Playlist Name — Index

> [[00 - Index]] | 50 videos | NotebookLM: [link]

## Videos
- ✅ [[01 - Video Title|1. Video Title]]
- ✅ [[02 - Video Title|2. Video Title]]
- ❌ [[03 - Video Title|3. Video Title]] — no transcript

## NotebookLM Artifacts
- 🎧 [Audio Overview](./notebooklm/podcast.mp3)
- 🧠 [Mind Map](./notebooklm/mindmap.json)
- 📝 [Quiz](./notebooklm/quiz.json)
- 🃏 [Flashcards](./notebooklm/flashcards.json)
```

### Safe filename generation
```python
import re

def safe_filename(index: int, title: str, max_len: int = 80) -> str:
    safe = re.sub(r'[\\/*?:"<>|]', '', title)
    safe = re.sub(r'\s+', ' ', safe).strip()
    return f"{index:02d} - {safe[:max_len]}.md"
```

---

## Skill 5 — Rich Terminal UI

### Install
```bash
pip install rich
```

### Progress bar for 50 videos
```python
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

console = Console()

with Progress(
    SpinnerColumn(),
    TextColumn("[progress.description]{task.description}"),
    BarColumn(),
    TextColumn("{task.completed}/{task.total}"),
) as progress:
    task = progress.add_task("Processing videos...", total=50)
    for video in videos:
        # do work
        progress.advance(task)
```
