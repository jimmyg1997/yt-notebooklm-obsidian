"""Smart theme → subtopic hierarchy for vault topic notes."""
from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip()).casefold()


# Canonical parent themes (max ~5). Vault meta themes map into these.
CANONICAL_THEMES = ("υγεία", "διατροφή", "επιστήμη", "ευεξία", "μάθηση")
BUSINESS_CANONICAL_THEMES = ("επιχειρηματικότητα", "οικονομία", "καριέρα", "marketing", "μάθηση")

# Rich display titles for theme MOC notes (filename stays canonical slug)
THEME_LABELS: dict[str, dict[str, str]] = {
    "υγεία": {
        "title": "Υγεία & Μεταβολισμός",
        "title_en": "Health & Metabolism",
        "tagline": "Μηχανισμοί σώματος, γλυκόζη, ινσουλίνη και μακροπρόθεσμη υγεία — όπως προκύπτουν από τα βίντεό σου.",
        "tagline_en": "Body mechanisms, glucose, insulin, and long-term health from your analyzed videos.",
    },
    "διατροφή": {
        "title": "Διατροφή & Τροφές",
        "title_en": "Nutrition & Foods",
        "tagline": "Συγκεκριμένες τροφές, θρεπτικά συστατικά και διατροφικές συνήθειες από τα επεισόδια που ανέλυσες.",
        "tagline_en": "Specific foods, nutrients, and eating habits from your analyzed episodes.",
    },
    "επιστήμη": {
        "title": "Επιστήμη & Μηχανισμοί",
        "title_en": "Science & Mechanisms",
        "tagline": "Βιολογικοί μηχανισμοί, έρευνα και εξήγηση «γιατί» πίσω από τις συμβουλές των βίντεο.",
        "tagline_en": "Biological mechanisms, research, and the science behind video advice.",
    },
    "ευεξία": {
        "title": "Ευεξία & Ζωή",
        "title_en": "Wellness & Life",
        "tagline": "Ύπνος, άσκηση, άγχος και καθημερινές συνήθειες που επηρεάζουν την ενέργειά σου.",
        "tagline_en": "Sleep, exercise, stress, and daily habits that affect your energy.",
    },
    "μάθηση": {
        "title": "Μάθηση & Οργάνωση",
        "title_en": "Learning & Organization",
        "tagline": "Πώς συνδέεις, θυμάσαι και αξιοποιείς γνώση από βίντεο σε προσωπικές σημειώσεις.",
        "tagline_en": "How you connect, remember, and use knowledge from videos in personal notes.",
    },
    "επιχειρηματικότητα": {
        "title": "Επιχειρηματικότητα & Startups",
        "title_en": "Entrepreneurship & Startups",
        "tagline": "Ίδρυση, ανάπτυξη και λειτουργία επιχειρήσεων — από τα επεισόδια Ολ Ιν.",
        "tagline_en": "Building and running businesses — from Ολ Ιν episodes.",
    },
    "οικονομία": {
        "title": "Οικονομία & Επενδύσεις",
        "title_en": "Economics & Investing",
        "tagline": "Χρήμα, αποταμίευση, επενδύσεις και οικονομική σκέψη.",
        "tagline_en": "Money, savings, investing, and financial thinking.",
    },
    "καριέρα": {
        "title": "Καριέρα & Εργασία",
        "title_en": "Career & Work",
        "tagline": "Μισθός, εργασία, δεξιότητες και επαγγελματική εξέλιξη.",
        "tagline_en": "Salary, work, skills, and professional growth.",
    },
    "marketing": {
        "title": "Marketing & Brand",
        "title_en": "Marketing & Brand",
        "tagline": "Προσωπικό brand, πωλήσεις, digital marketing και online εισόδημα.",
        "tagline_en": "Personal brand, sales, digital marketing, and online income.",
    },
}

SUBTOPIC_CLUSTERS: dict[str, tuple[str, ...]] = {
    "καρδιά": (
        "καρδ", "χοληστερ", "λιπιδ", "τριγλυκ", "αθηροσ", "αρτηρ", "στεφαν", "καρδιαγγ",
    ),
    "έντερο": (
        "έντερ", "πεψ", "μικροβιω", "προβιοτ", "γαστρ", "δυσπεψ", "σύνδρομο", "κολον",
    ),
    "ορμόνες": (
        "ορμόν", "λεπτίν", "θυρεο", "επινεφρ", "κορτιζ", "τεστοσ", "οιστρο",
    ),
    "ανοσο": (
        "ανοσο", "αυτοάνοσ", "φλεγμ", "αλλεργ", "κύτταρ",
    ),
    "βιταμίνες": (
        "βιταμ", "θρεπτ", "συμπληρ", "μεταλλ", "μικροθρεπ", "μαγνησ", "ψευδάργ",
    ),
    "τρόφιμα": (
        "αβγ", "γιαούρτι", "σολομ", "καρύδ", "μπανάνα", "κεφίρ", "ελαιόλαδο",
        "σπόρο", "τσία", "skyr", "biedronka", "πρωιν", "γεύμα", "τροφ", "διατροφ",
    ),
    "συνήθειες": (
        "συνήθει", "πρωινό", "ενδιάμεσ", "ισορροπ", "μοτίβ", "ρουτίνα", "ύπν", "άσκησ",
    ),
    "μηχανισμοί": (
        "ινσουλ", "γλυκ", "μεταβολ", "μιτοχονδρ", "μηχανισμ", "βιολογ",
    ),
    "κλινικά": (
        "εξέτασ", "διαγν", "θεραπ", "ασθεν", "κλινικ", "ιατρ", "παρακολ",
    ),
    "έπιπεδα": (
        "επίπεδ", "δείκτ", "ανάλυσ", "αιμα", "μετρ", "όριο",
    ),
}

CLUSTER_LABELS: dict[str, dict[str, str]] = {
    "καρδιά": {"el": "Καρδιά & λιπίδια", "en": "Heart & lipids"},
    "έντερο": {"el": "Έντερο & πέψη", "en": "Gut & digestion"},
    "ορμόνες": {"el": "Ορμόνες", "en": "Hormones"},
    "ανοσο": {"el": "Ανοσοποιητικό", "en": "Immune system"},
    "βιταμίνες": {"el": "Βιταμίνες & θρεπτικά", "en": "Vitamins & nutrients"},
    "τρόφιμα": {"el": "Τρόφιμα & διατροφή", "en": "Foods & nutrition"},
    "συνήθειες": {"el": "Συνήθειες & lifestyle", "en": "Habits & lifestyle"},
    "μηχανισμοί": {"el": "Μηχανισμοί σώματος", "en": "Body mechanisms"},
    "κλινικά": {"el": "Κλινικά & θεραπεία", "en": "Clinical & treatment"},
    "έπιπεδα": {"el": "Επίπεδα & εξετάσεις", "en": "Levels & labs"},
    "έννοιες": {"el": "Άλλες έννοιες", "en": "Other concepts"},
}

CLUSTER_ORDER = (
    "καρδιά", "έντερο", "ορμόνες", "ανοσο", "βιταμίνες", "τρόφιμα",
    "συνήθειες", "μηχανισμοί", "κλινικά", "έπιπεδα", "έννοιες",
)


def cluster_display_label(cluster: str, lang: str = "el") -> str:
    entry = CLUSTER_LABELS.get(cluster, {})
    return entry.get(lang) or entry.get("el") or cluster


def theme_display_title(theme: str, lang: str = "el") -> str:
    key = next((k for k in THEME_LABELS if _norm(k) == _norm(theme)), theme)
    entry = THEME_LABELS.get(key, {})
    if lang == "en":
        return entry.get("title_en") or entry.get("title", theme)
    return entry.get("title", theme)


def theme_tagline(theme: str, lang: str = "el") -> str:
    key = next((k for k in THEME_LABELS if _norm(k) == _norm(theme)), theme)
    entry = THEME_LABELS.get(key, {})
    if lang == "en":
        return entry.get("tagline_en") or entry.get("tagline", "")
    return entry.get("tagline", "")


def cluster_subtopic(name: str) -> str:
    n = _norm(name)
    for label, keywords in SUBTOPIC_CLUSTERS.items():
        if any(kw in n for kw in keywords):
            return label
    return "έννοιες"


THEME_ALIASES: dict[str, str] = {
    "αντίσταση στην ινσουλίνη": "υγεία",
    "αντιοξειδωτικά": "διατροφή",
    "προσωπική ανάπτυξη": "μάθηση",
    "παρακολούθηση βίντεο": "μάθηση",
    "health": "υγεία",
    "nutrition": "διατροφή",
    "science": "επιστήμη",
    "wellness": "ευεξία",
}

# Keyword hints for assignment when LLM unavailable
THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "διατροφή": (
        "τροφ", "διατροφ", "φαγη", "γεύμα", "πρωιν", "αβγ", "γιαούρτι", "σολομ",
        "καρύδ", "μπανάνα", "κεφίρ", "πρωτεΐν", "βιταμίν", "ίνα", "ελαιόλαδο",
        "σπόρο", "τσία", "biedronka", "skyr", "γαλακτο",
    ),
    "υγεία": (
        "υγε", "ινσουλ", "σακχαρ", "γλυκ", "διαβήτ", "πίεση", "αρτηρ",
        "καρδ", "μεταβολ", "μιτοχονδρ", "φλεγμ", "ανοσο", "ορμόν",
    ),
    "επιστήμη": (
        "επιστήμ", "έρευν", "μελέτ", "δεδομέν", "βιολογ", "μηχανισμ",
        "κλινικ", "lab", "συστατικ",
    ),
    "ευεξία": (
        "ευεξ", "άσκησ", "γυμναστ", "ύπν", "άγχ", "στρες", "ενέργει",
        "προσωπικ", "ανάπτυξ", "συνήθει",
    ),
    "μάθηση": (
        "μάθησ", "μαθή", "σημειώσ", "βίντεο", "πολύπλοκ", "κατανόησ",
    ),
    "επιχειρηματικότητα": (
        "επιχειρ", "startup", "business", "εταιρε", "founder", "ολ ιν",
    ),
    "οικονομία": (
        "οικονομ", "επενδ", "αποταμι", "μίσθ", "χρήμα", "πλούτ", "φόρο", "ακίνητ",
        "χρηματιστ", "σύνταξ",
    ),
    "καριέρα": (
        "καριέρ", "kariera", "δουλει", "εργασ", "προσλήψ", "μισθ", "skills",
    ),
    "marketing": (
        "marketing", "brand", "dropship", "freelanc", "affiliate", "online", "πωλ", "πελάτ",
        "cringe", "social media",
    ),
}


def canonicalize_themes(vault_themes: list[str], *, profile: str = "health") -> list[str]:
    """Reduce vault theme list to canonical parents (≤5)."""
    base = BUSINESS_CANONICAL_THEMES if profile == "business" else CANONICAL_THEMES
    seen: set[str] = set()
    out: list[str] = []
    for t in vault_themes:
        t = t.strip()
        if not t:
            continue
        mapped = THEME_ALIASES.get(_norm(t), t)
        if _norm(mapped) in {_norm(c) for c in base}:
            key = next(c for c in base if _norm(c) == _norm(mapped))
        else:
            key = mapped
        if _norm(key) not in seen:
            seen.add(_norm(key))
            out.append(key)
    for c in base:
        if _norm(c) not in seen and len(out) < 5:
            out.append(c)
            seen.add(_norm(c))
    return out[:5]


def is_parent_theme(concept: str, themes: list[str]) -> bool:
    return any(_norm(concept) == _norm(t) for t in themes)


def keyword_assign_parent(concept: str, themes: list[str]) -> str | None:
    """Pick best parent theme via keyword scoring."""
    if not themes or is_parent_theme(concept, themes):
        return None
    c = _norm(concept)
    alias = THEME_ALIASES.get(c)
    if alias and any(_norm(t) == _norm(alias) for t in themes):
        return next(t for t in themes if _norm(t) == _norm(alias))

    scores: dict[str, int] = {t: 0 for t in themes}
    for theme, keywords in THEME_KEYWORDS.items():
        parent = next((t for t in themes if _norm(t) == _norm(theme)), None)
        if not parent:
            continue
        for kw in keywords:
            if kw in c:
                scores[parent] += 3
    # Also score against enriched-related text overlap
    for theme in themes:
        if _norm(theme) in c or c in _norm(theme):
            scores[theme] += 5

    best = max(scores.items(), key=lambda x: x[1])
    if best[1] > 0:
        return best[0]
    # Default: διατροφή for food-like, else first theme
    if any(k in c for k in THEME_KEYWORDS["διατροφή"]):
        food_theme = next((t for t in themes if _norm(t) == "διατροφή"), None)
        if food_theme:
            return food_theme
    return themes[0] if themes else None


def cooccurrence_parents(
    concepts: list[str],
    mentions_map: dict[str, list],
) -> dict[str, str | None]:
    """Boost assignment: concepts co-mentioned in same videos share parent."""
    concept_videos: dict[str, set[str]] = defaultdict(set)
    for concept, mentions in mentions_map.items():
        for item in mentions:
            vid = item[4] if len(item) > 4 else item[0]
            concept_videos[concept].add(str(vid))

    parent_votes: dict[str, Counter] = defaultdict(Counter)
    for c in concepts:
        parent_votes[c]  # ensure key

    return {}  # used as hint layer in merge_assignments


def merge_parent_maps(*maps: dict[str, str | None]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for m in maps:
        for k, v in m.items():
            if k not in out or (out[k] is None and v is not None):
                out[k] = v
    return out


def assign_hierarchy(
    concepts: list[str],
    vault_themes: list[str],
    *,
    use_llm: bool = True,
    theme_profile: str = "health",
) -> tuple[list[str], dict[str, str | None]]:
    """
    Returns (canonical_parent_themes, concept→parent map).
    Parent themes have parent None; all other concepts get a parent theme.
    """
    parents = canonicalize_themes(vault_themes, profile=theme_profile)
    # Concepts that are parent theme names are not subtopic files
    subconcepts = [c for c in concepts if not is_parent_theme(c, parents)]

    llm_map: dict[str, str | None] = {}
    if use_llm and subconcepts:
        from utils.topic_content import assign_parent_themes_llm

        llm_map = assign_parent_themes_llm(subconcepts, parents)

    final: dict[str, str | None] = {}
    for c in concepts:
        if is_parent_theme(c, parents):
            final[c] = None
            continue
        parent = llm_map.get(c)
        if parent and _norm(parent) not in {_norm(p) for p in parents}:
            parent = keyword_assign_parent(c, parents)
        if not parent:
            parent = keyword_assign_parent(c, parents)
        final[c] = parent

    return parents, final


def validate_parent_map(
    parent_map: dict[str, str | None],
    themes: list[str],
) -> dict[str, str | None]:
    """Ensure every subtopic has a valid parent."""
    theme_norm = {_norm(t): t for t in themes}
    out: dict[str, str | None] = {}
    default = themes[0] if themes else None
    for concept, parent in parent_map.items():
        if is_parent_theme(concept, themes):
            out[concept] = None
            continue
        if parent and _norm(parent) in theme_norm:
            out[concept] = theme_norm[_norm(parent)]
        else:
            out[concept] = keyword_assign_parent(concept, themes) or default
    return out
