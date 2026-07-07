/** Obsidian-style local graph — scoped modes for performance. */
/** @global — exposed on window for explorer.js and E2E tests */
window.VaultGraph = {
  network: null,
  _nodes: null,
  _edges: null,
  _loadedKey: null,
  _physicsOn: false,
  scope: "overview",
  focus: "",
  activeTab: "note",

  destroy() {
    if (VaultGraph.network) {
      VaultGraph.network.destroy();
      VaultGraph.network = null;
    }
    VaultGraph._nodes = null;
    VaultGraph._edges = null;
    VaultGraph._loadedKey = null;
  },

  setScope(scope, focus = "") {
    VaultGraph.scope = scope || "overview";
    VaultGraph.focus = focus || "";
  },

  _visLib() {
    if (typeof vis !== "undefined" && vis.Network && vis.DataSet) return vis;
    if (typeof window !== "undefined" && window.vis?.Network) return window.vis;
    return null;
  },

  switchTab(tabName) {
    const tab = tabName === "graph" ? "graph" : "note";
    VaultGraph.activeTab = tab;
    document.querySelectorAll(".pane-tab").forEach((el) => {
      el.classList.toggle("active", el.dataset.tab === tab);
    });
    const notePanel = document.getElementById("note-panel");
    const graphPanel = document.getElementById("graph-panel");
    if (notePanel) {
      notePanel.hidden = tab === "graph";
      notePanel.classList.toggle("is-active", tab === "note");
    }
    if (graphPanel) {
      graphPanel.hidden = tab !== "graph";
      graphPanel.classList.toggle("is-active", tab === "graph");
    }
    const titleBar = document.getElementById("note-title-bar");
    if (titleBar) titleBar.hidden = tab === "graph";
    if (tab === "graph" && window.vaultId) {
      VaultGraph._scheduleLoad(window.vaultId);
    }
  },

  _scheduleLoad(vaultId) {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => VaultGraph.reloadFromUi(vaultId));
    });
  },

  _cacheKey(vaultId) {
    return `${vaultId}|${VaultGraph.scope}|${VaultGraph.focus}`;
  },

  async load(vaultId, opts = {}) {
    const container = document.getElementById("graph-canvas");
    const statsEl = document.getElementById("graph-stats");
    if (!container) return;

    const scope = opts.scope || VaultGraph.scope || "overview";
    const focus = opts.focus ?? VaultGraph.focus ?? "";
    const cacheKey = `${vaultId}|${scope}|${focus}`;
    if (VaultGraph._loadedKey && VaultGraph._loadedKey !== cacheKey) {
      VaultGraph.destroy();
    }
    VaultGraph._loadedKey = cacheKey;
    VaultGraph.scope = scope;
    VaultGraph.focus = focus;

    const visLib = VaultGraph._visLib();
    if (!visLib) {
      container.innerHTML = "<p class='loading'>Graph library failed to load. Check your network connection and refresh.</p>";
      return;
    }

    const building = typeof VaultI18n !== "undefined" ? VaultI18n.t("graphBuilding") : "Building graph…";
    container.innerHTML = `<p class='loading'>${building}</p>`;

    try {
      const qs = new URLSearchParams({ scope, focus });
      const res = await fetch(`/api/vaults/${encodeURIComponent(vaultId)}/graph?${qs}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();

      if (statsEl) {
        const scopeLabel = scope;
        if (typeof VaultI18n !== "undefined") {
          statsEl.textContent = VaultI18n.t("graphStats", data.stats?.nodes ?? 0, data.stats?.edges ?? 0, scopeLabel);
        } else {
          statsEl.textContent = `${data.stats?.nodes ?? 0} notes · ${data.stats?.edges ?? 0} links · ${scopeLabel}`;
        }
      }

      if (!data.nodes?.length) {
        container.innerHTML = "<p class='loading'>No nodes for this scope. Try another scope or open a theme/subtopic note first.</p>";
        return;
      }

      const groupColors = {
        meta: { background: "#e8dfd0", border: "#c8a96e" },
        video: { background: "#f0e6d8", border: "#c8a96e" },
        theme: { background: "#d4e4f7", border: "#4a7ab8" },
        subtopic: { background: "#e3efe5", border: "#6b8f71" },
        topic: { background: "#e3efe5", border: "#6b8f71" },
        root: { background: "#e8e8e4", border: "#b0a898" },
      };

      const heavy = data.nodes.length > 120;
      const sizeFor = (grp) => ({ meta: 12, video: 18, theme: 24, subtopic: 10, topic: 10, root: 8 }[grp] || 8);

      VaultGraph._nodes = new visLib.DataSet(
        data.nodes.map((n) => {
          const grp = n.group || "root";
          const colors = groupColors[grp] || groupColors.root;
          const label = n.label.length > 24 ? n.label.slice(0, 22) + "…" : n.label;
          return {
            id: n.id,
            label,
            title: n.label,
            group: grp,
            color: colors,
            font: { color: "#2d2a26", size: grp === "theme" ? 13 : 11 },
            size: sizeFor(grp),
          };
        })
      );

      VaultGraph._edges = new visLib.DataSet(
        data.edges.map((e, i) => ({
          id: i,
          from: e.source,
          to: e.target,
          arrows: { to: { enabled: true, scaleFactor: e.kind === "hierarchy" ? 0.6 : 0.4 } },
          color: {
            color: e.kind === "hierarchy" ? "#4a7ab8" : "#ddd8ce",
            opacity: e.kind === "hierarchy" ? 0.85 : 0.5,
          },
          width: e.kind === "hierarchy" ? 2 : 0.6,
          dashes: e.kind === "hierarchy",
        }))
      );

      container.innerHTML = "";
      const options = {
        physics: {
          enabled: !heavy,
          stabilization: { iterations: heavy ? 80 : 150, fit: true },
          barnesHut: {
            gravitationalConstant: heavy ? -8000 : -18000,
            springLength: heavy ? 120 : 160,
            damping: 0.15,
          },
        },
        interaction: { hover: true, dragNodes: true, dragView: true, zoomView: true },
        nodes: { shape: "dot", borderWidth: 2 },
        edges: { smooth: heavy ? false : { type: "dynamic", roundness: 0.15 } },
      };

      VaultGraph._physicsOn = !heavy;
      VaultGraph.network = new visLib.Network(container, { nodes: VaultGraph._nodes, edges: VaultGraph._edges }, options);
      if (!heavy) {
        VaultGraph.network.once("stabilizationIterationsDone", () => {
          VaultGraph.network.setOptions({ physics: { enabled: false } });
          VaultGraph._physicsOn = false;
        });
      }

      VaultGraph.network.on("click", (params) => {
        if (!params.nodes.length) return;
        const path = params.nodes[0];
        if (typeof window.openNote === "function") {
          VaultGraph.switchTab("note");
          window.openNote(path);
        }
      });

      VaultGraph._bindToolbar();
      setTimeout(() => {
        if (!VaultGraph.network) return;
        VaultGraph.network.redraw();
        VaultGraph.network.fit({ animation: false });
      }, 80);
    } catch (err) {
      container.innerHTML = `<p class="loading">Graph error: ${String(err.message || err)}</p>`;
    }
  },

  _bindToolbar() {
    const zoomIn = document.getElementById("graph-zoom-in");
    const zoomOut = document.getElementById("graph-zoom-out");
    const fit = document.getElementById("graph-fit");
    const physics = document.getElementById("graph-physics");
    if (!VaultGraph.network) return;
    if (zoomIn) zoomIn.onclick = () => VaultGraph.network.moveTo({ scale: VaultGraph.network.getScale() * 1.25 });
    if (zoomOut) zoomOut.onclick = () => VaultGraph.network.moveTo({ scale: VaultGraph.network.getScale() / 1.25 });
    if (fit) fit.onclick = () => VaultGraph.network.fit({ animation: true });
    if (physics) physics.onclick = () => {
      VaultGraph._physicsOn = !VaultGraph._physicsOn;
      VaultGraph.network.setOptions({ physics: { enabled: VaultGraph._physicsOn } });
      physics.textContent = typeof VaultI18n !== "undefined"
        ? VaultI18n.t(VaultGraph._physicsOn ? "freezeLayout" : "unfreezeLayout")
        : (VaultGraph._physicsOn ? "Freeze" : "Unfreeze");
    };
  },

  _resolveFocus(scope) {
    const folder = window.activeFolder || "";
    const notePath = window.activeNotePath || "";
    if (scope === "theme") {
      if (folder.startsWith("Topics/")) {
        const parts = folder.split("/").filter(Boolean);
        if (parts.length >= 2) return `${parts[0]}/${parts[1]}`;
        return folder;
      }
      if (notePath.startsWith("Topics/")) {
        const parts = notePath.replace(/\.md$/, "").split("/").filter(Boolean);
        if (parts.length >= 2) return `${parts[0]}/${parts[1]}`;
      }
    }
    if (scope === "subtopic") {
      if (notePath.startsWith("Topics/") && notePath.endsWith(".md")) return notePath;
      if (folder.startsWith("Topics/")) {
        const parts = folder.split("/").filter(Boolean);
        if (parts.length >= 3) {
          const guess = `${parts.slice(0, 3).join("/")}.md`;
          return guess;
        }
      }
    }
    return "";
  },

  reloadFromUi(vaultId) {
    const sel = document.getElementById("graph-scope");
    const scope = sel?.value || "overview";
    const focus = scope === "overview" || scope === "full" ? "" : VaultGraph._resolveFocus(scope);
    VaultGraph.load(vaultId, { scope, focus });
  },
};

/** Bind Note/Graph tab switching — event delegation survives i18n relabels. */
VaultGraph.bindTabs = function bindTabs() {
  if (VaultGraph._tabsBound) return;
  VaultGraph._tabsBound = true;

  document.addEventListener("click", (e) => {
    const tab = e.target.closest?.(".pane-tab[data-tab]");
    if (!tab) return;
    e.preventDefault();
    VaultGraph.switchTab(tab.dataset.tab);
  });

  document.getElementById("graph-scope")?.addEventListener("change", () => {
    if (VaultGraph.activeTab === "graph" && window.vaultId) {
      VaultGraph.reloadFromUi(window.vaultId);
    }
  });

  VaultGraph.switchTab("note");
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => VaultGraph.bindTabs());
} else {
  VaultGraph.bindTabs();
}
