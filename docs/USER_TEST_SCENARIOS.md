# User test scenarios — Vault Dashboard

Manual checks for a real user session. Run dashboard first: `./run_dashboard_daemon.sh`

## Scenario 1 — Browse & edit vault metadata

| Step | Action | Expected |
|------|--------|----------|
| 1 | Open http://127.0.0.1:8787 | Vault cards load with names, descriptions, theme chips |
| 2 | Click ✎ on a vault card | Edit modal: name, description, comma-separated themes |
| 3 | Change description, add a theme, Save | Card updates; `00 - About this vault.md` reflects changes |
| 4 | Open vault in explorer | Header title matches new name |

## Scenario 2 — Obsidian-style local graph

| Step | Action | Expected |
|------|--------|----------|
| 1 | Open any vault with 2+ notes | Explorer loads tree + note list |
| 2 | Click **Graph** tab | Graph renders (vis-network); stats show note/link counts |
| 3 | Click a node | Switches to Note tab and opens that note |
| 4 | Open a video note with `[[wikilinks]]` | Graph shows edges from video → topics/index |

## Scenario 3 — Topics linked to episodes (not bare labels)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Open vault created via auto-ingest | `Topics/` folder has theme notes |
| 2 | Click **Sync topics** in explorer | Alert lists synced topics |
| 3 | Open a topic (e.g. υγεία) | **Mentioned in** lists the video with one-liner |
| 4 | Scroll to **Related topics** | Links to other themes in the same vault |

## Scenario 4 — Single-video ingest end-to-end

| Step | Action | Expected |
|------|--------|----------|
| 1 | Paste YouTube URL, pick existing vault | Progress bar steps advance |
| 2 | Wait for complete | New numbered note in vault + index line |
| 3 | Open matching topic note | Episode appears under Mentioned in |
| 4 | Graph tab | New edges from video to topics |

## Scenario 5 — Wikilink navigation

| Step | Action | Expected |
|------|--------|----------|
| 1 | Open `00 - Topic Index` | Topic links use `Topics/...` paths |
| 2 | Click a topic wikilink | Note opens (not unresolved) |
| 3 | Open video note, click a concept link | Resolves or marks unresolved if missing |

## Scenario 6 — Cached transcript (repeat ingest)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Ingest same video URL again to new auto vault | Transcript step shows "Reusing cached transcript" quickly |
| 2 | No long hang on Greek subtitles | English-first / cache avoids 429 wait |

## Automated tests

```bash
cd yt-notebooklm-obsidian
.venv/bin/python -m pytest tests/test_dashboard_logical.py -v
```

## API smoke (optional)

```bash
# Replace VAULT_ID from dashboard URL
curl -s http://127.0.0.1:8787/api/vaults | python3 -m json.tool
curl -X PATCH http://127.0.0.1:8787/api/vaults/VAULT_ID \
  -H 'Content-Type: application/json' \
  -d '{"description":"Updated from API test"}'
curl -X POST http://127.0.0.1:8787/api/vaults/VAULT_ID/sync-topics
curl -s "http://127.0.0.1:8787/api/vaults/VAULT_ID/graph" | python3 -m json.tool
```
