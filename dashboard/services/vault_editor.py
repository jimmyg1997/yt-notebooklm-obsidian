"""Update vault display metadata (name, description, themes) from the dashboard."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from dashboard.services.vault_factory import (
    ABOUT_NOTE,
    INDEX_NOTE,
    META_FILE,
    TOPIC_INDEX_NOTE,
    bootstrap_vault_files,
    read_vault_meta,
    write_vault_meta,
)
from dashboard.services.vault_scanner import decode_vault_id

TOPICS_DIR = "Topics"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _data_dir_for_vault(vault_path: Path) -> Path:
    vault_path = vault_path.resolve()
    if vault_path.name == "vault":
        return vault_path.parent
    return vault_path.parent


def _safe_topic_filename(theme: str) -> str:
    safe = re.sub(r'[\\/*?:"<>|]', "-", theme.strip())
    safe = re.sub(r"\s+", " ", safe).strip()
    return (safe[:80] or "Topic") + ".md"


def update_vault_metadata(
    vault_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    themes: list[str] | None = None,
) -> dict:
    """Patch .vault-meta.json, About note, and topic stubs when themes change."""
    vault_path = decode_vault_id(vault_id).resolve()
    if not vault_path.is_dir():
        raise FileNotFoundError(f"Vault not found: {vault_path}")

    data_dir = _data_dir_for_vault(vault_path)
    meta = read_vault_meta(vault_path) or {}
    if name is not None:
        meta["name"] = name.strip()[:80]
    if description is not None:
        meta["description"] = description.strip()[:600]
    if themes is not None:
        cleaned = [t.strip() for t in themes if t and t.strip()][:12]
        meta["themes"] = cleaned

    write_vault_meta(data_dir, meta)

    _sync_about_note(vault_path, meta)
    _sync_index_title(vault_path, meta)
    if themes is not None:
        _sync_theme_stubs(vault_path, meta)

    try:
        from dashboard.services.vault_cover import ensure_vault_cover

        ensure_vault_cover(vault_path, force=name is not None)
    except Exception:
        pass

    return meta


def _sync_about_note(vault_path: Path, meta: dict) -> None:
    name = meta.get("name") or "Vault"
    description = meta.get("description") or ""
    themes: list[str] = meta.get("themes") or []
    themes_block = "\n".join(f"- {t}" for t in themes) if themes else "- *(add themes in dashboard)*"
    about = f"""---
title: "{name.replace('"', '\\"')}"
tags:
  - meta
  - vault
---

# {name}

## Description

{description}

## Themes & topics

{themes_block}

---
*Updated via Vault Dashboard.*
"""
    (vault_path / ABOUT_NOTE).write_text(about, encoding="utf-8")


def _sync_index_title(vault_path: Path, meta: dict) -> None:
    index_path = vault_path / INDEX_NOTE
    if not index_path.is_file():
        return
    name = meta.get("name") or "Vault"
    description = meta.get("description") or ""
    text = index_path.read_text(encoding="utf-8", errors="replace")
    if text.startswith("# "):
        lines = text.split("\n")
        lines[0] = f"# {name} — Index"
        if len(lines) > 2 and lines[2].startswith(">"):
            lines[2] = f"> {description[:200]}{'…' if len(description) > 200 else ''}"
        index_path.write_text("\n".join(lines), encoding="utf-8")


def _sync_theme_stubs(vault_path: Path, meta: dict) -> None:
    """Ensure each theme has a Topics note; rebuild index links."""
    name = meta.get("name") or "Vault"
    themes: list[str] = meta.get("themes") or []
    topics_dir = vault_path / TOPICS_DIR
    topics_dir.mkdir(exist_ok=True)

    topic_lines = [
        "# Topics by theme",
        "",
        f"> Concepts for **{name}** — each topic links to related themes and episodes.",
        "",
    ]
    for theme in themes:
        fname = _safe_topic_filename(theme)
        path = topics_dir / fname
        related = [t for t in themes if t != theme]
        related_block = "\n".join(
            f"- [[Topics/{_safe_topic_filename(r).replace('.md', '')}|{r}]]" for r in related[:12]
        )
        if not related_block:
            related_block = "*(Related links appear as you add more themes and videos.)*"

        if not path.is_file():
            stub = f"""---
title: "{theme.replace('"', '\\"')}"
tags:
  - topic
  - theme
---

# {theme}

## About this topic

*Theme in **{name}**. Related themes below; episodes appear as you ingest videos.*

## Mentioned in

*(no episodes yet)*

## Related topics

{related_block}

---
*Theme topic — connected to other vault themes.*
"""
            path.write_text(stub, encoding="utf-8")
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
            if "## Related topics" not in text:
                text = text.rstrip() + f"\n\n## Related topics\n\n{related_block}\n"
                path.write_text(text, encoding="utf-8")

        stem = fname.replace(".md", "")
        topic_lines.append(f"- [[Topics/{stem}|{theme}]]")
    topic_lines.append("")
    (vault_path / TOPIC_INDEX_NOTE).write_text("\n".join(topic_lines), encoding="utf-8")


def _managed_delete_root(vault_path: Path) -> Path:
    """Return folder to delete for dashboard-managed vaults only."""
    vault_path = vault_path.resolve()
    data_root = PROJECT_ROOT / "data"
    vaults_root = PROJECT_ROOT / "Vaults"

    if vault_path.name == "vault" and data_root in vault_path.parents:
        data_dir = vault_path.parent
        if data_dir.parent != data_root:
            raise PermissionError("Cannot delete nested data paths")
        return data_dir

    if vaults_root in vault_path.parents and vault_path.parent == vaults_root:
        return vault_path

    raise PermissionError(
        "Only vaults under data/*/vault or Vaults/ can be deleted from the dashboard"
    )


def delete_vault(vault_id: str) -> dict:
    """Remove a dashboard-managed vault folder (irreversible)."""
    vault_path = decode_vault_id(vault_id).resolve()
    if not vault_path.is_dir():
        raise FileNotFoundError(f"Vault not found: {vault_path}")

    target = _managed_delete_root(vault_path)
    name = target.name
    shutil.rmtree(target)
    return {"deleted": True, "path": str(target), "name": name}
