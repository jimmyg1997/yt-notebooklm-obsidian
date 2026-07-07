# WORKFLOW.md — Development gates

## Non-trivial task

Any of:

- 3+ files changed
- Dashboard UI/API behavior
- Vault topic hierarchy or sync logic
- Pipeline agent contract changes

## Sequence

1. **Planner** — scope, files, risks, verification plan → **user approval**
2. **Implementer** — minimal diff, match existing patterns
3. **Reviewer** — `pytest tests/ -q`; manual smoke if UI touched
4. **Auditor** (when vaults change) — spot-check theme MOCs and folder layout
5. **GitHub Expert** (when shipping) — stage, commit message, no secrets

## Verification checklist

```bash
pytest tests/ -q
./run_dashboard.sh   # optional: graph tab, lang switch, vault cover
```

Dashboard smoke:

- Home lists vaults with covers
- Explorer: tree → note → wikilink navigation
- Graph tab loads (`overview` scope default)
- EL/EN toggle reloads tree and note headers

## Completion rule

Do **not** tell the user the task is finished until Reviewer status is **PASS** with test evidence.

Exception: user says “quick fix, skip review” or single-line typo.
