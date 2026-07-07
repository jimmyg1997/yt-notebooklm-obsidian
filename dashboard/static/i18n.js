/** UI strings — Greek (default) / English. Persisted in localStorage. */
const VaultI18n = {
  lang: localStorage.getItem("vault-ui-lang") || "el",

  strings: {
    el: {
      allVaults: "← Όλα τα vaults",
      folders: "Φάκελοι",
      allNotes: "(όλες οι σημειώσεις)",
      notes: "Σημειώσεις",
      filterNotes: "Φίλτρο σημειώσεις…",
      noteTab: "Σημείωση",
      graphTab: "Γράφος",
      selectNote: "Επίλεξε σημείωση",
      syncTopics: "Sync topics",
      editVault: "Επεξεργασία vault",
      editNote: "Επεξεργασία",
      deleteNote: "Διαγραφή",
      graphOverview: "Επισκόπηση (γρήγορο)",
      graphTheme: "Θεματική τώρα",
      graphSubtopic: "Υποθέμα τώρα",
      graphFull: "Πλήρης (βαρύ)",
      graphBuilding: "Φόρτωση γράφου…",
      graphStats: (n, e, scope) => `${n} κόμβοι · ${e} σύνδεσμοι · ${scope}`,
      freezeLayout: "Πάγωμα διάταξης",
      unfreezeLayout: "Ξεπάγωμα",
      langLabel: "Γλώσσα",
      topicsRoot: "Topics",
      video: "Video",
      theme: "Θεματική",
      subtopic: "Υποθέμα",
      meta: "Index",
      note: "Σημείωση",
      groupVideos: "📹 Βίντεο YouTube",
      groupMeta: "📋 Index & οδηγοί",
      groupThemes: "📂 Θεματικές",
      groupTopics: "📚 Topics",
      loadingVault: "Φόρτωση vault…",
      loadingNote: "Φόρτωση σημείωσης…",
      rendering: "Απόδοση…",
      backlinks: "Αναφορές",
      noNotesInFolder: "Δεν υπάρχουν σημειώσεις σε αυτόν τον φάκελο.",
    },
    en: {
      allVaults: "← All vaults",
      folders: "Folders",
      allNotes: "(all notes)",
      notes: "Notes",
      filterNotes: "Filter notes…",
      noteTab: "Note",
      graphTab: "Graph",
      selectNote: "Select a note",
      syncTopics: "Sync topics",
      editVault: "Edit vault",
      editNote: "Edit",
      deleteNote: "Delete",
      graphOverview: "Overview (fast)",
      graphTheme: "Current theme",
      graphSubtopic: "Current subtopic",
      graphFull: "Full (heavy)",
      graphBuilding: "Building graph…",
      graphStats: (n, e, scope) => `${n} nodes · ${e} links · ${scope}`,
      freezeLayout: "Freeze layout",
      unfreezeLayout: "Unfreeze layout",
      langLabel: "Language",
      topicsRoot: "Topics",
      video: "Video",
      theme: "Theme",
      subtopic: "Subtopic",
      meta: "Index",
      note: "Note",
      groupVideos: "📹 YouTube videos",
      groupMeta: "📋 Index & guides",
      groupThemes: "📂 Themes",
      groupTopics: "📚 Topics",
      loadingVault: "Loading vault…",
      vaultReady: "Έτοιμο",
      loadingNote: "Loading note…",
      rendering: "Rendering…",
      backlinks: "Backlinks",
      noNotesInFolder: "No notes in this folder.",
    },
  },

  t(key, ...args) {
    const pack = VaultI18n.strings[VaultI18n.lang] || VaultI18n.strings.el;
    const val = pack[key];
    if (typeof val === "function") return val(...args);
    return val ?? key;
  },

  setLang(lang) {
    VaultI18n.lang = lang === "en" ? "en" : "el";
    localStorage.setItem("vault-ui-lang", VaultI18n.lang);
    document.documentElement.lang = VaultI18n.lang;
    window.dispatchEvent(new CustomEvent("vault-lang-change"));
  },

  applyStaticLabels(root = document) {
    const map = {
      "#btn-sync-topics": "syncTopics",
      "#btn-edit-vault": "editVault",
      "#btn-edit-note": "editNote",
      "#btn-delete-note": "deleteNote",
      ".pane-tab[data-tab='note']": "noteTab",
      ".pane-tab[data-tab='graph']": "graphTab",
      "#note-search": { placeholder: "filterNotes" },
      "#graph-scope": null,
    };
    Object.entries(map).forEach(([sel, key]) => {
      const el = root.querySelector(sel);
      if (!el || !key) return;
      if (typeof key === "object" && key.placeholder) {
        el.placeholder = VaultI18n.t(key.placeholder);
      } else {
        el.textContent = VaultI18n.t(key);
      }
    });
    const sub = root.querySelector(".subtitle a");
    if (sub) sub.textContent = VaultI18n.t("allVaults");
    root.querySelectorAll(".pane-header").forEach((el, i) => {
      if (i === 0) el.textContent = VaultI18n.t("folders");
      if (i === 1) el.textContent = VaultI18n.t("notes");
    });
    root.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = VaultI18n.t(el.dataset.i18n);
    });
    const scope = root.getElementById?.("graph-scope") || document.getElementById("graph-scope");
    if (scope) {
      [...scope.options].forEach((opt) => {
        const k = opt.dataset.i18n;
        if (k) opt.textContent = VaultI18n.t(k);
      });
    }
  },
};

document.documentElement.lang = VaultI18n.lang;
