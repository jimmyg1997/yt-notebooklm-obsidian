"""Write and delete vault notes from the dashboard."""
from __future__ import annotations

from pathlib import Path

from dashboard.services.vault_scanner import decode_vault_id

PROTECTED_PREFIXES = ("00 -",)


def _vault_root(vault_id: str) -> Path:
    root = decode_vault_id(vault_id).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Vault not found: {root}")
    return root


def _safe_note_path(root: Path, rel_path: str) -> Path:
    rel = rel_path.lstrip("/").replace("\\", "/")
    if not rel.endswith(".md"):
        rel += ".md"
    target = (root / rel).resolve()
    if not str(target).startswith(str(root)):
        raise PermissionError("Path escapes vault root")
    return target


def write_note(vault_id: str, rel_path: str, content: str) -> dict:
    root = _vault_root(vault_id)
    path = _safe_note_path(root, rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"path": path.relative_to(root).as_posix(), "saved": True}


def delete_note(vault_id: str, rel_path: str) -> dict:
    root = _vault_root(vault_id)
    path = _safe_note_path(root, rel_path)
    if not path.is_file():
        raise FileNotFoundError(rel_path)
    name = path.name
    if any(name.startswith(p) for p in PROTECTED_PREFIXES):
        raise PermissionError("Cannot delete index/meta notes (00 -*)")
    path.unlink()
    return {"path": rel_path, "deleted": True}
