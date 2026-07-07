"""Convert VTT subtitle content to plain text and timed cues."""
import re


def parse_vtt_cues(vtt_text: str) -> list[dict]:
    """Parse WEBVTT into [{start_sec, end_sec, text}, ...] for screenshot caption sync."""
    if not vtt_text or not vtt_text.strip():
        return []

    def _ts_to_sec(ts: str) -> float:
        ts = ts.strip()
        parts = ts.replace(",", ".").split(":")
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        if len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
        return float(parts[0])

    cues: list[dict] = []
    block_lines: list[str] = []
    block_start: str | None = None
    block_end: str | None = None

    def flush() -> None:
        nonlocal block_lines, block_start, block_end
        if block_start is None or not block_lines:
            block_lines = []
            block_start = block_end = None
            return
        text = " ".join(block_lines).strip()
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            cues.append(
                {
                    "start_sec": _ts_to_sec(block_start),
                    "end_sec": _ts_to_sec(block_end or block_start),
                    "text": text,
                }
            )
        block_lines = []
        block_start = block_end = None

    for raw in vtt_text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("WEBVTT") or line.isdigit():
            continue
        if "-->" in line:
            flush()
            start, end = line.split("-->", 1)
            block_start = start.strip().split()[0]
            block_end = end.strip().split()[0]
            continue
        if block_start is not None:
            block_lines.append(line)
    flush()
    return cues


def cue_text_at_second(cues: list[dict], seconds: float, window: float = 3.0) -> str:
    """Return transcript words spoken at/near a timestamp."""
    if not cues:
        return ""
    best = ""
    best_dist = 1e9
    for cue in cues:
        start = float(cue.get("start_sec", 0))
        end = float(cue.get("end_sec", start))
        mid = (start + end) / 2
        if start - window <= seconds <= end + window:
            return str(cue.get("text", "")).strip()
        dist = abs(mid - seconds)
        if dist < best_dist:
            best_dist = dist
            best = str(cue.get("text", "")).strip()
    return best


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
