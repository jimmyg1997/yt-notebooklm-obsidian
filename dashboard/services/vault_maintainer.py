"""One-shot maintenance: meta, covers, topic hierarchy for every discovered vault."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dashboard.services.topic_sync import rebuild_vault_topics, vault_hierarchy_status
from dashboard.services.vault_cover import ensure_vault_cover
from dashboard.services.vault_factory import read_vault_meta, write_vault_meta
from dashboard.services.vault_scanner import discover_vaults, encode_vault_id
from utils.topic_content import load_enriched_for_vault, merge_enriched_sources

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_THEMES = ["υγεία", "διατροφή", "επιστήμη", "ευεξία", "μάθηση"]

BUSINESS_THEMES = ["επιχειρηματικότητα", "οικονομία", "καριέρα", "marketing", "μάθηση"]


def _enriched_filter_for_meta(meta: dict):
    if meta.get("theme_profile") == "business":
        from dashboard.services.vault_purify import is_ol_in_enriched

        return is_ol_in_enriched
    return None

_VAULT_DESCRIPTIONS: dict[str, str] = {
    "metabolomic-medicine": (
        "Βίντεο Metabolomic Medicine® — αυτοάνοσα, μεταβολισμός, διατροφή και υγεία. "
        "Οργανωμένα σε θεματικές και υποθέματα για μελέτη χωρίς να χάνεσαι σε links."
    ),
    "proswpikesshmeiwseismathshs": (
        "Προσωπικές σημειώσεις μάθησης από YouTube — διατροφή, ινσουλίνη, τροφές. "
        "Κάθε υποθέμα έχει σύντομη ανάλυση από τα βίντεο που το αναφέρουν."
    ),
    "myvault - ολ ιν": (
        "Podcast «Ολ Ιν» (Financial Greeks) — επιχειρηματικότητα, οικονομία, καριέρα. "
        "Μόνο βίντεο Ολ Ιν· χωρίς διατροφή/υγεία."
    ),
    "myvault": (
        "Κύριο Obsidian vault — περιέχει playlists. Προτίμησε τα experiment vaults "
        "(`metabolomic-medicine`, `Διατροφή`) για πλήρη ιεραρχία Topics."
    ),
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip()).casefold()


def _ensure_meta(vault_path: Path, display_name: str) -> dict:
    meta = read_vault_meta(vault_path) or {}
    key = _norm(display_name)
    desc = (meta.get("description") or "").strip()
    if not desc:
        desc = _VAULT_DESCRIPTIONS.get(key, "")
    if not desc:
        for k, v in _VAULT_DESCRIPTIONS.items():
            if k in key or key in k:
                desc = v
                break
    if not desc:
        desc = f"Vault «{display_name}» — σημειώσεις και θεματικές από αναλυμένα βίντεο YouTube."

    updated = {
        **meta,
        "name": meta.get("name") or display_name,
        "description": desc,
        "themes": meta.get("themes") if isinstance(meta.get("themes"), list) and meta.get("themes") else DEFAULT_THEMES,
        "updated": datetime.now(tz=timezone.utc).isoformat(),
    }
    write_vault_meta(vault_path, updated)
    return updated


def maintain_vault(vault_path: Path, *, display_name: str = "", skip_llm: bool = True) -> dict:
    """Sync topics, meta, and cover for one vault root."""
    vault_path = vault_path.resolve()
    name = display_name or (read_vault_meta(vault_path) or {}).get("name") or vault_path.name
    if vault_path.name == "vault":
        slug_name = vault_path.parent.name
        if slug_name.startswith(".maintain-"):
            name = display_name or name
        else:
            name = (read_vault_meta(vault_path) or {}).get("name") or slug_name

    before = vault_hierarchy_status(vault_path)
    meta = _ensure_meta(vault_path, name)

    cover = None
    try:
        cover = ensure_vault_cover(vault_path)
    except Exception:
        cover = meta.get("cover_image")

    enriched = load_enriched_for_vault(vault_path, PROJECT_ROOT)
    touched: list[str] = []
    if enriched:
        slug = encode_vault_id(vault_path)[:20].replace("/", "-")
        tmp_data = PROJECT_ROOT / "data" / f".maintain-{slug}"
        enriched_dir = tmp_data / "enriched"
        enriched_dir.mkdir(parents=True, exist_ok=True)
        for old in enriched_dir.glob("*.json"):
            old.unlink()
        merged = merge_enriched_sources(tmp_data, vault_path, PROJECT_ROOT)
        for item in merged:
            vid = str(item.get("video_id") or "x").strip()
            (enriched_dir / f"{vid}.json").write_text(
                json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        prev = os.environ.get("TOPIC_SYNC_SKIP_LLM")
        if skip_llm:
            os.environ["TOPIC_SYNC_SKIP_LLM"] = "1"
        touched = rebuild_vault_topics(
            vault_path,
            tmp_data,
            vault_name=meta.get("name") or name,
            vault_themes=meta.get("themes") or DEFAULT_THEMES,
            theme_profile=meta.get("theme_profile") or "health",
            use_llm=not skip_llm,
            enriched_filter=_enriched_filter_for_meta(meta),
        )
        if prev is None:
            os.environ.pop("TOPIC_SYNC_SKIP_LLM", None)
        else:
            os.environ["TOPIC_SYNC_SKIP_LLM"] = prev

    after = vault_hierarchy_status(vault_path)
    return {
        "vault": str(vault_path),
        "name": meta.get("name") or name,
        "enriched_videos": len(enriched),
        "topics_synced": len(touched),
        "cover": cover,
        "hierarchy_before": before,
        "hierarchy_after": after,
        "description": (meta.get("description") or "")[:160],
    }


def maintain_all_vaults(*, skip_llm: bool = True) -> list[dict]:
    reports: list[dict] = []
    for v in discover_vaults():
        path = Path(v["path"])
        try:
            reports.append(maintain_vault(path, display_name=v["name"], skip_llm=skip_llm))
        except Exception as exc:
            reports.append({"vault": str(path), "name": v["name"], "error": str(exc)})
    return reports
