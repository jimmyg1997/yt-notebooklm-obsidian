const params = new URLSearchParams(window.location.search);
const vaultId = params.get("vault");
window.vaultId = vaultId;

let allNotes = [];
let activeFolder = null;
let activeNotePath = null;
let activeNoteRaw = "";
let noteLoadProgress = null;
let editing = false;

function showToast(msg, isError = false) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.classList.toggle("error", isError);
  el.hidden = false;
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => { el.hidden = true; }, 4500);
}

function isProtectedNote(path) {
  const name = path.split("/").pop() || "";
  return name.startsWith("00 -");
}

function setNoteToolbar(path, title) {
  const actions = document.getElementById("note-actions");
  const label = document.getElementById("note-path-label");
  const fallback = typeof VaultI18n !== "undefined" ? VaultI18n.t("selectNote") : "Select a note";
  if (label) label.textContent = title || path || fallback;
  if (actions) actions.hidden = !path || isProtectedNote(path);
}

async function fetchJson(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function renderTree(nodes, depth = 0) {
  return nodes.map((n) => {
    const count = n.note_count ? ` (${n.note_count})` : "";
    const kind = n.kind || "folder";
    const label = n.display_name || n.name;
    const icon = {
      topics_root: "📚",
      theme: "◆",
      cluster: "▸",
      subtopic_folder: "▹",
      root: "📹",
    }[kind] || "📁";
    const children = n.children?.length ? renderTree(n.children, depth + 1) : "";
    return `<div class="tree-item tree-item--${kind}" data-folder="${escapeHtml(n.path)}" style="--depth:${depth}"><span class="tree-icon">${icon}</span><span class="tree-label">${escapeHtml(label)}</span><span class="tree-count">${count}</span></div>${children}`;
  }).join("");
}

function noteTypeLabel(type) {
  if (typeof VaultI18n !== "undefined") {
    return VaultI18n.t({ video: "video", theme: "theme", subtopic: "subtopic", topic: "subtopic", meta: "meta" }[type] || "note");
  }
  return {
    video: "Video",
    theme: "Theme",
    subtopic: "Subtopic",
    topic: "Topic",
    meta: "Index",
    other: "Note",
  }[type] || "Note";
}

function filteredNotes() {
  const q = document.getElementById("note-search").value.trim().toLowerCase();
  return allNotes.filter((n) => {
    // Theme MOCs live in the sidebar tree — hide from flat "all notes" list
    if (activeFolder === null && n.note_type === "theme") {
      return false;
    }
    let inFolder = true;
    if (activeFolder !== null && activeFolder !== "") {
      const folder = n.folder || "";
      if (activeFolder === "Topics") {
        inFolder = folder === "Topics" || folder.startsWith("Topics/");
      } else if (activeFolder.startsWith("Topics/")) {
        inFolder = folder === activeFolder || folder.startsWith(activeFolder + "/");
      } else {
        inFolder = folder === activeFolder;
      }
    }
    const matches = !q || n.title.toLowerCase().includes(q) || n.path.toLowerCase().includes(q)
      || (n.theme || "").toLowerCase().includes(q);
    return inFolder && matches;
  });
}

function renderNoteList() {
  const list = document.getElementById("note-list");
  const notes = filteredNotes();
  let html = "";
  let lastGroup = null;

  notes.forEach((n) => {
    const type = n.note_type || "other";
    let groupKey = type;
    if (type === "subtopic" || type === "topic") {
      groupKey = `topic:${n.theme || "Topics"}`;
    }
    if (activeFolder === null && groupKey !== lastGroup) {
      lastGroup = groupKey;
      const label =
        type === "video" ? (typeof VaultI18n !== "undefined" ? VaultI18n.t("groupVideos") : "📹 YouTube videos")
        : type === "meta" ? (typeof VaultI18n !== "undefined" ? VaultI18n.t("groupMeta") : "📋 Index & guides")
        : type === "theme" ? (typeof VaultI18n !== "undefined" ? VaultI18n.t("groupThemes") : "📂 Themes")
        : type === "subtopic" || type === "topic"
          ? `${typeof VaultI18n !== "undefined" ? VaultI18n.t("groupTopics") : "📚 Topics"}${n.theme ? ` · ${n.theme}` : ""}`
          : noteTypeLabel(type);
      if (type !== "meta" || lastGroup === "meta") {
        html += `<div class="note-group-header">${escapeHtml(label)}</div>`;
      }
    }
    const themeBadge = n.theme && (type === "subtopic" || type === "topic")
      ? `<span class="note-theme-tag">${escapeHtml(n.theme)}</span>` : "";
    html += `<div class="note-item note-item--${type}${n.path === activeNotePath ? " active" : ""}" data-path="${escapeHtml(n.path)}">
      <span class="note-type-pill">${noteTypeLabel(type)}</span>
      <span class="note-item-title">${escapeHtml(n.title)}</span>${themeBadge}
    </div>`;
  });

  list.innerHTML = html || `<p class='loading'>${typeof VaultI18n !== "undefined" ? VaultI18n.t("noNotesInFolder") : "No notes in this folder."}</p>`;
  list.querySelectorAll(".note-item").forEach((el) => {
    el.addEventListener("click", () => openNote(el.dataset.path));
  });
}

function preprocessWikilinks(content, vaultId) {
  return content.replace(/\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]/g, (_, target, alias) => {
    const label = alias || target;
    return `<a href="#" class="wikilink" data-target="${escapeHtml(target.trim())}" data-vault="${vaultId}">${escapeHtml(label.trim())}</a>`;
  });
}

function stripFrontmatter(content) {
  return content.replace(/^---\s*\n[\s\S]*?\n---\s*\n/, "");
}

function showNoteLoading(label) {
  const container = document.getElementById("note-content");
  container.innerHTML = '<div id="note-load-progress" class="progress-panel"></div>';
  noteLoadProgress = ProgressUI.mount(container.querySelector("#note-load-progress"));
  noteLoadProgress.indeterminate(label);
}

async function openNote(path) {
  activeNotePath = path;
  window.activeNotePath = path;
  editing = false;
  renderNoteList();
  setNoteToolbar(path);
  showNoteLoading(typeof VaultI18n !== "undefined" ? VaultI18n.t("loadingNote") : "Loading note…");
  try {
    const note = await fetchJson(noteApiUrl(path));
    activeNoteRaw = note.content_raw || note.content;
    if (noteLoadProgress) noteLoadProgress.update({ percent: 55, label: typeof VaultI18n !== "undefined" ? VaultI18n.t("rendering") : "Rendering…", detail: path });
    setNoteToolbar(path, note.title);
    await renderNoteView(path, note.content);
  } catch (err) {
    const container = document.getElementById("note-content");
    if (noteLoadProgress) noteLoadProgress.fail(`Error: ${err.message}`);
    else container.innerHTML = `<p>Error: ${escapeHtml(err.message)}</p>`;
  }
}

async function renderNoteView(path, rawContent) {
  const container = document.getElementById("note-content");
  const body = preprocessWikilinks(stripFrontmatter(rawContent), vaultId);
  const html = marked.parse(body, { mangle: false, headerIds: false });
  const backlinks = await fetchJson(`/api/vaults/${encodeURIComponent(vaultId)}/backlinks?path=${encodeURIComponent(path)}`);
  if (noteLoadProgress) noteLoadProgress.update({ percent: 90, label: "Backlinks…", detail: "" });
  const blHtml = backlinks.backlinks.length
    ? `<div class="backlinks"><h4>${typeof VaultI18n !== "undefined" ? VaultI18n.t("backlinks") : "Backlinks"}</h4><ul>${backlinks.backlinks.map((b) =>
        `<li><a href="#" class="note-jump" data-path="${escapeHtml(b.path)}">${escapeHtml(b.title)}</a></li>`
      ).join("")}</ul></div>`
    : "";
  container.innerHTML = html + blHtml;
  bindWikilinks(container);
  container.querySelectorAll(".note-jump").forEach((a) => {
    a.addEventListener("click", (e) => { e.preventDefault(); openNote(a.dataset.path); });
  });
  fixAssetPaths(container, path);
  noteLoadProgress = null;
}

function enterEditMode() {
  if (!activeNotePath || isProtectedNote(activeNotePath)) {
    showToast("Index/meta notes (00 -*) cannot be edited here", true);
    return;
  }
  editing = true;
  const container = document.getElementById("note-content");
  container.innerHTML = `
    <textarea id="note-editor" class="note-editor"></textarea>
    <div class="editor-actions">
      <button type="button" id="btn-save-note" class="ingest-submit-btn">Save</button>
      <button type="button" id="btn-cancel-edit" class="btn-ghost">Cancel</button>
    </div>`;
  const ta = document.getElementById("note-editor");
  if (ta) ta.value = activeNoteRaw;
  document.getElementById("btn-save-note").addEventListener("click", saveNote);
  document.getElementById("btn-cancel-edit").addEventListener("click", () => {
    editing = false;
    renderNoteView(activeNotePath, activeNoteRaw);
  });
}

function bindExplorerChrome() {
  document.getElementById("btn-edit-vault")?.addEventListener("click", (e) => {
    e.preventDefault();
    if (!vaultId) return;
    VaultEdit.open(vaultId).catch((err) => showToast(err.message, true));
  });
  document.getElementById("btn-edit-note")?.addEventListener("click", (e) => {
    e.preventDefault();
    enterEditMode();
  });
  document.getElementById("btn-delete-note")?.addEventListener("click", (e) => {
    e.preventDefault();
    deleteActiveNote();
  });
}
bindExplorerChrome();

async function saveNote() {
  const ta = document.getElementById("note-editor");
  if (!ta || !activeNotePath) return;
  const content = ta.value;
  try {
    await fetchJson(`/api/vaults/${encodeURIComponent(vaultId)}/note`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: activeNotePath, content }),
    });
    activeNoteRaw = content;
    editing = false;
    showToast("Note saved");
    await renderNoteView(activeNotePath, content);
    if (document.querySelector('.pane-tab[data-tab="graph"].active')) {
    VaultGraph.reloadFromUi(vaultId);
  }
  } catch (err) {
    showToast(err.message, true);
  }
}

async function deleteActiveNote() {
  if (!activeNotePath || isProtectedNote(activeNotePath)) return;
  if (!confirm(`Delete "${activeNotePath}"? This cannot be undone.`)) return;
  try {
    await fetchJson(`/api/vaults/${encodeURIComponent(vaultId)}/note?path=${encodeURIComponent(activeNotePath)}`, {
      method: "DELETE",
    });
    showToast("Note deleted");
    allNotes = allNotes.filter((n) => n.path !== activeNotePath);
    activeNotePath = null;
    activeNoteRaw = "";
    setNoteToolbar(null);
    renderNoteList();
    document.getElementById("note-content").innerHTML = "<p class='loading'>Note deleted. Select another note.</p>";
  } catch (err) {
    showToast(err.message, true);
  }
}

function fixAssetPaths(container, notePath) {
  const noteDir = notePath.includes("/") ? notePath.replace(/\/[^/]+$/, "") : "";
  container.querySelectorAll("img").forEach((img) => {
    const src = img.getAttribute("src");
    if (!src || src.startsWith("http") || src.startsWith("/api/")) return;
    const rel = src.startsWith("./") ? src.slice(2) : src;
    const assetPath = noteDir ? `${noteDir}/${rel}` : rel;
    img.src = `/api/vaults/${encodeURIComponent(vaultId)}/asset?path=${encodeURIComponent(assetPath)}`;
  });
}

function bindWikilinks(root) {
  root.querySelectorAll(".wikilink").forEach((a) => {
    a.addEventListener("click", async (e) => {
      e.preventDefault();
      const target = a.dataset.target;
      try {
        const res = await fetchJson(`/api/vaults/${encodeURIComponent(vaultId)}/resolve?target=${encodeURIComponent(target)}`);
        if (res.found) {
          openNote(res.path);
        } else {
          a.classList.add("unresolved");
        }
      } catch {
        a.classList.add("unresolved");
      }
    });
  });
}

function bindTree(treeEl) {
  treeEl.querySelectorAll(".tree-item").forEach((el) => {
    el.addEventListener("click", () => {
      treeEl.querySelectorAll(".tree-item").forEach((x) => x.classList.remove("active"));
      el.classList.add("active");
      activeFolder = el.dataset.folder || "";
      window.activeFolder = activeFolder === "" ? null : activeFolder;
      if (activeFolder === "") activeFolder = null;
      renderNoteList();
    });
  });
}

function uiLang() {
  return typeof VaultI18n !== "undefined" ? VaultI18n.lang : "el";
}

function noteApiUrl(path) {
  return `/api/vaults/${encodeURIComponent(vaultId)}/note?path=${encodeURIComponent(path)}&lang=${encodeURIComponent(uiLang())}`;
}

function notesApiUrl(flat = true) {
  const base = `/api/vaults/${encodeURIComponent(vaultId)}/notes`;
  return flat ? `${base}?flat=true&lang=${encodeURIComponent(uiLang())}` : `${base}?lang=${encodeURIComponent(uiLang())}`;
}

function vaultApiUrl() {
  return `/api/vaults/${encodeURIComponent(vaultId)}?lang=${encodeURIComponent(uiLang())}`;
}

function treeApiUrl() {
  return `/api/vaults/${encodeURIComponent(vaultId)}/tree?lang=${encodeURIComponent(uiLang())}`;
}

async function reloadVaultTreeAndNotes(vaultProgress) {
  if (vaultProgress) vaultProgress.update({ percent: 82, label: "Refreshing folders…", detail: "" });
  const treeData = await fetchJson(treeApiUrl());
  const treeEl = document.getElementById("folder-tree");
  treeEl.innerHTML = `<div class="tree-item active" data-folder=""><span class="tree-icon">∞</span><span class="tree-label">${typeof VaultI18n !== "undefined" ? VaultI18n.t("allNotes") : "(all notes)"}</span></div>` + renderTree(treeData.tree || []);
  bindTree(treeEl);
  if (vaultProgress) vaultProgress.update({ percent: 92, label: "Refreshing notes…", detail: "" });
  const notesData = await fetchJson(notesApiUrl());
  allNotes = notesData.notes;
  renderNoteList();
}

async function runTopicSync(vaultProgress, auto = false) {
  const flat = vaultProgress?._flatTopics;
  const detail = flat ? `${flat} legacy topics` : "";
  if (vaultProgress) {
    vaultProgress.update({
      percent: 55,
      label: auto ? "Organizing themes & subtopics…" : "Syncing topics…",
      detail,
    });
  }
  const r = await fetchJson(`/api/vaults/${encodeURIComponent(vaultId)}/sync-topics`, { method: "POST" });
  await reloadVaultTreeAndNotes(vaultProgress);
  const folders = r.hierarchy?.theme_folders ?? 0;
  const msg = r.migrated
    ? `Organized ${r.synced} subtopics into ${folders} theme folders`
    : `Synced ${r.synced} topics`;
  showToast(msg);
  if (document.querySelector('.pane-tab[data-tab="graph"].active')) {
    VaultGraph.reloadFromUi(vaultId);
  }
  return r;
}

async function init() {
  if (!vaultId) {
    window.location.href = "/";
    return;
  }

  const langSel = document.getElementById("ui-lang");
  if (langSel && typeof VaultI18n !== "undefined") {
    langSel.value = VaultI18n.lang;
    langSel.addEventListener("change", async () => {
      VaultI18n.setLang(langSel.value);
      VaultI18n.applyStaticLabels();
      try {
        const vault = await fetchJson(vaultApiUrl());
        document.getElementById("vault-title").textContent = vault.name;
        const descEl = document.getElementById("vault-description");
        if (descEl) {
          descEl.textContent = vault.description || "";
          descEl.hidden = !vault.description;
        }
      } catch { /* ignore */ }
      renderNoteList();
      await reloadVaultTreeAndNotes(null).catch(() => {});
      if (activeNotePath && !editing) openNote(activeNotePath);
      if (document.querySelector('.pane-tab[data-tab="graph"].active') && window.vaultId) {
        VaultGraph.reloadFromUi(window.vaultId);
      }
    });
    VaultI18n.applyStaticLabels();
  }

  if (typeof VaultGraph !== "undefined") VaultGraph.bindTabs();

  window.activeFolder = null;
  window.activeNotePath = activeNotePath;
  const loadingBar = document.getElementById("explorer-loading");
  loadingBar.hidden = false;
  const vaultProgress = ProgressUI.mount(loadingBar);
  vaultProgress.indeterminate("Loading vault…");

  try {
    vaultProgress.update({ percent: 15, label: "Vault metadata…", detail: "" });
    const vault = await fetchJson(vaultApiUrl());
    document.getElementById("vault-title").textContent = vault.name;
    const descEl = document.getElementById("vault-description");
    if (descEl) {
      descEl.textContent = vault.description || "";
      descEl.hidden = !vault.description;
    }
    const coverEl = document.getElementById("vault-cover");
    if (coverEl) {
      coverEl.src = `/api/vaults/${encodeURIComponent(vaultId)}/cover`;
      coverEl.hidden = false;
      coverEl.onerror = () => { coverEl.hidden = true; };
    }

    if (vault.stats?.hierarchy?.needs_migration) {
      vaultProgress._flatTopics = vault.stats.hierarchy.flat_topics;
      loadingBar.hidden = false;
      await runTopicSync(vaultProgress, true);
    }

    vaultProgress.update({ percent: 35, label: "Folder tree…", detail: "" });
    const treeData = await fetchJson(treeApiUrl());
    const treeEl = document.getElementById("folder-tree");
    treeEl.innerHTML = `<div class="tree-item active" data-folder=""><span class="tree-icon">∞</span><span class="tree-label">${typeof VaultI18n !== "undefined" ? VaultI18n.t("allNotes") : "(all notes)"}</span></div>` + renderTree(treeData.tree || []);
    bindTree(treeEl);

    vaultProgress.update({ percent: 70, label: "Note index…", detail: "" });
    const notesData = await fetchJson(notesApiUrl());
    allNotes = notesData.notes;
    document.getElementById("note-search").addEventListener("input", renderNoteList);
    renderNoteList();

    vaultProgress.done("Vault ready");
    setTimeout(() => { loadingBar.hidden = true; }, 400);

    document.getElementById("btn-sync-topics")?.addEventListener("click", async () => {
      const btn = document.getElementById("btn-sync-topics");
      btn.disabled = true;
      loadingBar.hidden = false;
      const syncProgress = ProgressUI.mount(loadingBar);
      try {
        await runTopicSync(syncProgress, false);
        if (activeNotePath?.startsWith("Topics/")) openNote(activeNotePath);
      } catch (err) {
        showToast(err.message, true);
      } finally {
        btn.disabled = false;
        syncProgress.done("Done");
        setTimeout(() => { loadingBar.hidden = true; }, 400);
      }
    });
    window.onVaultEdited = async (vault) => {
      const v = vault || await fetchJson(vaultApiUrl());
      document.getElementById("vault-title").textContent = v.name;
      const descEl = document.getElementById("vault-description");
      if (descEl) {
        descEl.textContent = v.description || "";
        descEl.hidden = !v.description;
      }
      const coverEl = document.getElementById("vault-cover");
      if (coverEl) {
        coverEl.src = `/api/vaults/${encodeURIComponent(vaultId)}/cover?t=${Date.now()}`;
        coverEl.hidden = false;
      }
    };

    const indexNote = allNotes.find((n) => n.path.includes("00 - Index"));
    const paramNote = params.get("note");
    if (paramNote) {
      openNote(paramNote);
    } else if (indexNote) {
      openNote(indexNote.path);
    }
  } catch (err) {
    vaultProgress.fail(`Error: ${err.message}`);
    document.getElementById("note-content").innerHTML = `<p>Error: ${escapeHtml(err.message)}</p>`;
  }
}

init();
window.openNote = openNote;
