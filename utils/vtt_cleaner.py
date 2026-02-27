"""Convert VTT subtitle content to plain text."""
import re


def clean_vtt(vtt_text: str) -> str:
    """Strip VTT timestamps, cues, and tags; return single-line plain text."""
    if not vtt_text or not vtt_text.strip():
        return ""
    lines = vtt_text.split("\n")
    seen = set()
    result = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("WEBVTT") or "-->" in line or line.isdigit():
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = re.sub(r"&amp;", "&", line)
        line = re.sub(r"&#39;", "'", line)
        if line and line not in seen:
            seen.add(line)
            result.append(line)
    return " ".join(result)
