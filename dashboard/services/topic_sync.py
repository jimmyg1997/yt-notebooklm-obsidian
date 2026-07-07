"""Keep Topics/*.md rich, hierarchical, and in sync with all enriched videos in a vault."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from utils.concept_utils import get_concepts_from_enriched, summary_one_liner
from utils.topic_content import (
    api_delay,
    comentioned_subtopics,
    extract_concept_angle,
    extract_quotes_for_concept,
    extract_summary_for_concept,
    extract_takeaways_for_concept,
    extract_theme_threads,
    generate_subtopic_reference,
    generate_theme_overview,
    load_enriched_dir,
    synthesize_subtopic_overview,
)
from utils.topic_dedup import dedupe_bullets
from utils.topic_hierarchy import (
    assign_hierarchy,
    cluster_display_label,
    cluster_subtopic,
    is_parent_theme,
    theme_display_title,
    validate_parent_map,
    CLUSTER_ORDER,
)

TOPICS_DIR = "Topics"
_LEGACY_MENTION_RE = re.compile(
    r"^## (?:Mentioned in|Εμφανίζεται σε)\s*\n(.*?)(?:\n## |\Z)",
    re.DOTALL | re.IGNORECASE,
)
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:\|([^\]]*))?\]\]")
VAULT_ROLE_HDR = "## Στη βιβλιοθήκη σου"
ABOUT_SUBTOPIC_HDR = "## Σύντομη εικόνα"
FACTS_HDR = "## Τι λένε τα βίντεο"
QUOTES_HDR = "## Σημαντικές παραθέσεις"
MENTIONED_HDR = "## Πηγές (επεισόδια)"
RELATED_HDR = "## Σχετικά (συνεμφανίζονται)"
ABOUT_THEME_HDR = "## Επισκόπηση"
THREADS_HDR = "## Κύριες γραμμές"
START_HDR = "## Καλύτερα σημεία εκκίνησης"
SUBTOPICS_HDR = "## Υποθέματα"
CONNECTED_HDR = "## Συνδεδεμένες θεματικές"


def _safe_topic_filename(theme: str) -> str:
    safe = re.sub(r'[\\/*?:"<>|]', "-", theme.strip())
    safe = re.sub(r"\s+", " ", safe).strip()
    return (safe[:80] or "Topic") + ".md"


def _safe_dirname(theme: str) -> str:
    return _safe_topic_filename(theme).replace(".md", "")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip()).casefold()


def _topic_rel_path(concept: str, parent: str | None, *, cluster: str | None = None) -> str:
    fname = _safe_topic_filename(concept)
    if parent and _norm(parent) != _norm(concept):
        parent_dir = _safe_dirname(parent)
        if cluster and cluster != "έννοιες":
            return f"{TOPICS_DIR}/{parent_dir}/{cluster}/{fname}"
        return f"{TOPICS_DIR}/{parent_dir}/{fname}"
    return f"{TOPICS_DIR}/{fname}"


def _find_episode_stem(vault_dir: Path, video_id: str) -> str | None:
    for p in vault_dir.rglob("*.md"):
        if p.name.startswith("00 -"):
            continue
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:1500]
        except OSError:
            continue
        if f'video_id: "{video_id}"' in head or f"video_id: {video_id}" in head:
            return p.stem
    return None


def _build_mentions(
    vault_dir: Path,
    enriched_items: list[dict],
) -> dict[str, list[tuple[str, str, str, str, str]]]:
    """concept -> [(note_stem, title, one_liner, url, video_id), ...]"""
    out: dict[str, list[tuple[str, str, str, str, str]]] = {}
    for data in enriched_items:
        vid = data.get("video_id", "")
        title = data.get("title", "Unknown")
        url = data.get("url") or f"https://www.youtube.com/watch?v={vid}"
        stem = _find_episode_stem(vault_dir, vid) or title[:60]
        one = summary_one_liner(data)
        concepts = get_concepts_from_enriched(data)
        for c in concepts:
            out.setdefault(c, []).append((stem, title, one, url, vid))
    return out


def _flat_topic_paths(vault_dir: Path) -> list[Path]:
    topics_dir = vault_dir / TOPICS_DIR
    if not topics_dir.is_dir():
        return []
    return [p for p in topics_dir.glob("*.md") if p.is_file()]


def _theme_subfolders(vault_dir: Path) -> list[Path]:
    topics_dir = vault_dir / TOPICS_DIR
    if not topics_dir.is_dir():
        return []
    return [p for p in topics_dir.iterdir() if p.is_dir() and not p.name.startswith(".")]


def vault_hierarchy_status(vault_dir: Path) -> dict:
    flat = len(_flat_topic_paths(vault_dir))
    folders = len(_theme_subfolders(vault_dir))
    return {
        "needs_migration": vault_needs_hierarchy_migration(vault_dir),
        "flat_topics": flat,
        "theme_folders": folders,
    }


def vault_needs_hierarchy_migration(vault_dir: Path) -> bool:
    """True when vault has many flat Topics/*.md but no theme folder hierarchy."""
    flat = len(_flat_topic_paths(vault_dir))
    folders = len(_theme_subfolders(vault_dir))
    if flat < 8:
        return False
    if folders >= 3:
        return False
    # Has theme MOC files at Topics/{theme}.md with role: theme
    for p in _flat_topic_paths(vault_dir):
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:800]
            if "role: theme" in head or "tags:\n  - moc" in head:
                return folders < 3
        except OSError:
            continue
    return True


def _legacy_mentions_from_file(path: Path) -> list[tuple[str, str, str, str, str]]:
    """Parse legacy flat topic note → episode mention tuples."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    m = _LEGACY_MENTION_RE.search(text)
    if not m:
        return []
    block = m.group(1)
    out: list[tuple[str, str, str, str, str]] = []
    for line in block.split("\n"):
        line = line.strip()
        if not line.startswith("-"):
            continue
        wm = _WIKILINK_RE.search(line)
        if not wm:
            continue
        stem = wm.group(1).strip()
        title = (wm.group(2) or stem).strip()
        one = ""
        if "—" in line:
            one = line.split("—", 1)[-1].strip()
        elif " - " in line[len(wm.group(0)) :]:
            one = line.split(" - ", 1)[-1].strip()
        out.append((stem, title, one, "", stem))
    return out


def _merge_legacy_topics(
    vault_dir: Path,
    mentions_map: dict[str, list[tuple[str, str, str, str, str]]],
    all_concepts: list[str],
) -> tuple[dict[str, list], list[str]]:
    """Add concepts/mentions from legacy flat Topics/*.md files."""
    seen = {_norm(c) for c in all_concepts}
    for p in _flat_topic_paths(vault_dir):
        concept = p.stem.strip()
        if not concept:
            continue
        kn = _norm(concept)
        if kn not in seen:
            seen.add(kn)
            all_concepts.append(concept)
        legacy = _legacy_mentions_from_file(p)
        if legacy:
            existing = mentions_map.get(concept, [])
            existing_stems = {x[0] for x in existing}
            for item in legacy:
                if item[0] not in existing_stems:
                    existing.append(item)
            mentions_map[concept] = existing
    return mentions_map, all_concepts


def _legacy_facts_from_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    bullets: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("- ") and len(line) > 20:
            bullets.append(line[2:].strip())
    return bullets[:4]


def _collect_takeaways(concept: str, enriched_items: list[dict], legacy_path: Path | None = None) -> list[str]:
    raw: list[str] = []
    for data in enriched_items:
        raw.extend(extract_takeaways_for_concept(data, concept))
    if legacy_path and legacy_path.is_file():
        raw.extend(_legacy_facts_from_file(legacy_path))
    return dedupe_bullets(raw, max_items=8)


def _collect_summaries(
    concept: str,
    mentions: list[tuple[str, str, str, str, str]],
    enriched_by_vid: dict[str, dict],
) -> list[str]:
    summaries: list[str] = []
    for _stem, _title, _one, _url, vid in mentions:
        data = enriched_by_vid.get(vid)
        if not data:
            continue
        s = extract_summary_for_concept(data, concept)
        if s and s not in summaries:
            summaries.append(s)
    return summaries[:3]


def _collect_quotes(
    concept: str,
    mentions: list[tuple[str, str, str, str, str]],
    enriched_by_vid: dict[str, dict],
) -> list[str]:
    quotes: list[str] = []
    for _stem, _title, _one, _url, vid in mentions:
        data = enriched_by_vid.get(vid)
        if not data:
            continue
        quotes.extend(extract_quotes_for_concept(data, concept, max_items=2))
    return dedupe_bullets(quotes, max_items=3)


def _collect_angles(
    concept: str,
    mentions: list[tuple[str, str, str, str, str]],
    enriched_by_vid: dict[str, dict],
) -> list[str]:
    angles: list[str] = []
    for _stem, _title, _one, _url, vid in mentions:
        data = enriched_by_vid.get(vid)
        if not data:
            continue
        angle = extract_concept_angle(data, concept)
        if angle:
            angles.append(angle)
    return dedupe_bullets(angles, max_items=4)


def _theme_top_episodes(
    theme: str,
    theme_children: list[str],
    mentions_map: dict[str, list],
) -> list[tuple[str, str]]:
    """Video stems that mention the most subtopics in this theme."""
    scores: dict[str, tuple[int, str]] = {}
    child_norms = {_norm(c) for c in theme_children}
    for concept, items in mentions_map.items():
        if _norm(concept) not in child_norms and concept not in theme_children:
            continue
        for stem, title, _one, _url, _vid in items:
            prev = scores.get(stem, (0, title))
            scores[stem] = (prev[0] + 1, title)
    ranked = sorted(scores.items(), key=lambda x: (-x[1][0], x[1][1].casefold()))
    return [(stem, title) for stem, (_count, title) in ranked[:4]]


def _write_subtopic_note(
    vault_dir: Path,
    concept: str,
    *,
    vault_name: str,
    parent: str,
    parent_map: dict[str, str | None],
    mentions_map: dict[str, list],
    mentions: list[tuple[str, str, str, str, str]],
    takeaways: list[str],
    angles: list[str],
    reference_body: str,
    enriched_by_vid: dict[str, dict],
    summaries: list[str] | None = None,
    quotes: list[str] | None = None,
) -> Path:
    """Subtopic under Topics/{parent}/{cluster}/{concept}.md — readable synthesis, links secondary."""
    cluster = cluster_subtopic(concept)
    rel = _topic_rel_path(concept, parent, cluster=cluster)
    path = vault_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)

    parent_display = theme_display_title(parent)
    parent_theme_link = f"Topics/{_safe_dirname(parent)}"
    n_videos = len({m[4] for m in mentions})
    vault_role = (
        f"**{concept}** — {n_videos} επεισόδι{'ο' if n_videos == 1 else 'α'} · θεματική [[{parent_theme_link}|{parent_display}]]."
        if n_videos
        else f"**{concept}** — θεματική [[{parent_theme_link}|{parent_display}]]."
    )

    fact_norms = [_norm(t) for t in takeaways]

    mention_lines = []
    for stem, title, _one, _url, vid in mentions:
        data = enriched_by_vid.get(vid, {})
        angle = extract_concept_angle(data, concept) if data else ""
        if angle:
            an = _norm(angle)
            if any(an in fn or fn in an for fn in fact_norms if len(fn) > 20):
                angle = ""
        line = f"- [[{stem}|{title}]]"
        if angle:
            line += f" — *{angle}*"
        mention_lines.append(line)
    if not mention_lines:
        mention_lines = ["*(Θα εμφανιστεί όταν προστεθούν βίντεο που το αναφέρουν.)*"]

    related = comentioned_subtopics(concept, mentions_map, parent_map, parent, limit=6)
    rel_links: list[str] = []
    for r in related:
        rel_path = _topic_rel_path(r, parent, cluster=cluster_subtopic(r)).replace(".md", "")
        rel_links.append(f"- [[{rel_path}|{r}]]")
    related_lines = "\n".join(rel_links) if rel_links else "*(Δεν υπάρχουν ακόμα συχνά συνεμφανιζόμενα υποθέματα.)*"

    summaries = summaries or []
    quotes = quotes or []

    facts = "\n".join(f"- {t}" for t in takeaways) if takeaways else ""
    quotes_block = "\n".join(f"> {q}" for q in quotes) if quotes else ""

    about = reference_body.strip()
    if not about:
        about = synthesize_subtopic_overview(
            concept,
            takeaways=takeaways,
            summaries=summaries,
            angles=angles,
            parent_theme=parent_display,
        )
    if not about and takeaways:
        about = takeaways[0]
    if not about and summaries:
        about = summaries[0]
    if not about:
        about = f"Δεν βρέθηκαν ακόμα αναλυτικά σημεία για **{concept}** στα επεξεργασμένα βίντεο."

    updated = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    body_parts = [
        f"""---
title: "{concept.replace('"', '\\"')}"
tags:
  - topic
  - subtopic
parent: "{parent.replace('"', '\\"')}"
theme: "{parent.replace('"', '\\"')}"
---

# {concept}

{ABOUT_SUBTOPIC_HDR}

{about}
""",
    ]
    if facts:
        body_parts.append(f"""
{FACTS_HDR}

{facts}
""")
    if quotes_block:
        body_parts.append(f"""
{QUOTES_HDR}

{quotes_block}
""")
    body_parts.append(f"""
{MENTIONED_HDR}

{chr(10).join(mention_lines)}

{RELATED_HDR}

{related_lines}

{VAULT_ROLE_HDR}

{vault_role}

---
*Ενημερώθηκε: {updated} · yt-notebooklm-obsidian*
""")
    body = "\n".join(body_parts)
    path.write_text(body, encoding="utf-8")
    return path


def _grouped_subtopic_lines(theme: str, subtopics: list[str]) -> list[str]:
    clusters: dict[str, list[str]] = {}
    for st in sorted(subtopics, key=lambda x: x.casefold()):
        label = cluster_subtopic(st)
        clusters.setdefault(label, []).append(st)
    lines: list[str] = []
    for key in CLUSTER_ORDER:
        items = clusters.get(key, [])
        if not items:
            continue
        heading = cluster_display_label(key, "el")
        lines.append(f"### {heading}")
        lines.append("")
        for st in items:
            rel = _topic_rel_path(st, theme, cluster=key).replace(".md", "")
            lines.append(f"- [[{rel}|{st}]]")
        lines.append("")
    return lines


def _write_theme_moc(
    vault_dir: Path,
    theme: str,
    subtopics: list[str],
    vault_name: str,
    *,
    video_count: int = 0,
    overview: str = "",
    threads: list[str] | None = None,
    top_episodes: list[tuple[str, str]] | None = None,
    sibling_themes: list[str] | None = None,
) -> None:
    path = vault_dir / TOPICS_DIR / _safe_topic_filename(theme)
    subtopics = sorted(set(subtopics), key=lambda x: x.casefold())
    display = theme_display_title(theme)
    threads = threads or []
    top_episodes = top_episodes or []

    lines = [
        f'---\ntitle: "{display.replace(chr(34), chr(92)+chr(34))}"\ntags:\n  - topic\n  - theme\n  - moc\nrole: theme\ntheme_slug: "{theme.replace(chr(34), chr(92)+chr(34))}"\n---\n',
        f"# {display}",
        "",
        f"> Θεματική: `{theme}` · {len(subtopics)} υποθέματα · {video_count} βίντεο",
        "",
        ABOUT_THEME_HDR,
        "",
        overview.strip() or f"Κόμβος για **{display}** στο vault *{vault_name}*.",
        "",
    ]

    if threads:
        lines.extend([THREADS_HDR, ""])
        lines.extend(f"- {t}" for t in threads)
        lines.append("")

    if top_episodes:
        lines.extend([START_HDR, ""])
        for stem, title in top_episodes:
            lines.append(f"- [[{stem}|{title}]]")
        lines.append("")

    lines.extend([SUBTOPICS_HDR, ""])
    if subtopics:
        lines.extend(_grouped_subtopic_lines(theme, subtopics))
    else:
        lines.append("*(Υποθέματα εμφανίζονται όταν τα βίντεο αναφέρουν έννοιες σε αυτή τη θεματική.)*")
        lines.append("")

    others = [t for t in (sibling_themes or []) if _norm(t) != _norm(theme)]
    if others:
        lines.extend([CONNECTED_HDR, ""])
        for ot in sorted(others, key=lambda x: x.casefold()):
            lines.append(f"- [[Topics/{_safe_dirname(ot)}|{theme_display_title(ot)}]]")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def _rebuild_topic_index(
    vault_dir: Path,
    vault_name: str,
    themes: list[str],
    parent_map: dict[str, str | None],
    all_concepts: list[str],
) -> None:
    index_path = vault_dir / "00 - Topic Index.md"
    lines = [
        "# Topics — hierarchy",
        "",
        f"> **{vault_name}** — parent themes (A→Z) and subtopics. Each note is enriched from your analyzed videos.",
        "",
        "## How to browse",
        "",
        "- Expand **Topics** in the sidebar → pick a theme folder → subtopics sorted A→Z.",
        "- Use **Sync topics** after ingesting new videos to refresh learning notes.",
        "",
    ]
    theme_set = {_norm(t) for t in themes}
    for theme in sorted(themes, key=lambda x: x.casefold()):
        display = theme_display_title(theme)
        lines.append(f"## {display}")
        lines.append("")
        lines.append(f"- [[Topics/{_safe_dirname(theme)}|{display} — επισκόπηση]]")
        children = [
            c for c in all_concepts
            if parent_map.get(c) and _norm(parent_map[c]) == _norm(theme)
        ]
        for child in sorted(children, key=lambda x: x.casefold()):
            rel = _topic_rel_path(child, theme, cluster=cluster_subtopic(child)).replace(".md", "")
            lines.append(f"  - [[{rel}|{child}]]")
        lines.append("")

    orphans = [
        c for c in all_concepts
        if c not in themes and not parent_map.get(c) and _norm(c) not in theme_set
    ]
    if orphans:
        lines.append("## Other topics")
        lines.append("")
        for c in sorted(orphans, key=lambda x: x.casefold()):
            rel = _topic_rel_path(c, None).replace(".md", "")
            lines.append(f"- [[{rel}|{c}]]")
        lines.append("")

    index_path.write_text("\n".join(lines), encoding="utf-8")


def _cleanup_stale_topic_files(vault_dir: Path, keep_paths: set[str]) -> None:
    topics_root = vault_dir / TOPICS_DIR
    if not topics_root.is_dir():
        return
    for p in topics_root.rglob("*.md"):
        rel = p.relative_to(vault_dir).as_posix()
        if rel not in keep_paths and "_moc" not in rel.lower():
            try:
                p.unlink()
            except OSError:
                pass


def _llm_enabled(requested: bool, concept_count: int = 0) -> bool:
    if os.environ.get("TOPIC_SYNC_SKIP_LLM", "").lower() in ("1", "true", "yes"):
        return False
    if concept_count > 60:
        return False
    return requested


def _subtopic_llm_enabled(concept_count: int, has_takeaways: bool) -> bool:
    """Allow per-subtopic synthesis LLM when we have facts to work with."""
    if os.environ.get("TOPIC_SYNC_SKIP_LLM", "").lower() in ("1", "true", "yes"):
        return False
    if not has_takeaways:
        return False
    if concept_count > 250:
        return False
    return True


def rebuild_vault_topics(
    vault_dir: Path,
    data_dir: Path,
    *,
    vault_name: str,
    vault_themes: list[str] | None = None,
    theme_profile: str = "health",
    use_llm: bool = True,
    enriched_filter: Callable[[dict], bool] | None = None,
) -> list[str]:
    """Full topic rebuild from enriched JSON + legacy flat topic notes."""
    vault_dir = vault_dir.resolve()
    themes = [t.strip() for t in (vault_themes or []) if t.strip()]
    from utils.topic_content import merge_enriched_sources

    project_root = Path(__file__).resolve().parent.parent.parent
    enriched_items = merge_enriched_sources(
        data_dir, vault_dir, project_root, item_filter=enriched_filter
    )
    enriched_by_vid = {d.get("video_id", ""): d for d in enriched_items if d.get("video_id")}
    mentions_map = _build_mentions(vault_dir, enriched_items)
    video_count = len(enriched_items)

    all_concepts: list[str] = []
    seen: set[str] = set()
    for c in mentions_map:
        k = _norm(c)
        if k and k not in seen:
            seen.add(k)
            all_concepts.append(c.strip())

    mentions_map, all_concepts = _merge_legacy_topics(vault_dir, mentions_map, all_concepts)

    if not all_concepts:
        return []

    use_llm = _llm_enabled(use_llm, len(all_concepts))
    legacy_paths = {p.stem: p for p in _flat_topic_paths(vault_dir)}

    parent_themes, parent_map = assign_hierarchy(
        all_concepts, themes, use_llm=use_llm and len(all_concepts) <= 80, theme_profile=theme_profile
    )
    parent_map = validate_parent_map(parent_map, parent_themes)

    theme_children: dict[str, list[str]] = {t: [] for t in parent_themes}
    kept_paths: set[str] = set()
    touched: list[str] = []

    for concept in all_concepts:
        if is_parent_theme(concept, parent_themes):
            continue
        parent = parent_map.get(concept)
        if not parent:
            parent = parent_themes[0] if parent_themes else None
        if not parent:
            continue

        mentions = mentions_map.get(concept, [])
        legacy_path = legacy_paths.get(concept)
        takeaways = _collect_takeaways(concept, enriched_items, legacy_path)
        angles = _collect_angles(concept, mentions, enriched_by_vid)
        summaries = _collect_summaries(concept, mentions, enriched_by_vid)
        quotes = _collect_quotes(concept, mentions, enriched_by_vid)

        reference_body = ""
        if _subtopic_llm_enabled(len(all_concepts), bool(takeaways or summaries)):
            mention_triples = [(a, b, c) for a, b, c, _u, _v in mentions]
            reference_body = generate_subtopic_reference(
                concept, parent, mention_triples, takeaways=takeaways, angles=angles
            )
            api_delay()

        path = _write_subtopic_note(
            vault_dir,
            concept,
            vault_name=vault_name,
            parent=parent,
            parent_map=parent_map,
            mentions_map=mentions_map,
            mentions=mentions,
            takeaways=takeaways,
            angles=angles,
            reference_body=reference_body,
            enriched_by_vid=enriched_by_vid,
            summaries=summaries,
            quotes=quotes,
        )
        rel = path.relative_to(vault_dir).as_posix()
        kept_paths.add(rel)
        touched.append(concept)
        theme_children.setdefault(parent, []).append(concept)

    for theme in parent_themes:
        children = theme_children.get(theme, [])
        threads = extract_theme_threads(enriched_items, children)
        top_eps = _theme_top_episodes(theme, children, mentions_map)
        overview = ""
        refined_threads = threads
        if use_llm and children and len(all_concepts) <= 60:
            overview, refined_threads = generate_theme_overview(
                theme,
                theme_display_title(theme),
                children,
                vault_name,
                video_count,
                threads=threads,
                top_episodes=top_eps,
            )
            api_delay()
        elif not overview:
            from utils.topic_hierarchy import theme_tagline

            overview = theme_tagline(theme)

        _write_theme_moc(
            vault_dir,
            theme,
            children,
            vault_name,
            video_count=video_count,
            overview=overview,
            threads=refined_threads,
            top_episodes=top_eps,
            sibling_themes=parent_themes,
        )
        kept_paths.add(f"{TOPICS_DIR}/{_safe_topic_filename(theme)}")

    _rebuild_topic_index(vault_dir, vault_name, parent_themes, parent_map, all_concepts)
    kept_paths.add("00 - Topic Index.md")
    _cleanup_stale_topic_files(vault_dir, kept_paths)
    return touched


def sync_topics_after_ingest(
    vault_dir: Path,
    enriched_path: Path,
    note_stem: str,
    *,
    vault_name: str,
    vault_themes: list[str] | None = None,
) -> list[str]:
    """After one video ingest, rebuild topics from all enriched data in the vault."""
    vault_dir = vault_dir.resolve()
    if vault_dir.name == "vault":
        data_dir = vault_dir.parent
    else:
        data_dir = vault_dir.parent
    return rebuild_vault_topics(
        vault_dir,
        data_dir,
        vault_name=vault_name,
        vault_themes=vault_themes,
        use_llm=True,
    )
