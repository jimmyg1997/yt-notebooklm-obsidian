# CURSOR.md — Tooling quick reference

## Start here

1. `AGENTS.md` — roles and paths  
2. `WORKFLOW.md` — planner → implement → review  
3. `README.md` — install and pipeline usage  

## Project lock

`.cursorrules` restricts edits to this repo only.

## Common tasks

| Task | Command / entry |
|------|-----------------|
| Run pipeline | `./run_pipeline.sh` or `python pipeline.py` |
| Run dashboard | `./run_dashboard.sh` → http://127.0.0.1:8787 |
| Tests | `pytest tests/ -q` |
| Sync topics in vault | Dashboard explorer → **Sync topics** |
| NotebookLM login | `notebooklm login` |

## Environment

Copy `.env.example` → `.env`. Never commit `.env`.

Required for enrichment: `OPENAI_API_KEY` or `GEMINI_API_KEY`.  
Optional: `OBSIDIAN_VAULT_PATH`, `DASHBOARD_PORT`, `EXPERIMENT_NAME`.

## Invoke a role

Paste the role block from `AGENTS.md` (Planner, Implementer, Reviewer, Auditor, GitHub Expert) at the top of a Cursor chat, then add your task.

## Troubleshooting

- **Graph empty/slow** — use overview scope; theme/subtopic scopes in graph controls  
- **No vault cover** — re-run ingest or open vault; cover picks first video thumbnail under `YouTube Playlists/`  
- **Wrong theme bullets** — run **Sync topics** after code changes to `topic_content.py`  
