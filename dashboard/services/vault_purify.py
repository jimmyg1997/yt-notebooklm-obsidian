"""Remove non–Ολ Ιν content from the Ολ Ιν vault and rebuild index + topics."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OL_IN_VAULT = PROJECT_ROOT / "Vaults" / "MyVault - Ολ Ιν"

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---", re.S)


def _parse_frontmatter(text: str) -> dict[str, str]:
    m = _FM_RE.match(text)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).split("\n"):
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip().strip('"')
    return out


def is_ol_in_video_note(path: Path) -> bool:
    """True when note belongs to Ολ Ιν / Financial Greeks, not Metabolomic Medicine."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:2500]
    except OSError:
        return False
    fm = _parse_frontmatter(text)
    title = fm.get("title", path.stem)
    uploader = fm.get("uploader", "")
    blob = f"{title} {path.name}".casefold()
    if "metabolomic medicine" in uploader.casefold() or "metabolomic medicine" in blob:
        return False
    if "health project" in blob:
        return False
    if uploader == "Financial Greeks":
        return True
    if "ολ ιν" in blob:
        return True
    return False


def is_ol_in_enriched(data: dict) -> bool:
    playlist = (data.get("playlist_title") or "").casefold()
    uploader = (data.get("uploader") or "").casefold()
    title = (data.get("title") or "").casefold()
    if "ολ ιν" in playlist or playlist == "ολ ιν":
        return True
    if uploader == "financial greeks":
        return True
    if "ολ ιν" in title and "metabolomic" not in title:
        return True
    return False


def _episode_num(path: Path) -> int:
    m = re.match(r"^(\d+)", path.name)
    return int(m.group(1)) if m else 9999


def rebuild_ol_in_index(vault_path: Path, playlist_dir: Path) -> None:
    notes = sorted(
        (p for p in playlist_dir.glob("*.md") if not p.name.startswith("00 -")),
        key=_episode_num,
    )
    lines = [
        "# Ολ Ιν — Index",
        "",
        f"> {len(notes)} videos | Podcast επιχειρηματικότητας & οικονομίας (Financial Greeks)",
        "",
        "## Videos",
        "",
    ]
    for i, p in enumerate(notes, 1):
        fm = _parse_frontmatter(p.read_text(encoding="utf-8", errors="replace")[:1500])
        title = fm.get("title", p.stem)
        stem = p.stem
        lines.append(f"- ✅ [[{stem}|{i}. {title}]]")
    lines.extend(["", "## Topics", "", "- [[00 - Topic Index]]", ""])
    (playlist_dir / "00 - Index.md").write_text("\n".join(lines), encoding="utf-8")


def dedupe_playlist_notes(playlist_dir: Path) -> list[str]:
    """Keep one note per video_id; prefer filename/title containing Ολ Ιν."""
    by_vid: dict[str, Path] = {}
    removed: list[str] = []

    def score(p: Path) -> tuple[int, int]:
        name = p.name.casefold()
        rank = 2 if "ολ ιν" in name else 1 if "financial" in name else 0
        return (rank, -len(p.name))

    for p in sorted(playlist_dir.glob("*.md")):
        if p.name.startswith("00 -"):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")[:2500]
        except OSError:
            continue
        fm = _parse_frontmatter(text)
        vid = fm.get("video_id", "")
        if not vid:
            continue
        prev = by_vid.get(vid)
        if prev is None:
            by_vid[vid] = p
            continue
        if score(p) > score(prev):
            prev.unlink()
            removed.append(prev.name)
            by_vid[vid] = p
        else:
            p.unlink()
            removed.append(p.name)
    return removed


def purify_ol_in_vault(vault_path: Path | None = None) -> dict:
    vault_path = (vault_path or OL_IN_VAULT).resolve()
    playlist = vault_path / "YouTube Playlists"
    removed: list[str] = []

    for p in list(playlist.glob("*.md")):
        if p.name.startswith("00 -"):
            continue
        if not is_ol_in_video_note(p):
            p.unlink()
            removed.append(p.name)

    deduped = dedupe_playlist_notes(playlist)
    removed.extend(deduped)

    topics = vault_path / "Topics"
    if topics.is_dir():
        shutil.rmtree(topics)

    for meta_note in ("00 - Topic Index.md", "00 - How to use this vault.md"):
        p = vault_path / meta_note
        if p.is_file():
            p.unlink()

    rebuild_ol_in_index(vault_path, playlist)

    from dashboard.services.vault_factory import read_vault_meta, write_vault_meta

    meta = read_vault_meta(vault_path) or {}
    meta.update(
        {
            "name": "MyVault - Ολ Ιν",
            "description": (
                "Podcast «Ολ Ιν» (Financial Greeks) — επιχειρηματικότητα, οικονομία, καριέρα, "
                "επενδύσεις. Μόνο βίντεο Ολ Ιν, χωρίς περιεχόμενο διατροφής/υγείας."
            ),
            "theme_profile": "business",
            "themes": [
                "επιχειρηματικότητα",
                "οικονομία",
                "καριέρα",
                "marketing",
                "μάθηση",
            ],
        }
    )
    write_vault_meta(vault_path, meta)

    from dashboard.services.vault_maintainer import maintain_vault

    report = maintain_vault(vault_path, display_name=meta["name"], skip_llm=True)
    return {
        "removed_videos": len(removed),
        "removed_files": removed[:20],
        "maintain": report,
    }
