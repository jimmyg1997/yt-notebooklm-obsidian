/**
 * Reusable progress bars for dashboard UI (ingest, explorer loading, note fetch).
 */
const ProgressUI = {
  STEP_LABELS: {
    queued: "Queued",
    create_vault: "Creating vault",
    transcript: "Transcript",
    enrichment: "Enrichment",
    vault_profile: "Vault profile",
    screenshots: "Screenshots",
    vault: "Writing note",
    complete: "Complete",
  },

  /**
   * @param {HTMLElement} container
   * @returns {{ update: Function, done: Function, fail: Function, indeterminate: Function }}
   */
  mount(container) {
    container.innerHTML = `
      <div class="progress-label"></div>
      <div class="progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="100">
        <div class="progress-fill"></div>
      </div>
      <div class="progress-steps"></div>
      <div class="progress-detail"></div>
    `;
    const label = container.querySelector(".progress-label");
    const fill = container.querySelector(".progress-fill");
    const track = container.querySelector(".progress-track");
    const stepsEl = container.querySelector(".progress-steps");
    const detail = container.querySelector(".progress-detail");

    return {
      update({ percent = 0, label: text = "", steps = [], stepIndex = 0, detail: sub = "" } = {}) {
        const pct = Math.max(0, Math.min(100, percent));
        fill.style.width = `${pct}%`;
        track.setAttribute("aria-valuenow", String(pct));
        fill.classList.remove("indeterminate");
        label.textContent = text;
        detail.textContent = sub;
        if (steps.length) {
          stepsEl.innerHTML = steps.map((s, i) => {
            const cls = i < stepIndex ? "done" : i === stepIndex ? "active" : "";
            const name = ProgressUI.STEP_LABELS[s] || s;
            return `<span class="progress-step ${cls}">${name}</span>`;
          }).join("");
        }
      },
      indeterminate(text = "Loading…") {
        fill.style.width = "40%";
        fill.classList.add("indeterminate");
        label.textContent = text;
        detail.textContent = "";
      },
      done(text = "Done") {
        fill.style.width = "100%";
        fill.classList.remove("indeterminate");
        label.textContent = text;
        track.setAttribute("aria-valuenow", "100");
      },
      fail(text = "Failed") {
        fill.classList.remove("indeterminate");
        container.classList.add("progress-error");
        label.textContent = text;
      },
    };
  },

  fromIngestJob(job) {
    const mode = job.vault_mode || "existing";
    const stepsByMode = {
      existing: ["transcript", "enrichment", "screenshots", "vault"],
      manual: ["create_vault", "transcript", "enrichment", "screenshots", "vault"],
      auto: ["transcript", "enrichment", "vault_profile", "screenshots", "vault"],
    };
    const steps = stepsByMode[mode] || stepsByMode.existing;
    const step = job.step || job.status;
    let stepIndex = steps.indexOf(step);
    if (step === "complete") stepIndex = steps.length;
    if (stepIndex < 0) stepIndex = 0;
    const percent = job.progress_percent ?? 0;
    const label = job.progress_label || ProgressUI.STEP_LABELS[step] || step;
    return { percent, label, steps, stepIndex, detail: job.progress_detail || "" };
  },
};
