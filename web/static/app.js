const state = {
  view: "prompt",
  prompt: null,
  versions: [],
  draft: "",
  saved: "",
  viewingVersion: null,
  runs: [],
  selectedRun: null,
  detail: null,
  compare: null,
  evalStatus: { status: "idle" },
};

let pollTimer = null;

function $(id) {
  return document.getElementById(id);
}

async function api(path, options = {}) {
  const { headers, ...rest } = options;
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(headers || {}) },
    ...rest,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      detail = await response.text();
    }
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

function pct(value) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function money(value) {
  if (value == null) return "—";
  return `$${Number(value).toFixed(4)}`;
}

function shortHash(hash) {
  return hash ? hash.slice(0, 12) : "—";
}

function deltaText(value) {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(1)} pp`;
}

function deltaClass(value) {
  if (value == null || value === 0) return "";
  return value > 0 ? "delta-up" : "delta-down";
}

function unsaved() {
  return state.draft !== state.saved;
}

function setView(view) {
  state.view = view;
  $("view-prompt").hidden = view !== "prompt";
  $("view-runs").hidden = view !== "runs";
  document.querySelectorAll(".folio-tab").forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.view === view);
  });
}

function renderMasthead() {
  const version = state.prompt?.version || "—";
  $("version-stamp").textContent = version;
  $("hash-chip").textContent = `hash ${shortHash(state.prompt?.hash)}`;
}

function renderVersions() {
  const list = $("version-list");
  list.innerHTML = state.versions
    .map((item) => {
      const current = item.is_current ? "is-current" : "";
      const viewing = state.viewingVersion === item.version ? "is-current" : "";
      return `<li>
        <button type="button" data-version="${item.version}" class="${current} ${viewing}">
          <span class="ver-label">${item.version}${item.is_current ? " · live" : ""}</span>
          <span class="ver-meta">${shortHash(item.hash)}</span>
        </button>
      </li>`;
    })
    .join("");
}

function renderEditorChrome() {
  const banner = $("editor-banner");
  const viewing = state.viewingVersion && state.viewingVersion !== state.prompt?.version;
  banner.hidden = !viewing;
  banner.textContent = viewing
    ? `Viewing ${state.viewingVersion} (read only). Live edition is ${state.prompt?.version}.`
    : "";
  $("prompt-editor").readOnly = Boolean(viewing);
  $("btn-save").disabled = Boolean(viewing) || !unsaved();
  const busy = state.evalStatus.status === "running";
  $("btn-eval").disabled = busy;
}

function renderProgress() {
  const rail = $("progress-rail");
  const status = state.evalStatus || { status: "idle" };
  const running = status.status === "running";
  const errored = status.status === "error";
  rail.hidden = !running && !errored;
  if (!running && !errored) {
    $("progress-copy").textContent = "Idle";
    $("progress-fill").style.width = "0%";
    return;
  }
  const progress = status.progress || {};
  const total = progress.total || 0;
  const done = progress.done || 0;
  const pctDone = total ? Math.min(100, (done / total) * 100) : running ? 8 : 0;
  $("progress-fill").style.width = `${pctDone}%`;
  if (errored) {
    $("progress-copy").textContent = `Eval failed · ${status.error || "unknown error"}`;
    return;
  }
  const file = progress.current_file ? ` · ${progress.current_file}` : "";
  $("progress-copy").textContent = `Running ${done}/${total || "…"}${file}`;
}

function renderRuns() {
  const list = $("run-list");
  if (!state.runs.length) {
    list.innerHTML = `<li class="ver-meta">No sheets yet.</li>`;
  } else {
    list.innerHTML = state.runs
      .map((run) => {
        const active = run.id === state.selectedRun ? "is-active" : "";
        return `<li>
          <button type="button" class="run-item ${active}" data-run="${run.id}">
            <span class="acc">${pct(run.overall_accuracy)}</span>
            <span class="ver-label">${run.prompt_version}</span>
            <span class="run-meta">${run.id}<br>${run.n_docs} docs · ${run.n_errors} err · ${money(run.total_cost_usd)}</span>
          </button>
        </li>`;
      })
      .join("");
  }

  const options = state.runs
    .map((run) => `<option value="${run.id}">${run.prompt_version} · ${pct(run.overall_accuracy)} · ${run.id}</option>`)
    .join("");
  const a = $("compare-a");
  const b = $("compare-b");
  const prevA = a.value;
  const prevB = b.value;
  a.innerHTML = options;
  b.innerHTML = options;
  if (state.runs.length >= 2) {
    a.value = prevA && [...a.options].some((o) => o.value === prevA) ? prevA : state.runs[1].id;
    b.value = prevB && [...b.options].some((o) => o.value === prevB) ? prevB : state.runs[0].id;
  }
}

function fieldTable(title, rows, kind) {
  if (!rows?.length) return "";
  const body = rows
    .map((row) => {
      if (kind === "counts") {
        const [ok, n] = row.counts || [0, 0];
        return `<tr><td>${row.field}</td><td class="num">${ok}/${n}</td><td class="num">${pct(row.acc)}</td></tr>`;
      }
      if (kind === "style") {
        return `<tr><td>${row.style}</td><td class="num">${pct(row.acc)}</td></tr>`;
      }
      const cls = deltaClass(row.delta);
      return `<tr>
        <td>${row.field || row.style || row.file}</td>
        <td class="num">${pct(row.a)}</td>
        <td class="num">${pct(row.b)}</td>
        <td class="num ${cls}">${deltaText(row.delta)}</td>
      </tr>`;
    })
    .join("");
  const head =
    kind === "counts"
      ? `<th>Field</th><th class="num">ok/n</th><th class="num">acc</th>`
      : kind === "style"
        ? `<th>Style</th><th class="num">acc</th>`
        : `<th></th><th class="num">A</th><th class="num">B</th><th class="num">Δ</th>`;
  return `<h3>${title}</h3><table class="ledger"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function formatValue(value) {
  if (value == null || value === "") return "∅";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function renderDoc(doc) {
  const failed = (doc.field_pairs || []).filter((row) => !row.ok);
  const pairs = failed
    .map(
      (row) => `<tr class="miss">
        <td>${row.field}</td>
        <td><span class="pair-pred">${escapeHtml(formatValue(row.predicted))}</span></td>
        <td><span class="pair-gold">${escapeHtml(formatValue(row.gold))}</span></td>
      </tr>`
    )
    .join("");
  const error = doc.error
    ? `<p class="banner">${escapeHtml(doc.error)}</p>`
    : "";
  const table = failed.length
    ? `<table class="ledger"><thead><tr><th>Field</th><th>Predicted</th><th>Gold</th></tr></thead><tbody>${pairs}</tbody></table>`
    : `<p class="ver-meta">All scored fields matched.</p>`;
  return `<details class="doc-block">
    <summary>
      <span class="doc-file">${escapeHtml(doc.file)}</span>
      <span class="run-meta">${doc.style || ""} · ${pct(doc.accuracy)}${doc.ok ? "" : " · extract error"}</span>
    </summary>
    <div class="doc-body">${error}${table}</div>
  </details>`;
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderDetail() {
  const root = $("run-detail");
  if (state.compare) {
    const cmp = state.compare;
    root.innerHTML = `
      <p class="kicker">Compare</p>
      <h2>${cmp.a.prompt_version} → ${cmp.b.prompt_version}</h2>
      <div class="stat-row">
        <div class="stat"><dt>Overall Δ</dt><dd class="${deltaClass(cmp.overall_delta)}">${deltaText(cmp.overall_delta)}</dd></div>
        <div class="stat"><dt>A</dt><dd>${pct(cmp.a.overall_accuracy)}</dd></div>
        <div class="stat"><dt>B</dt><dd>${pct(cmp.b.overall_accuracy)}</dd></div>
      </div>
      ${fieldTable("By field", cmp.per_field, "delta")}
      ${fieldTable("By style", cmp.by_style, "delta")}
      ${fieldTable("Improved documents", cmp.improved, "delta")}
      ${fieldTable("Regressed documents", cmp.regressed, "delta")}
      <p class="ver-meta">${cmp.unchanged_docs} documents unchanged</p>
    `;
    return;
  }
  if (!state.detail) {
    root.innerHTML = `<p class="empty">Select a sheet from the rail.</p>`;
    return;
  }
  const run = state.detail;
  const fieldRows = Object.entries(run.per_field_counts || {}).map(([field, counts]) => ({
    field,
    counts,
    acc: run.per_field_accuracy?.[field],
  }));
  const styleRows = Object.entries(run.by_style || {}).map(([style, acc]) => ({ style, acc }));
  const docs = (run.docs || []).map(renderDoc).join("");
  const promptBlock = run.system_prompt
    ? `<details class="doc-block"><summary><span class="doc-file">Prompt snapshot</span></summary>
        <div class="doc-body"><pre class="pair-gold">${escapeHtml(run.system_prompt)}</pre></div></details>`
    : "";
  root.innerHTML = `
    <p class="kicker">${run.id}</p>
    <h2>${run.prompt_version} · ${pct(run.overall_accuracy)}</h2>
    <div class="stat-row">
      <div class="stat"><dt>Docs</dt><dd>${run.n_docs}</dd></div>
      <div class="stat"><dt>Errors</dt><dd>${run.n_errors}</dd></div>
      <div class="stat"><dt>Cost</dt><dd>${money(run.total_cost_usd)}</dd></div>
      <div class="stat"><dt>Model</dt><dd>${escapeHtml(run.model || "—")}</dd></div>
    </div>
    ${fieldTable("By field", fieldRows, "counts")}
    ${fieldTable("By style", styleRows, "style")}
    ${promptBlock}
    <h3>Documents</h3>
    ${docs || `<p class="ver-meta">No documents in this artifact.</p>`}
  `;
}

function render() {
  renderMasthead();
  renderVersions();
  renderEditorChrome();
  renderProgress();
  renderRuns();
  renderDetail();
  $("save-status").textContent = unsaved() ? "Unsaved changes" : "";
}

async function loadPrompt() {
  state.prompt = await api("/api/prompt");
  state.versions = await api("/api/prompts");
  state.draft = state.prompt.system_prompt;
  state.saved = state.prompt.system_prompt;
  state.viewingVersion = state.prompt.version;
  $("prompt-editor").value = state.draft;
}

async function loadRuns() {
  state.runs = await api("/api/runs");
}

async function loadVersion(version) {
  const entry = await api(`/api/prompts/${encodeURIComponent(version)}`);
  state.viewingVersion = entry.version;
  $("prompt-editor").value = entry.system_prompt;
  if (entry.is_current) {
    state.draft = entry.system_prompt;
  }
}

async function savePrompt() {
  const result = await api("/api/prompt", {
    method: "POST",
    body: JSON.stringify({ system_prompt: $("prompt-editor").value }),
  });
  await loadPrompt();
  $("save-status").textContent = result.unchanged
    ? "Already the live edition"
    : `Bumped to ${result.version}`;
  render();
}

async function startEval() {
  const raw = $("eval-limit").value;
  const limit = raw === "" ? null : Number(raw);
  const body = limit == null ? {} : { limit };
  state.evalStatus = await api("/api/eval", {
    method: "POST",
    body: JSON.stringify(body),
  });
  render();
  startPolling();
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    try {
      state.evalStatus = await api("/api/eval/status");
      renderProgress();
      renderEditorChrome();
      if (state.evalStatus.status === "done") {
        stopPolling();
        await loadRuns();
        if (state.evalStatus.run_id) {
          state.selectedRun = state.evalStatus.run_id;
          state.compare = null;
          state.detail = await api(`/api/runs/${encodeURIComponent(state.evalStatus.run_id)}`);
          setView("runs");
        }
        render();
      }
      if (state.evalStatus.status === "error") {
        stopPolling();
        render();
      }
    } catch (err) {
      stopPolling();
      $("save-status").textContent = err.message;
    }
  }, 1000);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function maybeStartEval() {
  if (unsaved()) {
    $("confirm-modal").hidden = false;
    return;
  }
  await startEval();
}

document.querySelectorAll(".folio-tab").forEach((tab) => {
  tab.addEventListener("click", async () => {
    setView(tab.dataset.view);
    if (tab.dataset.view === "runs") {
      await loadRuns();
      render();
    }
  });
});

$("prompt-editor").addEventListener("input", () => {
  state.draft = $("prompt-editor").value;
  renderEditorChrome();
  $("save-status").textContent = unsaved() ? "Unsaved changes" : "";
});

$("version-list").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-version]");
  if (!button) return;
  await loadVersion(button.dataset.version);
  render();
});

$("btn-save").addEventListener("click", async () => {
  try {
    await savePrompt();
  } catch (err) {
    $("save-status").textContent = err.message;
  }
});

$("btn-eval").addEventListener("click", async () => {
  try {
    await maybeStartEval();
  } catch (err) {
    $("save-status").textContent = err.message;
    render();
  }
});

$("confirm-cancel").addEventListener("click", () => {
  $("confirm-modal").hidden = true;
});

$("confirm-run").addEventListener("click", async () => {
  $("confirm-modal").hidden = true;
  try {
    await startEval();
  } catch (err) {
    $("save-status").textContent = err.message;
  }
});

$("run-list").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-run]");
  if (!button) return;
  state.selectedRun = button.dataset.run;
  state.compare = null;
  state.detail = await api(`/api/runs/${encodeURIComponent(state.selectedRun)}`);
  render();
});

$("btn-compare").addEventListener("click", async () => {
  const a = $("compare-a").value;
  const b = $("compare-b").value;
  if (!a || !b) return;
  state.compare = await api(`/api/eval/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
  state.selectedRun = null;
  state.detail = null;
  render();
});

window.addEventListener("beforeunload", (event) => {
  if (unsaved()) event.preventDefault();
});

(async function init() {
  try {
    await loadPrompt();
    await loadRuns();
    state.evalStatus = await api("/api/eval/status");
    if (state.evalStatus.status === "running") startPolling();
    render();
  } catch (err) {
    $("save-status").textContent = err.message;
  }
})();
