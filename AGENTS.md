# AGENTS.md — yt-notebooklm-obsidian

Machine-readable agent manual for Cursor and other coding assistants.  
Humans: start with `README.md` and `CURSOR.md`.

## Project lock

Work **only** inside `yt-notebooklm-obsidian/`.  
First chat line: `🟢 yt-notebooklm-obsidian — <topic>`.

## What this repo does

1. **Pipeline** — YouTube playlist/channel → transcripts → enrichment → NotebookLM artifacts → Obsidian Markdown vault
2. **Vault Dashboard** — local web UI at `http://127.0.0.1:8787` to browse vaults, ingest single videos, sync topics, scoped graph view (EL/EN)

## Commands

```bash
pip install -r requirements.txt
playwright install chromium          # NotebookLM login only
./run_pipeline.sh                    # full or partial pipeline
./run_dashboard.sh                   # vault dashboard
pytest tests/ -q                     # automated checks
```

## Development workflow

Multi-agent loop — see **`WORKFLOW.md`**:

| Role | When | Output |
|------|------|--------|
| **Planner** | Non-trivial feature, 3+ files | Plan in chat or `PLAN.md`; wait for approval |
| **Implementer** | After approved plan | Code + tests |
| **Reviewer** | Before “done” | PASS/FAIL checklist, pytest evidence |
| **Auditor** | Vault/content quality | Theme purity, hierarchy, bilingual gaps |
| **GitHub Expert** | Releases, PRs, CI | Branch hygiene, commit messages, `.gitignore` |

Non-trivial = touches dashboard + pipeline, vault structure, or 3+ files.

---

## Cursor roles (paste at chat start)

### Planner

```
You are the Planner for yt-notebooklm-obsidian.
Read WORKFLOW.md, AGENTS.md, README.md dashboard section.
Output: goals, tasks, files touched, risks, verification (pytest + manual dashboard checks).
Do NOT write implementation code. Stop when the plan is ready for human approval.
```

### Implementer

```
You are the Implementer for yt-notebooklm-obsidian.
Plan must be user-approved. Follow AGENTS.md and existing code style.
Run pytest before claiming done. Hand off to Reviewer — do not mark complete yourself.
```

### Reviewer

```
You are the Reviewer for yt-notebooklm-obsidian.
Run pytest tests/. Inspect diff for regressions in graph, i18n, topic sync, pipeline.
Status: PASS (with evidence) or FAIL (numbered fixes). Never say "done" on FAIL.
```

### Auditor

```
You are the Auditor for yt-notebooklm-obsidian vault quality.
Check: theme MOC bullets match episodes only; no cross-theme pollution; cluster folders
Topics/{parent}/{cluster}/{concept}.md; business vaults exclude off-topic health content.
Report findings as a numbered list with vault paths. Do not rewrite notes without approval.
```

### GitHub Expert

```
You are the GitHub Expert for yt-notebooklm-obsidian.
Ensure .gitignore excludes .env, data/, .dashboard/, secrets.
Commit messages: imperative, why-focused. Never commit .env or API keys.
Use gh for PRs when asked. Warn before force-push or large binary adds.
```

---

## Pipeline agents (runtime Python modules)

These run inside `pipeline.py`, not as Cursor roles.

| Module | Role |
|--------|------|
| `agents/transcript_agent.py` | yt-dlp subtitles → `data/transcripts/` |
| `agents/gemini_agent.py` | OpenAI/Gemini enrichment → `data/enriched/` |
| `agents/notebooklm_agent.py` | NotebookLM sources + artifacts |
| `agents/obsidian_agent.py` | Markdown vault, topic index, wikilinks |
| `agents/screenshot_agent.py` | Video frame captures for notes (dashboard ingest) |
| `pipeline.py` | Orchestrator: `--only`, `--resume`, `--update` |

---

## Key paths

| Area | Path |
|------|------|
| Dashboard API | `dashboard/api/routes.py` |
| Graph | `dashboard/services/vault_reader.py`, `dashboard/static/graph.js` |
| i18n | `dashboard/static/i18n.js`, `dashboard/services/note_localizer.py` |
| Topics | `dashboard/services/topic_sync.py`, `utils/topic_hierarchy.py` |
| Local vaults | `Vaults/*/` |
| Tests | `tests/test_*.py` |

## Copy guidelines

- User-facing UI/README: say **enrichment** / **transcript**, not “AI enrichment”.
- Vault note content may mention AI when it is the **subject** of an episode (e.g. “AI in Business”).
