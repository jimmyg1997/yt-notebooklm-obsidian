"""Read vault notes, resolve wikilinks, and list folder trees."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from dashboard.services.vault_scanner import decode_vault_id

try:
    from utils.topic_hierarchy import cluster_display_label, theme_display_title
except ImportError:
    def theme_display_title(t: str) -> str:
        return t

    def cluster_display_label(c: str, lang: str = "el") -> str:
        return c

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
SKIP_DIRS = {".obsidian", ".trash", ".git", "__pycache__"}
_EPISODE_RE = re.compile(r"^\d{2,3}\s*-\s*.+\.md$", re.IGNORECASE)


def _parse_frontmatter(text: str) -> dict:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def _classify_note(path: str, text: str) -> str:
    """meta | video | theme | subtopic | topic | other"""
    if path.startswith("00 -"):
        return "meta"
    meta = _parse_frontmatter(text)
    if path.startswith("Topics/"):
        parts = path.split("/")
        if meta.get("role") == "theme" or "moc" in (meta.get("tags") or []):
            return "theme"
        if meta.get("parent") or "subtopic" in (meta.get("tags") or []):
            return "subtopic"
        if len(parts) >= 3:
            return "subtopic"
        if len(parts) == 2:
            if "theme" in (meta.get("tags") or []):
                return "theme"
            return "topic"
        return "topic"
    m = FRONTMATTER_RE.match(text)
    if m:
        try:
            meta = yaml.safe_load(m.group(1)) or {}
            if meta.get("source") == "youtube" or meta.get("video_id"):
                return "video"
        except yaml.YAMLError:
            pass
    if _EPISODE_RE.match(path.split("/")[-1]):
        return "video"
    if "video_id:" in text[:800] and "source: youtube" in text[:800]:
        return "video"
    return "other"


def _theme_for_path(path: str, folder: str, text: str = "") -> str:
    meta = _parse_frontmatter(text) if text else {}
    parent = meta.get("parent") or meta.get("theme")
    if isinstance(parent, str) and parent.strip():
        return parent.strip()
    if folder.startswith("Topics/"):
        parts = folder.split("/")
        if len(parts) >= 2:
            return parts[1]
    return ""


@dataclass
class NoteMeta:
    path: str
    title: str
    folder: str


class VaultReader:
    def __init__(self, vault_id: str) -> None:
        self.vault_id = vault_id
        self.root = decode_vault_id(vault_id).resolve()
        if not self.root.is_dir():
            raise FileNotFoundError(f"Vault not found: {self.root}")
        self._index_built = False
        self._by_stem: dict[str, str] = {}
        self._by_title: dict[str, str] = {}
        self._all_notes: list[NoteMeta] = []

    def _safe_path(self, rel: str) -> Path:
        rel = rel.lstrip("/").replace("\\", "/")
        target = (self.root / rel).resolve()
        if not str(target).startswith(str(self.root)):
            raise PermissionError("Path escapes vault root")
        return target

    def _parse_frontmatter_title(self, text: str, fallback: str) -> str:
        m = FRONTMATTER_RE.match(text)
        if not m:
            return fallback
        try:
            meta = yaml.safe_load(m.group(1)) or {}
            title = meta.get("title")
            if isinstance(title, str) and title.strip():
                return title.strip()
        except yaml.YAMLError:
            pass
        return fallback

    def _norm(self, s: str) -> str:
        return re.sub(r"\s+", " ", s.strip()).casefold()

    def _build_index(self) -> None:
        if self._index_built:
            return
        notes: list[NoteMeta] = []
        by_stem: dict[str, str] = {}
        by_title: dict[str, str] = {}
        for p in sorted(self.root.rglob("*.md")):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            rel = p.relative_to(self.root).as_posix()
            stem = p.stem
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            title = self._parse_frontmatter_title(text, stem)
            folder = p.parent.relative_to(self.root).as_posix()
            if folder == ".":
                folder = ""
            notes.append(NoteMeta(path=rel, title=title, folder=folder))
            for key in {self._norm(stem), self._norm(title)}:
                if key and key not in by_stem:
                    by_stem[key] = rel
            # Path-style wikilinks: Topics/foo
            rel_no_ext = rel[:-3] if rel.endswith(".md") else rel
            path_key = self._norm(rel_no_ext)
            if path_key and path_key not in by_stem:
                by_stem[path_key] = rel
            if self._norm(title) not in by_title:
                by_title[self._norm(title)] = rel
        self._all_notes = notes
        self._by_stem = by_stem
        self._by_title = by_title
        self._index_built = True

    def list_tree(self, lang: str = "el") -> list[dict]:
        self._build_index()
        ui_lang = "en" if lang == "en" else "el"
        folders: dict[str, dict] = {"": {"name": "(root)", "path": "", "children": [], "note_count": 0}}

        def ensure_folder(rel: str) -> dict:
            if rel in folders:
                return folders[rel]
            parent = "/".join(rel.split("/")[:-1]) if "/" in rel else ""
            ensure_folder(parent)
            name = rel.split("/")[-1] if rel else "(root)"
            kind = "root"
            if rel == "Topics":
                kind = "topics_root"
            elif rel.startswith("Topics/"):
                depth = rel.count("/")
                if depth == 1:
                    kind = "theme"
                elif depth == 2:
                    kind = "cluster"
                else:
                    kind = "subtopic_folder"
            elif rel == "":
                kind = "root"
            elif not rel:
                kind = "videos"
            display_name = name
            if kind == "theme":
                display_name = theme_display_title(name, ui_lang)
            elif kind == "cluster":
                display_name = cluster_display_label(name, ui_lang)
            node = {
                "name": name,
                "display_name": display_name,
                "path": rel,
                "children": [],
                "note_count": 0,
                "kind": kind,
            }
            folders[rel] = node
            folders[parent]["children"].append(node)
            return node

        for note in self._all_notes:
            folder = note.folder or ""
            ensure_folder(folder)
            folders[folder]["note_count"] += 1
            for part in folder.split("/"):
                if part:
                    pass
            if folder:
                parts = folder.split("/")
                acc = ""
                for part in parts:
                    acc = f"{acc}/{part}" if acc else part
                    ensure_folder(acc)

        def sort_children(node: dict) -> None:
            node["children"].sort(key=lambda c: c["name"].lower())
            for child in node["children"]:
                sort_children(child)

        root = folders[""]
        sort_children(root)
        return root["children"]

    def list_notes(self, folder: str = "") -> list[dict]:
        self._build_index()
        folder = folder.strip("/")
        out: list[dict] = []
        for note in self._all_notes:
            n_folder = note.folder or ""
            if folder:
                if folder == "Topics":
                    if not (n_folder == "Topics" or n_folder.startswith("Topics/")):
                        continue
                elif folder.startswith("Topics/"):
                    if not (n_folder == folder or n_folder.startswith(folder + "/")):
                        continue
                elif n_folder != folder:
                    continue
            elif n_folder:
                continue
            out.append({"path": note.path, "title": note.title})
        out.sort(key=lambda x: x["title"].casefold())
        return out

    def list_all_notes_flat(self, lang: str = "el") -> list[dict]:
        self._build_index()
        ui_lang = "en" if lang == "en" else "el"

        def sort_key(n: NoteMeta) -> tuple:
            try:
                text = self._safe_path(n.path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            ntype = _classify_note(n.path, text)
            theme = _theme_for_path(n.path, n.folder, text)
            if ntype == "meta":
                return (0, n.path.lower())
            if ntype == "video":
                return (1, n.title.casefold())
            if ntype == "theme":
                return (2, theme.casefold(), n.title.casefold())
            if ntype in ("subtopic", "topic"):
                return (3, theme.casefold(), n.title.casefold())
            return (4, n.path.lower())

        ordered = sorted(self._all_notes, key=sort_key)
        out: list[dict] = []
        for n in ordered:
            try:
                text = self._safe_path(n.path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            ntype = _classify_note(n.path, text)
            theme = _theme_for_path(n.path, n.folder, text)
            display = n.title
            try:
                from dashboard.services.note_localizer import localized_title

                display = localized_title(n.title, n.path, ui_lang)
            except ImportError:
                pass
            out.append(
                {
                    "path": n.path,
                    "title": display,
                    "title_raw": n.title,
                    "folder": n.folder or "",
                    "note_type": ntype,
                    "theme": theme,
                }
            )
        return out

    def read_note(self, rel_path: str, lang: str = "el") -> dict:
        path = self._safe_path(rel_path)
        if not path.is_file():
            raise FileNotFoundError(rel_path)
        text = path.read_text(encoding="utf-8", errors="replace")
        self._build_index()
        title = self._parse_frontmatter_title(text, path.stem)
        ui_lang = "en" if lang == "en" else "el"
        try:
            from dashboard.services.note_localizer import localize_markdown, localized_title

            display_title = localized_title(title, rel_path, ui_lang)
            body = localize_markdown(text, ui_lang)
        except ImportError:
            display_title = title
            body = text
        wikilinks = [
            {"target": m.group(1).strip(), "alias": (m.group(2) or m.group(1)).strip()}
            for m in WIKILINK_RE.finditer(text)
        ]
        return {
            "path": rel_path.replace("\\", "/"),
            "title": display_title,
            "title_raw": title,
            "content": body,
            "content_raw": text,
            "wikilinks": wikilinks,
            "lang": ui_lang,
        }

    def resolve_wikilink(self, target: str) -> dict:
        self._build_index()
        target = target.strip()
        if not target:
            return {"found": False, "path": None, "title": None}
        if target.endswith(".md"):
            target = target[:-3]
        key = self._norm(target)
        rel = self._by_stem.get(key) or self._by_title.get(key)
        if not rel:
            # partial stem match (Obsidian tolerates shortened links)
            for note in self._all_notes:
                if self._norm(note.title).startswith(key) or self._norm(note.path).startswith(key):
                    rel = note.path
                    break
        if not rel:
            return {"found": False, "path": None, "title": None}
        title = next((n.title for n in self._all_notes if n.path == rel), Path(rel).stem)
        return {"found": True, "path": rel, "title": title}

    def build_graph(self, scope: str = "overview", focus: str = "") -> dict:
        """Obsidian-style graph. scope: overview | theme | subtopic | full."""
        self._build_index()
        scope = (scope or "overview").lower()
        focus = focus.strip().lstrip("/")

        note_types: dict[str, str] = {}
        note_texts: dict[str, str] = {}
        for note in self._all_notes:
            try:
                text = self._safe_path(note.path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            note_texts[note.path] = text
            note_types[note.path] = _classify_note(note.path, text)

        theme_paths: dict[str, str] = {}
        for note in self._all_notes:
            if note.path.startswith("Topics/") and note.path.count("/") == 1:
                theme_paths[self._norm(note.title)] = note.path
                meta = _parse_frontmatter(note_texts.get(note.path, ""))
                slug = note.path.split("/")[-1].replace(".md", "")
                theme_paths[self._norm(slug)] = note.path
                if meta.get("theme"):
                    theme_paths[self._norm(str(meta["theme"]))] = note.path

        allowed: set[str] | None = None
        if scope == "overview":
            allowed = {
                n.path for n in self._all_notes
                if note_types[n.path] in ("meta", "theme", "video")
            }
        elif scope == "theme" and focus:
            focus_base = focus.replace(".md", "").strip("/")
            prefix = focus_base if focus_base.startswith("Topics/") else f"Topics/{focus_base}"
            theme_md = f"{prefix}.md" if not prefix.endswith(".md") else prefix
            allowed = {
                n.path for n in self._all_notes
                if n.path == theme_md
                or n.path == prefix
                or n.path.startswith(prefix + "/")
            }
        elif scope == "subtopic" and focus:
            allowed = {focus if focus.endswith(".md") else focus + ".md"}
            allowed = {p for p in allowed if any(n.path == p for n in self._all_notes)}
            seed = next(iter(allowed), "")
            if seed:
                allowed = {seed}
                for note in self._all_notes:
                    text = note_texts.get(note.path, "")
                    if seed.split("/")[-1].replace(".md", "") in text or note.path in text:
                        allowed.add(note.path)
        elif scope == "full":
            allowed = {n.path for n in self._all_notes}

        if allowed is None:
            allowed = {n.path for n in self._all_notes if note_types[n.path] in ("meta", "theme", "video")}

        if scope in ("theme", "full") and len(allowed) > 220:
            subtopics = sorted(p for p in allowed if note_types.get(p) in ("subtopic", "topic"))
            allowed -= set(subtopics[180:])

        if scope == "theme":
            linked_videos: set[str] = set()
            for note in self._all_notes:
                if note_types.get(note.path) != "video":
                    continue
                text = note_texts.get(note.path, "")
                for m in WIKILINK_RE.finditer(text):
                    resolved = self.resolve_wikilink(m.group(1).strip())
                    tgt = resolved.get("path") if resolved.get("found") else None
                    if tgt and tgt in allowed:
                        linked_videos.add(note.path)
                        break
            allowed |= linked_videos

        nodes: list[dict] = []
        edges: list[dict] = []
        seen_edges: set[tuple[str, str, str]] = set()

        def add_edge(src: str, tgt: str, kind: str = "wikilink") -> None:
            if src not in allowed or tgt not in allowed or src == tgt:
                return
            key = (src, tgt, kind)
            if key in seen_edges:
                return
            seen_edges.add(key)
            edges.append({"source": src, "target": tgt, "kind": kind})

        for note in self._all_notes:
            if note.path not in allowed:
                continue
            ntype = note_types[note.path]
            group = "root"
            level = 0
            if ntype == "meta":
                group, level = "meta", 0
            elif ntype == "video":
                group, level = "video", 1
            elif ntype == "theme":
                group, level = "theme", 2
            elif ntype in ("subtopic", "topic"):
                group = "subtopic"
                level = 4 if note.path.count("/") >= 3 else 3
            elif note.folder.startswith("Topics/"):
                group, level = "topic", 3
            nodes.append({
                "id": note.path,
                "label": note.title,
                "group": group,
                "level": level,
            })

        for note in self._all_notes:
            if note.path not in allowed:
                continue
            text = note_texts.get(note.path, "")
            meta = _parse_frontmatter(text)
            parent = meta.get("parent") or meta.get("theme")
            if isinstance(parent, str) and parent.strip():
                parent_path = theme_paths.get(self._norm(parent.strip()))
                if parent_path and parent_path in allowed:
                    add_edge(note.path, parent_path, "hierarchy")

            if scope == "overview":
                continue
            for m in WIKILINK_RE.finditer(text):
                target = m.group(1).strip()
                resolved = self.resolve_wikilink(target)
                if not resolved.get("found") or not resolved.get("path"):
                    continue
                tgt = resolved["path"]
                if tgt in allowed:
                    add_edge(note.path, tgt, "wikilink")

        if scope == "overview":
            for note in self._all_notes:
                if note.path not in allowed or note_types[note.path] != "video":
                    continue
                text = note_texts.get(note.path, "")
                for m in WIKILINK_RE.finditer(text):
                    resolved = self.resolve_wikilink(m.group(1).strip())
                    tgt = resolved.get("path") if resolved.get("found") else None
                    if tgt and tgt in allowed and note_types.get(tgt) == "theme":
                        add_edge(note.path, tgt, "wikilink")

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {"nodes": len(nodes), "edges": len(edges), "scope": scope, "focus": focus},
        }

    def backlinks(self, rel_path: str) -> list[dict]:
        self._build_index()
        path = self._safe_path(rel_path)
        target_title = path.stem
        note = self.read_note(rel_path)
        target_title = note["title"]
        keys = {self._norm(target_title), self._norm(path.stem), self._norm(path.name)}
        hits: list[dict] = []
        for n in self._all_notes:
            if n.path == rel_path.replace("\\", "/"):
                continue
            try:
                text = self._safe_path(n.path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in WIKILINK_RE.finditer(text):
                link_target = self._norm(m.group(1).strip())
                if link_target in keys or any(link_target in k or k in link_target for k in keys):
                    hits.append({"path": n.path, "title": n.title})
                    break
        return hits
