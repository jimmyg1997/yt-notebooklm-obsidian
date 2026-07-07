"""Generate rich topic note content from enriched video JSON (shared by pipeline + dashboard)."""
from __future__ import annotations

import json
import logging
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable

from utils.topic_dedup import dedupe_bullets, text_not_in_bullets

logger = logging.getLogger(__name__)

KEY_IDEAS_KEYS = ("Key Ideas", "Κύριες Ιδέες", "Κύριες ιδέες")
SUMMARY_KEYS = ("Summary", "Περίληψη")
RELATED_KEYS = (
    "Related Concepts",
    "Σχετικές Έννοιες",
    "Σχετικές έννοιες",
    "Σχετικοί Όροι",
    "Σχετικοί όροι",
)
TAKEAWAY_KEYS = (
    "Takeaways",
    "Takeaways & Action Items",
    "Συμβουλές & Ενέργειες",
    "Tips & Actions",
)
ACTION_KEYS = ("Σημαντικά Τεχνάσματα", "Tips & Actions", "Takeaways", "Συμβουλές & Ενέργειες")
QUOTE_KEYS = ("Σημαντικές Παραθέσεις", "Notable Quotes", "Quotes")
_CONCEPT_STOP = frozenset(
    {"και", "του", "της", "των", "στο", "στη", "στα", "με", "για", "από", "the", "and", "for", "with"}
)
# Too broad alone — must co-occur with a specific token or match in idea title
_GENERIC_TOPIC_TOKENS = frozenset(
    {
        "υγεια",
        "υγειας",
        "health",
        "διατροφη",
        "διατροφής",
        "ευεξια",
        "wellness",
        "μαθηση",
        "learning",
        "επιστημη",
        "science",
        "τροπος",
        "ζωης",
        "lifestyle",
        "συνηθειες",
        "habits",
    }
)

DEFAULT_CATEGORIES = [
    "Health & Wellness",
    "Nutrition & Diet",
    "Fitness & Exercise",
    "Personal Development",
    "Science & Learning",
    "Mindset & Psychology",
    "Career & Skills",
    "Other",
]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s.strip()).casefold()


def _section(data: dict, *keys: str) -> str:
    sections = data.get("gemini_sections") or {}
    for k in keys:
        if sections.get(k):
            return str(sections[k]).strip()
    return ""


def _concept_tokens(concept: str) -> set[str]:
    return {
        w
        for w in re.findall(r"[\w\u0370-\u03ff]{4,}", _norm(concept), flags=re.UNICODE)
        if w not in _CONCEPT_STOP
    }


def _specific_tokens(concept: str) -> set[str]:
    all_t = _concept_tokens(concept)
    specific = {t for t in all_t if t not in _GENERIC_TOPIC_TOKENS}
    return specific if specific else all_t


def _token_in_text(token: str, text: str) -> bool:
    if not token:
        return False
    if token in text:
        return True
    stem = token[: max(4, min(len(token), 6))]
    return len(stem) >= 4 and stem in text


def _line_matches_concept(line: str, concept: str) -> bool:
    """Strict: line must discuss this concept, not merely share a tagged video."""
    cnorm = _norm(concept)
    ln = _norm(line)
    if cnorm in ln:
        return True
    title_part = ln.split(":", 1)[0].strip()
    if cnorm in title_part:
        return True
    specific = _specific_tokens(concept)
    if any(_token_in_text(t, title_part) for t in specific):
        return True
    if sum(1 for t in specific if _token_in_text(t, ln)) >= 1:
        return True
    all_tokens = _concept_tokens(concept)
    if len(all_tokens) >= 2:
        hits = sum(1 for t in all_tokens if _token_in_text(t, ln))
        return hits >= 2
    return False


def video_mentions_concept(data: dict, concept: str) -> bool:
    """True when this enriched video explicitly tags the concept."""
    from utils.concept_utils import get_concepts_from_enriched

    cnorm = _norm(concept)
    for c in get_concepts_from_enriched(data):
        if _norm(c) == cnorm:
            return True
    related = _section(data, *RELATED_KEYS)
    if cnorm in _norm(related) or f"[[{concept}]]" in related:
        return True
    notes = data.get("gemini_notes") or ""
    return f"[[{concept}]]" in notes or cnorm in _norm(notes)


def concept_in_enriched(data: dict, concept: str) -> bool:
    return video_mentions_concept(data, concept)


def _parse_bullet_lines(block: str) -> list[str]:
    out: list[str] = []
    for raw in block.split("\n"):
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^[\d]+\.\s*", "", line)
        line = re.sub(r"^[-*]\s*", "", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"\*+", "", line).strip()
        if len(line) >= 15:
            out.append(line)
    return out


def extract_takeaways_for_concept(data: dict, concept: str, max_items: int = 8) -> list[str]:
    """Only bullets that explicitly discuss this concept — never whole unrelated videos."""
    if not video_mentions_concept(data, concept):
        return []
    out: list[str] = []
    for key in KEY_IDEAS_KEYS + TAKEAWAY_KEYS + ACTION_KEYS:
        block = _section(data, key)
        if not block:
            continue
        for line in _parse_bullet_lines(block):
            if _line_matches_concept(line, concept) and line not in out:
                out.append(line)
            if len(out) >= max_items:
                return out
    return out[:max_items]


def extract_summary_for_concept(data: dict, concept: str, max_len: int = 420) -> str:
    if not video_mentions_concept(data, concept):
        return ""
    summary = _section(data, *SUMMARY_KEYS)
    if not summary:
        return ""
    specific = _specific_tokens(concept)
    for sent in re.split(r"(?<=[.!?;])\s+", summary):
        sn = _norm(sent)
        if not any(_token_in_text(t, sn) for t in specific):
            continue
        if not _line_matches_concept(sent, concept):
            continue
        s = sent.strip()
        return (s[: max_len - 1] + "…") if len(s) > max_len else s
    return ""


def extract_quotes_for_concept(data: dict, concept: str, max_items: int = 2) -> list[str]:
    if not video_mentions_concept(data, concept):
        return []
    block = _section(data, *QUOTE_KEYS)
    if not block:
        return []
    out: list[str] = []
    for line in _parse_bullet_lines(block):
        q = re.sub(r'^["\'""]|["\'""]$', "", line.strip())
        if len(q) >= 20 and _line_matches_concept(q, concept):
            out.append(q)
        if len(out) >= max_items:
            break
    return out


def synthesize_subtopic_overview(
    concept: str,
    *,
    takeaways: list[str],
    summaries: list[str],
    angles: list[str],
    parent_theme: str = "",
) -> str:
    """Offline readable paragraph from matched content only."""
    matched_angles = [a for a in angles if _line_matches_concept(a, concept)]
    if takeaways:
        if len(takeaways) == 1:
            return takeaways[0]
        return f"{takeaways[0]} {takeaways[1]}".strip()
    if matched_angles:
        return matched_angles[0]
    if summaries:
        return summaries[0]
    if parent_theme:
        return (
            f"Το **{concept}** εμφανίζεται ως σχετική έννοια σε επεισόδια της θεματικής **{parent_theme}**, "
            f"χωρίς εκτενή ανάλυση — δες τις πηγές παρακάτω."
        )
    return ""


def _output_language() -> str:
    lang = (os.environ.get("OUTPUT_LANGUAGE") or "english").strip().lower()
    return "greek" if lang.startswith("el") or "greek" in lang else "english"


def _llm_text(prompt: str) -> str:
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    try:
        if openai_key and "your_openai" not in openai_key.lower():
            from openai import OpenAI

            client = OpenAI(api_key=openai_key)
            r = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
            )
            return (r.choices[0].message.content or "").strip()
        if gemini_key:
            import google.generativeai as genai

            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            resp = model.generate_content(prompt)
            return (getattr(resp, "text", None) or "").strip()
    except Exception as e:
        logger.warning("LLM text failed: %s", e)
    return ""


def extract_concept_angle(data: dict, concept: str, max_len: int = 220) -> str:
    """One specific sentence about this concept from a video (not the whole summary)."""
    if not video_mentions_concept(data, concept):
        return ""
    for key in KEY_IDEAS_KEYS + TAKEAWAY_KEYS + ACTION_KEYS:
        block = _section(data, key)
        if not block:
            continue
        for line in _parse_bullet_lines(block):
            if _line_matches_concept(line, concept) and len(line) >= 20:
                return (line[: max_len - 1] + "…") if len(line) > max_len else line
    summary = extract_summary_for_concept(data, concept, max_len=max_len)
    return summary


def extract_theme_threads(enriched_items: list[dict], theme_concepts: list[str], max_items: int = 5) -> list[str]:
    """Cross-video insights for a theme — only bullets tied to theme subtopics."""
    raw: list[str] = []
    for concept in theme_concepts[:50]:
        for data in enriched_items:
            if not video_mentions_concept(data, concept):
                continue
            for takeaway in extract_takeaways_for_concept(data, concept, max_items=2):
                if len(takeaway) >= 25:
                    raw.append(takeaway)
    return dedupe_bullets(raw, max_items=max_items)


def generate_subtopic_reference(
    concept: str,
    parent_theme: str,
    mentions: list[tuple[str, str, str]],
    *,
    takeaways: list[str] | None = None,
    angles: list[str] | None = None,
) -> str:
    takeaways = dedupe_bullets(takeaways or [], max_items=6)
    angles = dedupe_bullets(angles or [], max_items=4)
    lang = _output_language()
    lang_instruction = "Write in Greek." if lang == "greek" else "Write in English."
    facts = "\n".join(f"- {t}" for t in takeaways) or "(none)"
    angles_txt = "\n".join(f"- {a}" for a in angles) or "(none)"
    videos = "\n".join(f"- {title}" for _, title, _ in mentions[:6] if title)

    prompt = f"""Write ONE readable paragraph (3-5 sentences) for a subtopic note the user opens to LEARN about "{concept}".

Parent theme: "{parent_theme}"

Rules:
- Self-contained: the user should understand the topic WITHOUT clicking links.
- Synthesize the facts below into clear prose; you MAY reuse key phrases from facts.
- NO "δες παρακάτω", NO "άνοιξε τα βίντεο", NO "you will learn".
- Stay faithful to the facts; do not invent medical claims beyond what is given.
- Greek medical/education tone if {lang_instruction}

Facts from analyzed videos:
{facts}

Per-video angles:
{angles_txt}

Videos: {videos}

{lang_instruction} Plain markdown, no headings."""

    text = _llm_text(prompt)
    if text:
        return text_not_in_bullets(text, takeaways)
    if lang == "greek":
        n = len(mentions)
        base = f"Το **{concept}** συγκεντρώνει πληροφορίες από {n} επεισόδι{'ο' if n == 1 else 'α'} υπό τη θεματική **{parent_theme}**."
        if takeaways:
            return base
        return base + " Άνοιξε τα βίντεο παρακάτω για λεπτομέρειες."
    return f"**{concept}** across your videos under **{parent_theme}**."


def generate_theme_overview(
    theme: str,
    display_title: str,
    subtopics: list[str],
    vault_name: str,
    video_count: int,
    *,
    threads: list[str] | None = None,
    top_episodes: list[tuple[str, str]] | None = None,
) -> tuple[str, list[str]]:
    """Returns (overview paragraph, key threads list — possibly LLM-refined)."""
    threads = dedupe_bullets(threads or [], max_items=5)
    lang = _output_language()
    lang_instruction = "Write in Greek." if lang == "greek" else "Write in English."
    subs = ", ".join(subtopics[:10])
    thread_txt = "\n".join(f"- {t}" for t in threads[:5]) or "(none yet)"
    eps = "\n".join(f"- {t}" for _, t in top_episodes[:4]) or "(none)"

    prompt = f"""Write content for a theme hub note in a personal learning vault.

Theme slug: {theme}
Display title: {display_title}
Vault: {vault_name}
Subtopics ({len(subtopics)}): {subs}
Videos analyzed: {video_count}

Existing thread bullets from videos (dedupe/refine into 3-5 sharper bullets):
{thread_txt}

Top episodes:
{eps}

Output exactly two markdown sections:

## Overview
2-3 sentences: what this theme collects, how subtopics connect, when to open it. NOT a lesson.

## Key threads
3-5 bullet points (- prefix): cross-cutting insights from the videos only. No duplicates. No generic wellness advice.

{lang_instruction}"""

    text = _llm_text(prompt)
    if text and "## Overview" in text:
        parts = text.split("## Key threads", 1)
        overview = parts[0].replace("## Overview", "").strip()
        thread_block = parts[1].strip() if len(parts) > 1 else ""
        refined = [
            re.sub(r"^[-*]\s*", "", ln).strip()
            for ln in thread_block.split("\n")
            if ln.strip().startswith(("-", "*"))
        ]
        return overview, dedupe_bullets(refined or threads, max_items=5)

    from utils.topic_hierarchy import theme_tagline

    tagline = theme_tagline(theme)
    overview = tagline or (
        f"**{display_title}** — {len(subtopics)} υποθέματα από {video_count} βίντεο στο *{vault_name}*."
        if lang == "greek"
        else f"**{display_title}** — {len(subtopics)} subtopics from {video_count} videos."
    )
    return overview, threads


def comentioned_subtopics(
    concept: str,
    mentions_map: dict[str, list],
    parent_map: dict[str, str | None],
    parent: str,
    *,
    limit: int = 6,
) -> list[str]:
    """Subtopics that share videos with this concept (most co-occurrences first)."""
    my_vids: set[str] = set()
    for item in mentions_map.get(concept, []):
        vid = item[4] if len(item) > 4 else item[0]
        my_vids.add(str(vid))
    if not my_vids:
        return []

    scores: dict[str, int] = {}
    for other, items in mentions_map.items():
        if _norm(other) == _norm(concept):
            continue
        if parent_map.get(other) != parent:
            continue
        shared = sum(1 for it in items if str(it[4] if len(it) > 4 else it[0]) in my_vids)
        if shared:
            scores[other] = shared
    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0].casefold()))
    return [name for name, _ in ranked[:limit]]


def get_concepts_from_enriched(data: dict) -> list[str]:
    from utils.concept_utils import get_concepts_from_enriched as _g

    return _g(data)


def generate_topic_about(
    concept: str,
    mentions: list[tuple[str, str, str]],
    *,
    takeaways: list[str] | None = None,
) -> str:
    """2–4 paragraphs explaining the concept (LLM) or fallback from takeaways."""
    takeaways = takeaways or []
    lang = _output_language()
    lang_instruction = "Write in Greek." if lang == "greek" else "Write in English."

    if mentions:
        context_lines = [f"- {title}: {one_liner}" for (_, title, one_liner) in mentions[:12] if title]
        context = "\n".join(context_lines)
    else:
        context = "\n".join(f"- {t}" for t in takeaways[:8])

    if not context.strip():
        return ""

    prompt = f"""Write educational content for a personal learning vault topic note about: "{concept}".

Context from analyzed YouTube videos:
{context}

Write:
1) Two to three short paragraphs explaining what "{concept}" means and why it matters for learning (neutral, clear, practical).
2) Then a markdown subsection exactly titled "## Key takeaways" with 3-6 bullet points the reader should remember (use - bullets).

{lang_instruction}
Do not list video titles in the paragraphs. Output markdown only."""

    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    try:
        if openai_key and "your_openai" not in openai_key.lower():
            from openai import OpenAI

            client = OpenAI(api_key=openai_key)
            r = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
            )
            text = (r.choices[0].message.content or "").strip()
        elif gemini_key:
            import google.generativeai as genai

            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            resp = model.generate_content(prompt)
            text = (getattr(resp, "text", None) or "").strip()
        else:
            return _fallback_about(concept, takeaways, lang)
        return text if text else _fallback_about(concept, takeaways, lang)
    except Exception as e:
        logger.warning("Topic about generation failed for %s: %s", concept[:40], e)
        return _fallback_about(concept, takeaways, lang)


def _fallback_about(concept: str, takeaways: list[str], lang: str) -> str:
    intro = (
        f"**{concept}** — σύνοψη από τα βίντεο που έχεις αναλύσει σε αυτό το vault."
        if lang == "greek"
        else f"**{concept}** — a learning note synthesized from videos analyzed in this vault."
    )
    if not takeaways:
        return intro
    bullets = "\n".join(f"- {t}" for t in takeaways[:6])
    return f"{intro}\n\n## Key takeaways\n\n{bullets}"


def assign_parent_themes(
    concepts: list[str],
    vault_themes: list[str],
) -> dict[str, str | None]:
    """
    Map each concept to a parent vault theme (subtopic) or None if it is a top-level theme.
    Uses LLM when keys available; else keyword overlap with theme names.
    """
    themes = [t.strip() for t in vault_themes if t.strip()]
    out: dict[str, str | None] = {}
    for c in concepts:
        if any(_norm(c) == _norm(t) for t in themes):
            out[c] = None
            continue
        parent = _keyword_parent(c, themes)
        out[c] = parent
    return out


def _keyword_parent(concept: str, themes: list[str]) -> str | None:
    if not themes:
        return None
    c = _norm(concept)
    for t in themes:
        if _norm(t) in c or c in _norm(t):
            return t
    return themes[0] if themes else None


def assign_parent_themes_llm(concepts: list[str], vault_themes: list[str]) -> dict[str, str | None]:
    """LLM batch assign subtopics to one of the vault themes."""
    themes = [t.strip() for t in vault_themes if t.strip()]
    if not themes:
        return {c: None for c in concepts}

    need = [c for c in concepts if not any(_norm(c) == _norm(t) for t in themes)]
    if not need:
        return {c: None if any(_norm(c) == _norm(t) for t in themes) else themes[0] for c in concepts}

    prompt = f"""Parent themes ONLY (assign every concept to one of these — never create new parents):
{", ".join(themes)}

Rules:
- Reply with the parent theme for EACH concept below.
- Use "SELF" ONLY if the concept is exactly one of the parent theme names above.
- Every food, nutrient, product, or mechanism → assign to the best parent (usually διατροφή or υγεία).
- Never use SELF for specific items like foods, vitamins, exercises.

Concepts:
{chr(10).join("- " + c for c in need)}

Reply JSON only: {{"Concept Name": "ParentTheme", ...}}"""

    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    mapping: dict[str, str] = {}
    try:
        if openai_key and "your_openai" not in openai_key.lower():
            from openai import OpenAI

            client = OpenAI(api_key=openai_key)
            r = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
            )
            text = (r.choices[0].message.content or "").strip()
        elif gemini_key:
            import google.generativeai as genai

            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            resp = model.generate_content(prompt)
            text = (getattr(resp, "text", None) or "").strip()
        else:
            return assign_parent_themes(concepts, themes)
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text).rstrip("`").strip()
        mapping = json.loads(text)
    except Exception as e:
        logger.warning("Parent theme assignment failed: %s", e)
        return assign_parent_themes(concepts, themes)

    out: dict[str, str | None] = {}
    theme_norm = {_norm(t): t for t in themes}
    for c in concepts:
        if any(_norm(c) == _norm(t) for t in themes):
            out[c] = None
            continue
        raw = mapping.get(c, "")
        if isinstance(raw, str) and raw.upper() == "SELF":
            out[c] = None
        elif isinstance(raw, str) and _norm(raw) in theme_norm:
            out[c] = theme_norm[_norm(raw)]
        else:
            from utils.topic_hierarchy import keyword_assign_parent

            out[c] = keyword_assign_parent(c, themes)
    return out


def api_delay() -> None:
    try:
        delay = float(os.environ.get("API_DELAY_SECONDS", "1.5"))
        if delay > 0:
            time.sleep(delay)
    except (TypeError, ValueError):
        time.sleep(1)


def load_enriched_dir(data_dir: Path) -> list[dict]:
    enriched = data_dir / "enriched"
    if not enriched.is_dir():
        return []
    out = []
    for p in sorted(enriched.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


_VIDEO_ID_RE = re.compile(r'video_id:\s*["\']?([A-Za-z0-9_-]{6,})["\']?')


def collect_vault_video_ids(vault_dir: Path) -> set[str]:
    """Video IDs referenced in vault markdown frontmatter."""
    ids: set[str] = set()
    vault_dir = vault_dir.resolve()
    if not vault_dir.is_dir():
        return ids
    for p in vault_dir.rglob("*.md"):
        if p.name.startswith("."):
            continue
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:2500]
        except OSError:
            continue
        m = _VIDEO_ID_RE.search(head)
        if m:
            ids.add(m.group(1))
    return ids


def _enriched_search_roots(project_root: Path) -> list[Path]:
    roots: list[Path] = []
    data_dir = project_root / "data"
    if data_dir.is_dir():
        flat = data_dir / "enriched"
        if flat.is_dir() and any(flat.glob("*.json")):
            roots.append(flat)
        for child in sorted(data_dir.iterdir()):
            if child.name.startswith("."):
                continue
            enriched = child / "enriched"
            if enriched.is_dir() and enriched not in roots:
                roots.append(enriched)
    dash = project_root / ".dashboard" / "ingest"
    if dash.is_dir():
        for child in sorted(dash.iterdir()):
            enriched = child / "enriched"
            if enriched.is_dir():
                roots.append(enriched)
    return roots


def load_enriched_for_vault(vault_dir: Path, project_root: Path) -> list[dict]:
    """Load enriched JSON for every video_id present in vault notes (any data/ source)."""
    vids = collect_vault_video_ids(vault_dir)
    if not vids:
        return load_enriched_dir(project_root / "data" / vault_dir.parent.name) if vault_dir.name == "vault" else []

    out: list[dict] = []
    seen: set[str] = set()
    for enriched_dir in _enriched_search_roots(project_root):
        for p in sorted(enriched_dir.glob("*.json")):
            vid = p.stem
            if vid not in vids or vid in seen:
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("video_id"):
                out.append(data)
                seen.add(vid)
    return out


def merge_enriched_sources(
    data_dir: Path,
    vault_dir: Path,
    project_root: Path,
    *,
    item_filter: Callable[[dict], bool] | None = None,
) -> list[dict]:
    """Prefer data_dir/enriched; supplement from vault-matched JSON across data/."""
    primary = load_enriched_dir(data_dir)
    by_vid = {d.get("video_id"): d for d in primary if d.get("video_id")}
    for item in load_enriched_for_vault(vault_dir, project_root):
        vid = item.get("video_id")
        if not vid or vid in by_vid:
            continue
        if item_filter and not item_filter(item):
            continue
        by_vid[vid] = item
    if item_filter:
        by_vid = {k: v for k, v in by_vid.items() if item_filter(v)}
    return list(by_vid.values())
