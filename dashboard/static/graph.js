/** Obsidian-style local graph — scoped modes, hierarchical overview, focused ego view. */
/** @global — exposed on window for explorer.js and E2E tests */
window.VaultGraph = {
  network: null,
  _nodes: null,
  _edges: null,
  _loadedKey: null,
  _physicsOn: false,
  _centerId: null,
  scope: "auto",
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
    VaultGraph._centerId = null;
  },

  setScope(scope, focus = "") {
    VaultGraph.scope = scope || "auto";
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

  /** Pick scope/focus from current note or folder (Obsidian local-graph behaviour). */
  resolveAutoScope() {
    const notePath = window.activeNotePath || "";
    const folder = window.activeFolder || "";
    if (notePath.startsWith("00 -")) {
      return { scope: "overview", focus: "" };
    }
    const noteInFolder = !folder || notePath.startsWith(`${folder}/`) || notePath === `${folder}.md`;
    if (notePath && noteInFolder) {
      return { scope: "focus", focus: notePath };
    }
    if (folder.startsWith("Topics/")) {
      const parts = folder.split("/").filter(Boolean);
      if (parts.length >= 2) {
        return { scope: "focus", focus: `${parts[0]}/${parts[1]}.md` };
      }
    }
    if (notePath) {
      return { scope: "focus", focus: notePath };
    }
    return { scope: "overview", focus: "" };
  },

  _resolveManualScope(scope) {
    const notePath = window.activeNotePath || "";
    const folder = window.activeFolder || "";
    if (scope === "theme") {
      if (folder.startsWith("Topics/")) {
        const parts = folder.split("/").filter(Boolean);
        if (parts.length >= 2) return `${parts[0]}/${parts[1]}.md`;
      }
      if (notePath.startsWith("Topics/")) {
        const parts = notePath.replace(/\.md$/, "").split("/").filter(Boolean);
        if (parts.length >= 2) return `${parts[0]}/${parts[1]}.md`;
      }
    }
    if (scope === "subtopic" || scope === "focus") {
      if (notePath) return notePath;
      if (folder.startsWith("Topics/")) {
        const parts = folder.split("/").filter(Boolean);
        if (parts.length >= 3) return `${parts.slice(0, 3).join("/")}.md`;
        if (parts.length >= 2) return `${parts[0]}/${parts[1]}.md`;
      }
    }
    return "";
  },

  reloadFromUi(vaultId) {
    const sel = document.getElementById("graph-scope");
    let scope = sel?.value || "auto";
    let focus = "";
    if (scope === "auto") {
      const auto = VaultGraph.resolveAutoScope();
      scope = auto.scope;
      focus = auto.focus;
    } else if (scope === "overview" || scope === "index" || scope === "full") {
      focus = "";
    } else {
      focus = VaultGraph._resolveManualScope(scope);
    }
    VaultGraph.load(vaultId, { scope, focus });
  },

  _layoutOptions(layout, nodeCount, scope) {
    if (layout === "hierarchical") {
      return {
        layout: {
          hierarchical: {
            enabled: true,
            direction: "UD",
            sortMethod: "directed",
            levelSeparation: nodeCount > 80 ? 140 : 180,
            nodeSpacing: nodeCount > 80 ? 90 : 130,
            treeSpacing: 220,
            blockShifting: true,
            edgeMinimization: true,
          },
        },
        physics: { enabled: false },
      };
    }
    if (layout === "focus") {
      return {
        physics: {
          enabled: true,
          stabilization: { iterations: 120, fit: true },
          forceAtlas2Based: {
            gravitationalConstant: -65,
            centralGravity: 0.015,
            springLength: 160,
            springConstant: 0.08,
            damping: 0.5,
            avoidOverlap: 1,
          },
        },
      };
    }
    const heavy = nodeCount > 100 || scope === "full";
    return {
      physics: {
        enabled: true,
        stabilization: { iterations: heavy ? 60 : 100, fit: true },
        barnesHut: {
          gravitationalConstant: heavy ? -12000 : -20000,
          centralGravity: heavy ? 0.2 : 0.35,
          springLength: heavy ? 200 : 170,
          springConstant: 0.04,
          damping: 0.12,
          avoidOverlap: 0.35,
        },
      },
    };
  },

  async load(vaultId, opts = {}) {
    const container = document.getElementById("graph-canvas");
    const statsEl = document.getElementById("graph-stats");
    if (!container) return;

    const scope = opts.scope || VaultGraph.scope || "auto";
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

      const displayScope = scope === "focus" && focus
        ? (typeof VaultI18n !== "undefined" ? VaultI18n.t("graphFocusLabel") : "focus")
        : scope;
      if (statsEl) {
        if (typeof VaultI18n !== "undefined") {
          statsEl.textContent = VaultI18n.t("graphStats", data.stats?.nodes ?? 0, data.stats?.edges ?? 0, displayScope);
        } else {
          statsEl.textContent = `${data.stats?.nodes ?? 0} notes · ${data.stats?.edges ?? 0} links · ${displayScope}`;
        }
      }

      if (!data.nodes?.length) {
        container.innerHTML = "<p class='loading'>No nodes for this scope. Select a note or topic, or try Overview.</p>";
        return;
      }

      const layout = data.layout || (scope === "overview" || scope === "index" ? "hierarchical" : "force");
      VaultGraph._centerId = data.center_id || focus || null;
      const nodeCount = data.nodes.length;
      const hideVideoLabels = layout === "hierarchical" && nodeCount > 25;

      const groupColors = {
        meta: { background: "#e8dfd0", border: "#c8a96e", highlight: { background: "#f5ecd8", border: "#c8a96e" } },
        video: { background: "#f0e6d8", border: "#c8a96e", highlight: { background: "#faf3e8", border: "#c8a96e" } },
        theme: { background: "#d4e4f7", border: "#4a7ab8", highlight: { background: "#e8f2fc", border: "#4a7ab8" } },
        subtopic: { background: "#e3efe5", border: "#6b8f71", highlight: { background: "#f0f7f1", border: "#6b8f71" } },
        topic: { background: "#e3efe5", border: "#6b8f71", highlight: { background: "#f0f7f1", border: "#6b8f71" } },
        root: { background: "#e8e8e4", border: "#b0a898", highlight: { background: "#f5f5f2", border: "#b0a898" } },
      };

      const sizeFor = (grp, isCenter) => {
        if (isCenter) return 28;
        return ({ meta: 16, video: 10, theme: 22, subtopic: 14, topic: 12, root: 8 }[grp] || 8);
      };

      VaultGraph._nodes = new visLib.DataSet(
        data.nodes.map((n) => {
          const grp = n.group || "root";
          const isCenter = VaultGraph._centerId && n.id === VaultGraph._centerId;
          const colors = groupColors[grp] || groupColors.root;
          const showLabel = isCenter || grp === "theme" || grp === "meta" || (!hideVideoLabels && grp !== "video");
          const raw = n.label || "";
          const label = showLabel ? (raw.length > 28 ? raw.slice(0, 26) + "…" : raw) : "";
          return {
            id: n.id,
            label,
            title: raw,
            group: grp,
            level: n.level,
            color: isCenter
              ? { background: "#fff8e7", border: "#c8a96e", highlight: { background: "#fff8e7", border: "#a8864a" } }
              : colors,
            font: {
              color: "#2d2a26",
              size: isCenter ? 14 : (grp === "theme" ? 12 : 10),
              bold: isCenter || grp === "meta" || grp === "theme",
            },
            size: sizeFor(grp, isCenter),
            borderWidth: isCenter ? 4 : 2,
            fixed: isCenter && layout === "focus" ? { x: true, y: true } : false,
          };
        })
      );

      VaultGraph._edges = new visLib.DataSet(
        data.edges.map((e, i) => ({
          id: i,
          from: e.source,
          to: e.target,
          arrows: { to: { enabled: true, scaleFactor: e.kind === "hierarchy" ? 0.5 : 0.35 } },
          color: {
            color: e.kind === "hierarchy" ? "#7a9fc8" : "#ddd8ce",
            opacity: e.kind === "hierarchy" ? 0.75 : 0.45,
            highlight: "#c8a96e",
          },
          width: e.kind === "hierarchy" ? 1.8 : 0.8,
          dashes: e.kind === "hierarchy",
          smooth: layout === "hierarchical"
            ? { type: "cubicBezier", forceDirection: "vertical", roundness: 0.35 }
            : false,
        }))
      );

      container.innerHTML = "";
      const layoutOpts = VaultGraph._layoutOptions(layout, nodeCount, scope);
      const options = {
        ...layoutOpts,
        interaction: {
          hover: true,
          dragNodes: true,
          dragView: true,
          zoomView: true,
          tooltipDelay: 120,
        },
        nodes: { shape: "dot" },
        edges: { selectionWidth: 2 },
      };

      VaultGraph._physicsOn = !!options.physics?.enabled;
      VaultGraph.network = new visLib.Network(container, { nodes: VaultGraph._nodes, edges: VaultGraph._edges }, options);

      const finishLayout = () => {
        if (!VaultGraph.network) return;
        if (VaultGraph._centerId && VaultGraph._nodes.get(VaultGraph._centerId)) {
          VaultGraph.network.selectNodes([VaultGraph._centerId]);
          VaultGraph.network.focus(VaultGraph._centerId, {
            scale: layout === "focus" ? 1.35 : 1.0,
            animation: { duration: 450, easingFunction: "easeInOutQuad" },
          });
        } else {
          VaultGraph.network.fit({ animation: { duration: 350, easingFunction: "easeInOutQuad" } });
        }
        if (layout === "focus") {
          VaultGraph.network.once("afterDrawing", () => {
            if (VaultGraph._centerId) {
              VaultGraph.network.moveTo({
                position: VaultGraph.network.getPositions([VaultGraph._centerId])[VaultGraph._centerId],
                scale: 1.35,
                animation: false,
              });
            }
          });
        }
      };

      if (VaultGraph._physicsOn) {
        VaultGraph.network.once("stabilizationIterationsDone", () => {
          VaultGraph.network.setOptions({ physics: { enabled: false } });
          VaultGraph._physicsOn = false;
          finishLayout();
        });
      } else {
        setTimeout(finishLayout, 120);
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
    if (fit) fit.onclick = () => {
      if (VaultGraph._centerId && VaultGraph._nodes?.get(VaultGraph._centerId)) {
        VaultGraph.network.focus(VaultGraph._centerId, { scale: 1.2, animation: true });
      } else {
        VaultGraph.network.fit({ animation: true });
      }
    };
    if (physics) physics.onclick = () => {
      VaultGraph._physicsOn = !VaultGraph._physicsOn;
      VaultGraph.network.setOptions({ physics: { enabled: VaultGraph._physicsOn } });
      physics.textContent = typeof VaultI18n !== "undefined"
        ? VaultI18n.t(VaultGraph._physicsOn ? "freezeLayout" : "unfreezeLayout")
        : (VaultGraph._physicsOn ? "Freeze" : "Unfreeze");
    };
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
