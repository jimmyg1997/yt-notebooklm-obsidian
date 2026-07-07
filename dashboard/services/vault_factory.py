"""Create vaults, metadata, and auto-generated profiles from the first ingested video."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from dashboard.services.vault_scanner import encode_vault_id

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
META_FILE = ".vault-meta.json"
ABOUT_NOTE = "00 - About this vault.md"
INDEX_NOTE = "00 - Index.md"
TOPIC_INDEX_NOTE = "00 - Topic Index.md"
HOWTO_NOTE = "00 - How to use this vault.md"


def sanitize_slug(name: str) -> str:
    s = re.sub(r"[^\w\s-]", "", (name or "").strip())
    s = re.sub(r"[-\s]+", "-", s).strip().lower()
    return (s[:64] or "new-vault").strip("-")


def _unique_slug(base: str) -> str:
    slug = sanitize_slug(base)
    data_root = PROJECT_ROOT / "data"
    candidate = slug
    n = 2
    while (data_root / candidate).exists():
        candidate = f"{slug}-{n}"
        n += 1
    return candidate


def _call_llm_json(prompt: str) -> dict:
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    text = ""
    if openai_key and "your_openai" not in openai_key.lower():
        from openai import OpenAI

        client = OpenAI(api_key=openai_key)
        r = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
        )
        text = (r.choices[0].message.content or "").strip()
    elif gemini_key:
        from google import genai

        client = genai.Client(api_key=gemini_key)
        model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        resp = client.models.generate_content(model=model, contents=prompt)
        text = (getattr(resp, "text", None) or "").strip()
    else:
        raise ValueError("Set OPENAI_API_KEY or GEMINI_API_KEY for auto vault naming")
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text).rstrip("`").strip()
    return json.loads(text)


def generate_vault_profile_from_enriched(enriched: dict) -> dict:
    """LLM: vault display name, slug, description, themes from first video."""
    title = enriched.get("title") or "Untitled"
    uploader = enriched.get("uploader") or enriched.get("channel") or ""
    sections = enriched.get("gemini_sections") or {}
    summary = sections.get("Summary") or ""
    key_ideas = sections.get("Key Ideas") or ""
    related = sections.get("Related Concepts") or ""
    output_lang = (os.environ.get("OUTPUT_LANGUAGE") or "english").strip().lower()
    lang = "Greek" if output_lang == "greek" else "English"

    prompt = f"""Design a personal Obsidian knowledge vault for YouTube learning notes.

First video ingested:
- Title: {title}
- Channel: {uploader}
- Summary: {summary[:1500]}
- Key ideas: {key_ideas[:1200]}
- Related concepts: {related[:800]}

Reply JSON only:
{{
  "name": "Short human-readable vault name (3-6 words)",
  "slug": "url-safe-slug-lowercase",
  "description": "2-3 sentences: what this vault is for and who it helps",
  "themes": ["5-8 topic/theme labels for browsing, no duplicates"]
}}

Write name, description, and themes in {lang}. slug must be ASCII lowercase with hyphens only.
"""
    try:
        data = _call_llm_json(prompt)
    except Exception:
        fallback_slug = _unique_slug(uploader or title[:40] or "youtube-vault")
        return {
            "name": uploader or title[:60] or "New Vault",
            "slug": fallback_slug,
            "description": summary[:400] or f"Knowledge base seeded from: {title}",
            "themes": _themes_from_wikilinks(related) or ["General"],
            "source": "auto",
        }

    slug = sanitize_slug(data.get("slug") or data.get("name") or "vault")
    slug = _unique_slug(slug)
    themes = data.get("themes") or []
    if isinstance(themes, str):
        themes = [t.strip() for t in themes.split(",") if t.strip()]
    themes = [str(t).strip() for t in themes if str(t).strip()][:10]
    if not themes:
        themes = _themes_from_wikilinks(related) or ["General"]

    return {
        "name": str(data.get("name") or slug).strip()[:80],
        "slug": slug,
        "description": str(data.get("description") or "").strip()[:600],
        "themes": themes,
        "source": "auto",
    }


def _themes_from_wikilinks(text: str) -> list[str]:
    links = re.findall(r"\[\[([^\]|]+)", text or "")
    out = []
    seen: set[str] = set()
    for link in links:
        t = link.strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:8]


def read_vault_meta(vault_path: Path) -> dict | None:
    vault_path = vault_path.resolve()
    for candidate in [vault_path / META_FILE, vault_path.parent / META_FILE]:
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
    about = vault_path / ABOUT_NOTE
    if about.is_file():
        text = about.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        name = m.group(1).strip() if m else vault_path.parent.name
        desc_m = re.search(r"## Description\s*\n+(.+?)(?:\n##|\Z)", text, re.DOTALL)
        return {
            "name": name,
            "description": (desc_m.group(1).strip() if desc_m else "")[:600],
            "themes": [],
        }
    return None


def write_vault_meta(data_dir: Path, meta: dict) -> None:
    meta = {**meta, "updated": datetime.now(tz=timezone.utc).isoformat()}
    (data_dir / META_FILE).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_topic_filename(theme: str) -> str:
    safe = re.sub(r'[\\/*?:"<>|]', "-", theme.strip())
    safe = re.sub(r"\s+", " ", safe).strip()
    return (safe[:80] or "Topic") + ".md"


def bootstrap_vault_files(vault_dir: Path, meta: dict) -> None:
    """Create About, Index, Topic Index, How-to, and theme stubs for a new vault."""
    vault_dir.mkdir(parents=True, exist_ok=True)
    name = meta.get("name") or "New Vault"
    description = meta.get("description") or "A personal knowledge vault for YouTube notes."
    themes: list[str] = meta.get("themes") or []
    themes_block = "\n".join(f"- {t}" for t in themes) if themes else "- *(themes will grow as you add videos)*"

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
*Created via Vault Dashboard.*
"""
    (vault_dir / ABOUT_NOTE).write_text(about, encoding="utf-8")

    index = f"""# {name} — Index

> {description[:200]}{"…" if len(description) > 200 else ""}

## Start here

- 📖 [[00 - About this vault|About this vault]] — purpose and themes
- 📂 [[00 - Topic Index|Topics by theme]]
- ❓ [[00 - How to use this vault|How to use this vault]]

## Videos

"""
    (vault_dir / INDEX_NOTE).write_text(index, encoding="utf-8")

    topics_dir = vault_dir / "Topics"
    topics_dir.mkdir(exist_ok=True)
    topic_lines = [
        "# Topics by theme",
        "",
        f"> Browse concepts for **{name}**. Each topic links to related themes and episodes.",
        "",
    ]
    for theme in themes:
        fname = _safe_topic_filename(theme)
        related = [t for t in themes if t != theme]
        related_block = "\n".join(
            f"- [[Topics/{_safe_topic_filename(r).replace('.md', '')}|{r}]]" for r in related[:12]
        )
        if not related_block:
            related_block = "*(Related links appear as you add more themes and videos.)*"
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
        (topics_dir / fname).write_text(stub, encoding="utf-8")
        stem = fname.replace(".md", "")
        topic_lines.append(f"- [[Topics/{stem}|{theme}]]")
    topic_lines.append("")
    (vault_dir / TOPIC_INDEX_NOTE).write_text("\n".join(topic_lines), encoding="utf-8")

    howto = f"""---
title: "How to use this vault"
tags:
  - meta
  - help
---

# How to use this vault

**{name}** — {description}

## Structure

| Note | Purpose |
|------|--------|
| **00 - About** | Vault purpose and themes |
| **00 - Index** | All video notes |
| **00 - Topic Index** | Themes → topic notes |
| **01 - …** | One note per ingested YouTube video |
| **Topics/** | One note per theme (grows with ingest) |

## Tips

- Use the **dashboard** to ingest more single videos into this vault.
- Follow `[[wikilinks]]` in video notes to explore themes.
- Open **Graph view** in Obsidian to see connections.
"""
    (vault_dir / HOWTO_NOTE).write_text(howto, encoding="utf-8")


def create_vault(
    name: str,
    description: str = "",
    themes: list[str] | None = None,
    *,
    source: str = "manual",
    slug: str | None = None,
) -> dict:
    """Create data/{{slug}}/vault/ with bootstrap notes. Returns vault info dict."""
    slug = _unique_slug(slug or name)
    data_dir = PROJECT_ROOT / "data" / slug
    vault_dir = data_dir / "vault"
    if vault_dir.exists() and any(vault_dir.glob("*.md")):
        raise FileExistsError(f"Vault already exists: {slug}")

    meta = {
        "name": name.strip() or slug,
        "slug": slug,
        "description": (description or "").strip(),
        "themes": themes or [],
        "source": source,
        "created": datetime.now(tz=timezone.utc).isoformat(),
    }
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "transcripts").mkdir(exist_ok=True)
    (data_dir / "enriched").mkdir(exist_ok=True)
    write_vault_meta(data_dir, meta)
    bootstrap_vault_files(vault_dir, meta)

    try:
        from dashboard.services.vault_cover import ensure_vault_cover

        ensure_vault_cover(vault_dir)
    except Exception:
        pass

    return {
        "id": encode_vault_id(vault_dir),
        "name": meta["name"],
        "slug": slug,
        "path": str(vault_dir.resolve()),
        "description": meta["description"],
        "themes": meta["themes"],
        "source_type": "experiment",
    }


def create_vault_from_profile(profile: dict) -> dict:
    return create_vault(
        name=profile["name"],
        description=profile.get("description", ""),
        themes=profile.get("themes"),
        source=profile.get("source", "auto"),
        slug=profile.get("slug"),
    )
