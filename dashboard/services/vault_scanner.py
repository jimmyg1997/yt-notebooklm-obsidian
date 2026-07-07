"""Discover Obsidian vault roots: data experiments, Vaults/, and .env paths."""
from __future__ import annotations

import base64
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class VaultInfo:
    id: str
    name: str
    path: str
    source_type: str  # experiment | local | obsidian
    note_count: int
    last_modified: str | None
    has_index: bool
    description: str = ""
    description_en: str = ""
    themes: list[str] | None = None
    stats: dict | None = None
    cover_image: str | None = None


def encode_vault_id(path: Path) -> str:
    raw = str(path.resolve()).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_vault_id(vault_id: str) -> Path:
    pad = "=" * (-len(vault_id) % 4)
    return Path(base64.urlsafe_b64decode(vault_id + pad).decode("utf-8"))


def _is_placeholder_vault(path: str) -> bool:
    if not path:
        return True
    lower = path.lower()
    return "yourname" in lower or path == "/Users/yourname/Obsidian/MyVault"


def _vault_stats(root: Path) -> tuple[int, str | None, bool]:
    if not root.is_dir():
        return 0, None, False
    count = 0
    latest: float | None = None
    has_index = False
    for p in root.rglob("*.md"):
        if p.name.startswith("."):
            continue
        count += 1
        if p.name.startswith("00 - Index"):
            has_index = True
        try:
            mtime = p.stat().st_mtime
            if latest is None or mtime > latest:
                latest = mtime
        except OSError:
            continue
    last_modified = None
    if latest is not None:
        last_modified = datetime.fromtimestamp(latest, tz=timezone.utc).isoformat()
    return count, last_modified, has_index


_EPISODE_RE = re.compile(r"^\d{2,3}\s*-\s*.+\.md$", re.IGNORECASE)


def _count_enriched_videos(vault_path: Path) -> int:
    """Count enriched JSON files for this vault (experiment data/ or .dashboard/ingest/)."""
    vault_path = vault_path.resolve()
    candidates: list[Path] = []

    if vault_path.name == "vault" and (PROJECT_ROOT / "data") in vault_path.parents:
        candidates.append(vault_path.parent / "enriched")

    try:
        from dashboard.services.single_video_writer import resolve_data_dir_for_vault

        ingest_enriched = resolve_data_dir_for_vault(vault_path) / "enriched"
        if ingest_enriched not in candidates:
            candidates.append(ingest_enriched)
    except Exception:
        pass

    total = 0
    seen: set[str] = set()
    for enriched in candidates:
        if not enriched.is_dir():
            continue
        for f in enriched.glob("*.json"):
            if f.is_file() and f.name not in seen:
                seen.add(f.name)
                total += 1
    return total


def _count_episode_notes(root: Path) -> int:
    count = 0
    root = root.resolve()
    for p in root.rglob("*.md"):
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] == "Topics":
            continue
        if p.name.startswith("00 -"):
            continue
        if _EPISODE_RE.match(p.name):
            count += 1
            continue
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:1200]
        except OSError:
            continue
        if "video_id:" in head and "source: youtube" in head:
            count += 1
    return count


def _count_topic_notes(root: Path) -> int:
    topics_dir = root / "Topics"
    if not topics_dir.is_dir():
        return 0
    return sum(1 for p in topics_dir.rglob("*.md") if p.is_file())


def vault_analytics(root: Path) -> dict:
    from dashboard.services.topic_sync import vault_hierarchy_status

    topics = _count_topic_notes(root)
    meta_notes = sum(1 for p in root.glob("00 - *.md") if p.is_file())
    videos_analyzed = max(_count_enriched_videos(root), _count_episode_notes(root))
    total_notes, _, _ = _vault_stats(root)
    return {
        "total_notes": total_notes,
        "topics": topics,
        "videos_analyzed": videos_analyzed,
        "meta_notes": meta_notes,
        "hierarchy": vault_hierarchy_status(root),
    }


def _candidate_roots() -> list[tuple[Path, str, str]]:
    """Return (path, display_name, source_type) candidates."""
    out: list[tuple[Path, str, str]] = []
    seen: set[str] = set()

    def add(path: Path, name: str, source: str) -> None:
        try:
            resolved = str(path.resolve())
        except OSError:
            return
        if resolved in seen or not path.is_dir():
            return
        seen.add(resolved)
        out.append((path, name, source))

    data_dir = PROJECT_ROOT / "data"
    if data_dir.is_dir():
        for child in sorted(data_dir.iterdir()):
            vault = child / "vault"
            if vault.is_dir():
                add(vault, child.name, "experiment")

    vaults_dir = PROJECT_ROOT / "Vaults"
    if vaults_dir.is_dir():
        for child in sorted(vaults_dir.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                add(child, child.name, "local")

    env_path = os.environ.get("OBSIDIAN_VAULT_PATH", "").strip()
    if env_path and not _is_placeholder_vault(env_path):
        p = Path(env_path)
        add(p, p.name or "Obsidian Vault", "obsidian")

    return out


def discover_vaults() -> list[dict]:
    from dashboard.services.vault_factory import read_vault_meta

    vaults: list[VaultInfo] = []
    for path, name, source in _candidate_roots():
        note_count, last_modified, has_index = _vault_stats(path)
        meta = read_vault_meta(path)
        display_name = (meta or {}).get("name") or name
        description = (meta or {}).get("description") or ""
        description_en = (meta or {}).get("description_en") or ""
        themes = (meta or {}).get("themes") or []
        stats = vault_analytics(path)
        cover_image = None
        try:
            from dashboard.services.vault_cover import cover_api_path, ensure_vault_cover

            cover_image = cover_api_path(path)
            if not cover_image:
                cover_image = ensure_vault_cover(path)
        except Exception:
            cover_image = (meta or {}).get("cover_image")
        # Include empty vaults created via dashboard (have meta file)
        if note_count == 0 and source != "obsidian" and not meta:
            continue
        vaults.append(
            VaultInfo(
                id=encode_vault_id(path),
                name=display_name,
                path=str(path.resolve()),
                source_type=source,
                note_count=note_count,
                last_modified=last_modified,
                has_index=has_index,
                description=description,
                description_en=description_en,
                themes=themes if isinstance(themes, list) else [],
                stats=stats,
                cover_image=cover_image,
            )
        )
    vaults.sort(key=lambda v: (v.source_type, v.name.lower()))
    return [asdict(v) for v in vaults]
