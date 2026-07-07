"""Auto-generate vault cover images (video thumbnail + name caption)."""
from __future__ import annotations

import json
import logging
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from dashboard.services.vault_factory import META_FILE, read_vault_meta, write_vault_meta
from dashboard.services.single_video_writer import resolve_data_dir_for_vault

logger = logging.getLogger(__name__)

COVER_REL = "assets/vault-cover.jpg"
COVER_W, COVER_H = 640, 360


def _latest_video_id(data_dir: Path) -> str | None:
    enriched = data_dir / "enriched"
    if not enriched.is_dir():
        return None
    best: tuple[float, str] | None = None
    for p in enriched.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            vid = str(data.get("video_id") or p.stem).strip()
            if not vid:
                continue
            mtime = p.stat().st_mtime
            if best is None or mtime > best[0]:
                best = (mtime, vid)
        except (OSError, json.JSONDecodeError):
            continue
    return best[1] if best else None


def _video_id_from_notes(vault_path: Path) -> str | None:
    candidates: list[tuple[float, str]] = []
    for p in vault_path.rglob("*.md"):
        if p.name.startswith("00 -") or "Topics" in p.parts:
            continue
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:2000]
        except OSError:
            continue
        m = re.search(r'video_id:\s*"?([A-Za-z0-9_-]{6,})"?', head)
        if m:
            candidates.append((p.stat().st_mtime, m.group(1)))
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return None


def _write_vault_meta_at(vault_path: Path, patch: dict) -> None:
    from dashboard.services.vault_factory import META_FILE, read_vault_meta

    vault_path = vault_path.resolve()
    existing = read_vault_meta(vault_path) or {}
    merged = {**existing, **patch, "updated": datetime.now(tz=timezone.utc).isoformat()}
    (vault_path / META_FILE).write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _download_thumbnail(video_id: str, dest: Path) -> bool:
    url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "yt-notebooklm-obsidian/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        if len(data) < 500:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return True
    except Exception as e:
        logger.warning("Thumbnail download failed for %s: %s", video_id, e)
        return False


def _caption_with_pillow(src: Path, dest: Path, title: str, subtitle: str = "") -> bool:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False

    try:
        img = Image.open(src).convert("RGB")
        img = img.resize((COVER_W, COVER_H), Image.Resampling.LANCZOS)
        overlay_h = 88
        bar = Image.new("RGBA", (COVER_W, overlay_h), (15, 15, 14, 200))
        img.paste(bar, (0, COVER_H - overlay_h), bar)
        draw = ImageDraw.Draw(img)
        title_font = ImageFont.load_default()
        sub_font = ImageFont.load_default()
        title_line = (title or "Vault")[:72]
        draw.text((16, COVER_H - overlay_h + 14), title_line, fill=(250, 250, 248), font=title_font)
        if subtitle:
            draw.text((16, COVER_H - overlay_h + 38), subtitle[:90], fill=(200, 169, 110), font=sub_font)
        img.save(dest, "JPEG", quality=88)
        return True
    except Exception as e:
        logger.warning("Caption overlay failed: %s", e)
        return False


def ensure_vault_cover(vault_path: Path, *, force: bool = False) -> str | None:
    """
    Create or refresh vault cover at assets/vault-cover.jpg.
    Uses latest video thumbnail + vault name caption when Pillow is available.
    Returns relative path inside vault or None.
    """
    vault_path = vault_path.resolve()
    data_dir = resolve_data_dir_for_vault(vault_path)
    meta = read_vault_meta(vault_path) or {}
    cover_path = vault_path / COVER_REL

    video_id = _latest_video_id(data_dir) or _video_id_from_notes(vault_path)
    name = str(meta.get("name") or vault_path.parent.name).strip()
    stats_line = ""
    try:
        from dashboard.services.vault_scanner import vault_analytics

        s = vault_analytics(vault_path)
        parts = []
        if s.get("videos_analyzed"):
            parts.append(f"{s['videos_analyzed']} videos")
        if s.get("topics"):
            parts.append(f"{s['topics']} topics")
        stats_line = " · ".join(parts)
    except Exception:
        pass

    if cover_path.is_file() and not force:
        if meta.get("cover_image") == COVER_REL and meta.get("cover_video_id") == video_id:
            return COVER_REL

    tmp = vault_path / "assets" / "_thumb_tmp.jpg"
    if video_id and _download_thumbnail(video_id, tmp):
        captioned = _caption_with_pillow(tmp, cover_path, name, stats_line)
        if not captioned:
            cover_path.parent.mkdir(parents=True, exist_ok=True)
            cover_path.write_bytes(tmp.read_bytes())
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    else:
        try:
            ph = _solid_placeholder(vault_path)
            if not _caption_with_pillow(ph, cover_path, name, stats_line):
                return meta.get("cover_image")
        except Exception:
            return meta.get("cover_image")

    meta["cover_image"] = COVER_REL
    meta["cover_video_id"] = video_id
    meta["cover_updated"] = datetime.now(tz=timezone.utc).isoformat()
    _write_vault_meta_at(vault_path, meta)
    return COVER_REL


def _solid_placeholder(vault_path: Path) -> Path:
    """Minimal placeholder when no thumbnail — solid color JPEG via Pillow or skip."""
    p = vault_path / "assets" / "_placeholder.jpg"
    try:
        from PIL import Image

        p.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (COVER_W, COVER_H), (232, 228, 220)).save(p, "JPEG")
        return p
    except ImportError:
        raise FileNotFoundError("no thumbnail and Pillow not installed")


def cover_api_path(vault_path: Path) -> str | None:
    meta = read_vault_meta(vault_path) or {}
    rel = meta.get("cover_image")
    if rel and (vault_path / rel).is_file():
        return rel
    if (vault_path / COVER_REL).is_file():
        return COVER_REL
    return None
