async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });
}

function sourceLabel(type) {
  return { experiment: "Experiment", local: "Local vault", obsidian: "Obsidian path" }[type] || type;
}

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function showToast(msg, isError = false) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.classList.toggle("error", isError);
  el.hidden = false;
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => { el.hidden = true; }, 5000);
}

function canDeleteVault(v) {
  return v.source_type === "experiment" || v.source_type === "local";
}

function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}

function formatVaultStats(v) {
  const s = v.stats || {};
  const parts = [];
  if (s.videos_analyzed) parts.push(plural(s.videos_analyzed, "video analyzed", "videos analyzed"));
  if (s.topics) parts.push(plural(s.topics, "topic", "topics"));
  if (s.meta_notes) parts.push(plural(s.meta_notes, "index note", "index notes"));
  if (!parts.length && v.note_count) parts.push(plural(v.note_count, "note", "notes"));
  return parts.join(" · ");
}

const DeleteConfirm = {
  _vaultId: null,

  bind() {
    const modal = document.getElementById("delete-confirm-modal");
    document.getElementById("delete-cancel")?.addEventListener("click", () => DeleteConfirm.close());
    document.getElementById("delete-confirm")?.addEventListener("click", () => DeleteConfirm.confirm());
    modal?.addEventListener("click", (e) => {
      if (e.target === modal) DeleteConfirm.close();
    });
  },

  open(vaultId, name, statsLine) {
    const modal = document.getElementById("delete-confirm-modal");
    const msg = document.getElementById("delete-confirm-message");
    if (!modal || !msg) return;
    this._vaultId = vaultId;
    msg.innerHTML = `Are you sure you want to delete <strong>${escapeHtml(name)}</strong>?`;
    if (statsLine) {
      msg.innerHTML += `<br><span class="hint">${escapeHtml(statsLine)} will be removed.</span>`;
    }
    modal.hidden = false;
    modal.removeAttribute("hidden");
  },

  close() {
    const modal = document.getElementById("delete-confirm-modal");
    if (modal) {
      modal.hidden = true;
      modal.setAttribute("hidden", "");
    }
    this._vaultId = null;
  },

  async confirm() {
    const vaultId = this._vaultId;
    const btn = document.getElementById("delete-confirm");
    if (!vaultId || !btn) return;
    btn.disabled = true;
    try {
      const res = await fetch(`/api/vaults/${encodeURIComponent(vaultId)}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      DeleteConfirm.close();
      showToast(`Deleted "${data.name || "vault"}"`);
      await loadVaults();
    } catch (err) {
      showToast(err.message, true);
    } finally {
      btn.disabled = false;
    }
  },
};

function getVaultMode() {
  const checked = document.querySelector('input[name="vault-mode"]:checked');
  return checked ? checked.value : "existing";
}

function setupVaultModePanels() {
  const panels = {
    existing: document.getElementById("panel-existing"),
    manual: document.getElementById("panel-manual"),
    auto: document.getElementById("panel-auto"),
  };
  document.querySelectorAll('input[name="vault-mode"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      const mode = getVaultMode();
      Object.entries(panels).forEach(([key, el]) => {
        if (el) el.hidden = key !== mode;
      });
    });
  });
}

async function loadVaults() {
  const loading = document.getElementById("loading");
  const grid = document.getElementById("vault-grid");
  const empty = document.getElementById("empty");
  const vaultSelect = document.getElementById("ingest-vault");
  loading.hidden = false;
  grid.hidden = true;
  empty.hidden = true;
  const vaultProgress = ProgressUI.mount(loading);
  vaultProgress.indeterminate("Discovering vaults…");
  try {
    const data = await fetchJson("/api/vaults");
    loading.hidden = true;
    if (vaultSelect) {
      vaultSelect.innerHTML = '<option value="">Select vault…</option>' +
        data.vaults.map((v) => `<option value="${v.id}">${escapeHtml(v.name)} (${formatVaultStats(v)})</option>`).join("");
    }
    if (!data.vaults.length) {
      empty.hidden = false;
      return;
    }
    grid.hidden = false;
    grid.innerHTML = data.vaults.map((v) => {
      const desc = v.description
        ? `<p class="vault-desc">${escapeHtml(v.description)}</p>`
        : "";
      const themes = (v.themes && v.themes.length)
        ? `<div class="vault-themes">${v.themes.slice(0, 5).map((t) => `<span class="theme-chip">${escapeHtml(t)}</span>`).join("")}</div>`
        : "";
      const coverUrl = `/api/vaults/${encodeURIComponent(v.id)}/cover?t=${Date.now() % 100000}`;
      return `
      <article class="vault-card" data-id="${v.id}">
        <div class="vault-cover"><img src="${coverUrl}" alt="" loading="lazy" onerror="this.parentElement.classList.add('no-cover')" /></div>
        <div class="vault-card-body">
        <span class="badge ${v.source_type}">${sourceLabel(v.source_type)}</span>
        <h2>${escapeHtml(v.name)}</h2>
        ${desc}
        ${themes}
        <div class="meta vault-stats">
          <div class="vault-stats-line">${escapeHtml(formatVaultStats(v))}</div>
          <div>Updated ${formatDate(v.last_modified)}</div>
        </div>
        </div>
        <div class="vault-card-actions">
          <button type="button" class="vault-action-btn" data-action="edit" data-id="${v.id}">Edit</button>
          ${canDeleteVault(v) ? `<button type="button" class="vault-action-btn danger" data-action="delete" data-id="${v.id}" data-name="${escapeHtml(v.name)}">Delete</button>` : ""}
        </div>
      </article>`;
    }).join("");
    grid.querySelectorAll(".vault-card").forEach((card) => {
      card.addEventListener("click", (e) => {
        if (e.target.closest(".vault-card-actions")) return;
        window.location.href = `/explorer?vault=${encodeURIComponent(card.dataset.id)}`;
      });
    });
    grid.querySelectorAll("[data-action='edit']").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        VaultEdit.open(btn.dataset.id).catch((err) => showToast(err.message, true));
      });
    });
    grid.querySelectorAll("[data-action='delete']").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const card = btn.closest(".vault-card");
        const vaultId = btn.dataset.id;
        const name = btn.dataset.name || "this vault";
        const statsLine = card?.querySelector(".vault-stats-line")?.textContent || "";
        DeleteConfirm.open(vaultId, name, statsLine);
      });
    });
  } catch (err) {
    loading.hidden = false;
    vaultProgress.fail(`Error: ${err.message}`);
  }
}

function setupIngestForm() {
  const form = document.getElementById("ingest-form");
  const statusEl = document.getElementById("ingest-status");
  const submitBtn = document.getElementById("ingest-submit");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const url = document.getElementById("ingest-url").value.trim();
    const mode = getVaultMode();
    if (!url) return;

    const payload = { url, vault_mode: mode };
    if (mode === "existing") {
      const vaultId = document.getElementById("ingest-vault").value;
      if (!vaultId) return;
      payload.vault_id = vaultId;
    } else if (mode === "manual") {
      const name = document.getElementById("vault-name").value.trim();
      const description = document.getElementById("vault-description").value.trim();
      if (!name) {
        statusEl.hidden = false;
        statusEl.className = "ingest-status progress-panel error";
        statusEl.textContent = "Please enter a vault name.";
        return;
      }
      payload.vault_name = name;
      payload.vault_description = description;
    }

    submitBtn.disabled = true;
    statusEl.hidden = false;
    statusEl.className = "ingest-status progress-panel";
    const ingestProgress = ProgressUI.mount(statusEl);
    ingestProgress.update({ percent: 0, label: "Starting ingest…", detail: "" });

    try {
      const res = await fetch("/api/ingest/single-video", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      const { job_id } = await res.json();
      await pollIngestJob(job_id, statusEl, ingestProgress);
      await loadVaults();
    } catch (err) {
      statusEl.className = "ingest-status progress-panel progress-error";
      ingestProgress.fail(`Failed: ${err.message}`);
    } finally {
      submitBtn.disabled = false;
    }
  });
}

async function pollIngestJob(jobId, statusEl, progress) {
  for (let i = 0; i < 600; i++) {
    const job = await fetchJson(`/api/ingest/jobs/${encodeURIComponent(jobId)}`);
    const ui = ProgressUI.fromIngestJob(job);
    progress.update(ui);

    if (job.status === "done") {
      statusEl.className = "ingest-status progress-panel done";
      progress.done("Complete");
      const r = job.result || {};
      const vaultId = r.vault_id || job.vault_id;
      const created = r.vault_created;
      const createdNote = r.created !== false;
      const action = createdNote ? "saved" : "updated";
      const vaultLine = created
        ? ` New vault <strong>${escapeHtml(created.name)}</strong> created.`
        : "";
      const link = r.path && vaultId
        ? ` <a href="/explorer?vault=${encodeURIComponent(vaultId)}&note=${encodeURIComponent(r.path)}">Open note</a>`
        : vaultId
          ? ` <a href="/explorer?vault=${encodeURIComponent(vaultId)}">Open vault</a>`
          : "";
      const detailEl = statusEl.querySelector(".progress-detail");
      if (detailEl) {
        detailEl.innerHTML = `✅ <strong>${escapeHtml(r.title || "Video")}</strong> ${action} (${r.screenshots ?? 0} screenshots).${vaultLine}${link}`;
      }
      return;
    }
    if (job.status === "failed") {
      statusEl.className = "ingest-status progress-panel progress-error";
      throw new Error(job.error || "Ingest failed");
    }
    await new Promise((r) => setTimeout(r, 1500));
  }
  throw new Error("Timed out waiting for ingest");
}

setupVaultModePanels();
DeleteConfirm.bind();
if (typeof VaultEdit !== "undefined") VaultEdit.bind();
window.onVaultEdited = () => loadVaults();

(function initUiLang() {
  const langSel = document.getElementById("ui-lang");
  if (!langSel || typeof VaultI18n === "undefined") return;
  langSel.value = VaultI18n.lang;
  langSel.addEventListener("change", () => {
    VaultI18n.setLang(langSel.value);
    VaultI18n.applyStaticLabels();
  });
  VaultI18n.applyStaticLabels();
})();

loadVaults();
setupIngestForm();
