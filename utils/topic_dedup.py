"""Deduplicate and normalize topic note text (facts, bullets, angles)."""
from __future__ import annotations

import re


def _norm(s: str) -> str:
    s = re.sub(r"\*+", "", s)
    s = re.sub(r"^[\d]+\.\s*", "", s)
    s = re.sub(r"^[-*]\s*", "", s)
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s.strip()).casefold()


def dedupe_bullets(bullets: list[str], *, min_len: int = 12, max_items: int = 8) -> list[str]:
    """Drop near-duplicate bullets; keep the longer, more specific variant."""
    out: list[str] = []
    norms: list[str] = []
    for raw in bullets:
        b = raw.strip()
        n = _norm(b)
        if not n or len(n) < min_len:
            continue
        replaced = False
        for i, existing in enumerate(norms):
            if n == existing:
                replaced = True
                break
            if n in existing or existing in n:
                if len(n) > len(existing):
                    out[i] = b
                    norms[i] = n
                replaced = True
                break
        if not replaced:
            out.append(b)
            norms.append(n)
        if len(out) >= max_items:
            break
    return out


def text_not_in_bullets(paragraph: str, bullets: list[str]) -> str:
    """Trim paragraph sentences that repeat fact bullets."""
    if not paragraph.strip():
        return ""
    pnorm = _norm(paragraph)
    for b in bullets:
        if _norm(b) in pnorm and len(_norm(b)) > 30:
            return ""
    return paragraph.strip()
