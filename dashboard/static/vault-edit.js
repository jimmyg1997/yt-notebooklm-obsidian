/** Shared vault edit modal (home + explorer). */
const VaultEdit = {
  async open(vaultId) {
    const modal = document.getElementById("vault-edit-modal");
    if (!modal) {
      throw new Error("Edit modal not found on this page");
    }
    const res = await fetch(`/api/vaults/${encodeURIComponent(vaultId)}`);
    if (!res.ok) throw new Error(await res.text());
    const v = await res.json();

    modal.dataset.vaultId = vaultId;
    const hiddenId = document.getElementById("edit-vault-id");
    if (hiddenId) hiddenId.value = vaultId;

    const nameEl = document.getElementById("edit-vault-name");
    const descEl = document.getElementById("edit-vault-description");
    const themesEl = document.getElementById("edit-vault-themes");
    if (nameEl) nameEl.value = v.name || "";
    if (descEl) descEl.value = v.description || "";
    if (themesEl) themesEl.value = (v.themes || []).join(", ");

    modal.hidden = false;
    modal.removeAttribute("hidden");
    nameEl?.focus();
  },

  close() {
    const modal = document.getElementById("vault-edit-modal");
    if (modal) {
      modal.hidden = true;
      modal.setAttribute("hidden", "");
      delete modal.dataset.vaultId;
    }
  },

  async save(e) {
    e.preventDefault();
    const modal = document.getElementById("vault-edit-modal");
    const hiddenId = document.getElementById("edit-vault-id");
    const vaultId = modal?.dataset.vaultId || hiddenId?.value;
    if (!vaultId) throw new Error("No vault selected");

    const name = document.getElementById("edit-vault-name")?.value.trim();
    if (!name) throw new Error("Vault name is required");

    const themesRaw = document.getElementById("edit-vault-themes")?.value || "";
    const themes = themesRaw.split(",").map((t) => t.trim()).filter(Boolean);
    const body = {
      name,
      description: document.getElementById("edit-vault-description")?.value.trim() || "",
      themes,
    };

    const saveBtn = modal?.querySelector('button[type="submit"]');
    if (saveBtn) saveBtn.disabled = true;
    try {
      const res = await fetch(`/api/vaults/${encodeURIComponent(vaultId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      VaultEdit.close();
      if (typeof showToast === "function") {
        showToast(`Saved "${data.vault?.name || name}"`);
      }
      if (typeof window.onVaultEdited === "function") window.onVaultEdited(data.vault);
    } finally {
      if (saveBtn) saveBtn.disabled = false;
    }
  },

  bind() {
    if (VaultEdit._bound) return;
    VaultEdit._bound = true;
    const form = document.getElementById("vault-edit-form");
    const cancel = document.getElementById("edit-cancel");
    const modal = document.getElementById("vault-edit-modal");
    form?.addEventListener("submit", (e) =>
      VaultEdit.save(e).catch((err) => {
        if (typeof showToast === "function") showToast(err.message, true);
        else alert(err.message);
      })
    );
    cancel?.addEventListener("click", () => VaultEdit.close());
    modal?.addEventListener("click", (e) => {
      if (e.target === modal) VaultEdit.close();
    });
  },
};

function bootVaultEdit() {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => VaultEdit.bind());
  } else {
    VaultEdit.bind();
  }
}
bootVaultEdit();
