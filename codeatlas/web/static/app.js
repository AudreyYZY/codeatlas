"use strict";

const $ = (sel) => document.querySelector(sel);
const el = (tag, props = {}, kids = []) => {
  const node = document.createElement(tag);
  Object.entries(props).forEach(([k, v]) => {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  });
  (Array.isArray(kids) ? kids : [kids]).forEach((k) => k && node.append(k));
  return node;
};
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (n) => (n ?? 0).toLocaleString();

const state = { project: null, report: null, files: [], graph: null, tab: "architecture", structure: null };

async function api(path, opts) {
  if (window.CODEATLAS_SNAPSHOT) return snapshotApi(path, opts);
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) { /* not json */ }
    throw new Error(detail);
  }
  return res.headers.get("content-type")?.includes("json") ? res.json() : res.text();
}

/* ── Projects ───────────────────────────────────────────── */

async function loadProjects() {
  const { projects } = await api("/api/projects");
  const list = $("#projList");
  list.textContent = "";
  if (!projects.length) {
    list.append(el("div", { class: "muted", style: "font-size:12.5px", text: "None yet." }));
    return;
  }
  projects.forEach((p) => {
    list.append(el("div", {
      class: "proj" + (p.name === state.project ? " active" : ""),
      onclick: () => selectProject(p.name),
    }, [
      el("div", { class: "n", text: p.name }),
      el("div", { class: "m", text: `${num(p.files)} files · ${num(p.symbols)} symbols` }),
    ]));
  });
}

async function selectProject(name) {
  state.project = name;
  $("#noproj").classList.add("hidden");
  $("#workspace").classList.remove("hidden");
  $("#projName").textContent = name;
  $("#mdLink").href = `/api/projects/${encodeURIComponent(name)}/report.md`;
  await loadProjects();
  await Promise.all([loadReport(), loadFiles(), loadStructure()]);
  showTab(state.tab);
}

/* ── Indexing ───────────────────────────────────────────── */

async function startIndex(body) {
  const job = await api("/api/index", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  pollJob(job.job);
}

function pollJob(jobId) {
  $("#jobBox").classList.remove("hidden");
  const tick = async () => {
    let job;
    try { job = await api(`/api/jobs/${jobId}`); }
    catch (e) { $("#jobMsg").textContent = e.message; return; }

    const pct = job.total ? Math.round((job.done / job.total) * 100) : (job.state === "done" ? 100 : 8);
    $("#jobBar").style.width = pct + "%";
    $("#jobMsg").textContent = job.state === "error" ? "Failed: " + job.error : job.message;

    if (job.state === "done") {
      $("#jobBar").style.width = "100%";
      const s = job.stats || {};
      $("#jobMsg").textContent =
        `Indexed ${num(s.files)} files, ${num(s.symbols)} symbols in ${(s.elapsed || 0).toFixed(1)}s${s.errors ? " · WARNING: " + s.errors + " files failed to parse" : ""}`;
      await selectProject(job.project);
      setTimeout(() => $("#jobBox").classList.add("hidden"), 4000);
      return;
    }
    if (job.state === "error") return;
    setTimeout(tick, 400);
  };
  tick();
}

$("#indexBtn").addEventListener("click", () => {
  const path = $("#pathInput").value.trim();
  if (!path) { $("#pathInput").focus(); return; }
  startIndex({ path, incremental: true }).catch((e) => {
    $("#jobBox").classList.remove("hidden");
    $("#jobMsg").textContent = e.message;
  });
});
$("#pathInput").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#indexBtn").click(); });
$("#reindexBtn").addEventListener("click", async () => {
  const root = $("#projRoot").textContent;
  if (root) startIndex({ path: root, name: state.project, incremental: true });
});

const drop = $("#drop");
drop.addEventListener("click", () => $("#fileInput").click());
["dragenter", "dragover"].forEach((ev) =>
  drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) =>
  drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => { if (e.dataTransfer.files[0]) uploadZip(e.dataTransfer.files[0]); });
$("#fileInput").addEventListener("change", (e) => { if (e.target.files[0]) uploadZip(e.target.files[0]); });

async function uploadZip(file) {
  const form = new FormData();
  form.append("file", file);
  $("#jobBox").classList.remove("hidden");
  $("#jobMsg").textContent = `Uploading ${file.name}…`;
  $("#jobBar").style.width = "5%";
  try {
    const job = await api("/api/upload", { method: "POST", body: form });
    pollJob(job.job);
  } catch (e) { $("#jobMsg").textContent = e.message; }
}

/* ── Tabs ───────────────────────────────────────────────── */

document.querySelectorAll(".tab").forEach((btn) =>
  btn.addEventListener("click", () => showTab(btn.dataset.tab)));

function showTab(name) {
  state.tab = name;
  history.replaceState(null, "", "#" + name);
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  ["overview", "architecture", "flow", "guide", "map", "structure", "calls", "files", "symbols", "cycles"].forEach((t) =>
    $("#tab-" + t).classList.toggle("hidden", t !== name));
  if (name === "architecture") loadArchitecture().catch(showError);
  if (name === "flow") loadRelationships().catch(showError);
  if (name === "guide") loadFileGuide().catch(showError);
  if (name === "map") loadGraph().catch(showError);
  if (name === "calls") loadCallGraph().catch(showError);
  if (name === "cycles") loadCycles().catch(showError);
}

/* ── Overview ───────────────────────────────────────────── */

function miniTable(rows, cols) {
  const table = el("table");
  table.append(el("thead", {}, el("tr", {}, cols.map((c) =>
    el("th", { class: c.num ? "num" : "", text: c.label })))));
  const tbody = el("tbody");
  rows.forEach((r) => {
    const tr = el("tr", { onclick: () => cols.onclick && cols.onclick(r) });
    cols.forEach((c) => tr.append(el("td", { class: c.num ? "num" : "", html: c.get(r) })));
    tbody.append(tr);
  });
  table.append(tbody);
  return table;
}

function renderMarkdownish(text) {
  // Deliberately minimal: bold, inline code, and "- " bullets. Everything is
  // escaped first, so no HTML from the report can execute.
  const lines = esc(text).split("\n");
  let html = "", inList = false;
  for (const raw of lines) {
    const line = raw
      .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
      .replace(/`([^`]+)`/g, '<code>$1</code>');
    if (line.startsWith("- ")) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${line.slice(2)}</li>`;
    } else {
      if (inList) { html += "</ul>"; inList = false; }
      if (line.trim()) html += `<p>${line}</p>`;
    }
  }
  if (inList) html += "</ul>";
  return html;
}

async function loadReport() {
  const r = await api(`/api/projects/${encodeURIComponent(state.project)}/report`);
  state.report = r;
  $("#projRoot").textContent = r.root || "";

  const s = r.stats;
  $("#tiles").innerHTML = "";
  [
    ["Files", num(s.files)], ["Lines", num(s.lines)], ["Symbols", num(s.symbols)],
    ["Imports", num(s.imports)], ["Call sites", num(s.calls)],
    ["Dep edges", num(s.deps)], ["Cycles", num(r.cycles.length)],
  ].forEach(([k, v]) =>
    $("#tiles").append(el("div", { class: "tile" }, [
      el("div", { class: "v", text: v }), el("div", { class: "k", text: k }),
    ])));

  const narr = $("#narrative");
  narr.innerHTML = "<h3>What this codebase is</h3>";
  r.narrative.forEach((sec) => {
    narr.append(el("h4", { text: sec.title }));
    narr.append(el("div", { html: renderMarkdownish(sec.body) }));
  });

  $("#signals").innerHTML = "";
  r.health.forEach((sig) => {
    $("#signals").append(el("div", { style: "margin-bottom:10px" }, [
      el("div", { class: "row", style: "justify-content:space-between" }, [
        el("span", { text: sig.label }),
        el("span", { class: "pill " + sig.status, text: sig.value }),
      ]),
      el("div", { class: "muted", style: "font-size:12px", text: sig.detail }),
    ]));
  });

  $("#modTable").replaceWith(withId(miniTable(r.modules, [
    { label: "Module", get: (m) => `<code>${esc(m.module)}</code>` +
      (m.role ? ` <span class="muted">${esc(m.role)}</span>` : "") },
    { label: "Files", num: true, get: (m) => num(m.files) },
    { label: "Symbols", num: true, get: (m) => num(m.symbols) },
    { label: "Lines", num: true, get: (m) => num(m.lines) },
  ]), "modTable"));

  $("#extTable").replaceWith(withId(miniTable(r.externals, [
    { label: "Package", get: (e) => `<code>${esc(e.source_path)}</code>` },
    { label: "Files", num: true, get: (e) => num(e.cnt) },
  ]), "extTable"));

  const openFile = (row) => { showTab("files"); loadFileDetail(row.rel_path); };
  $("#entryTable").replaceWith(withId(miniTable(r.entrypoints, [
    { label: "File", get: (f) => `<code>${esc(f.rel_path)}</code>`, onclick: openFile },
    { label: "Imports", num: true, get: (f) => num(f.imports_count) },
    { label: "Lines", num: true, get: (f) => num(f.lines) },
  ].map((c, i) => (i === 0 ? c : c))), "entryTable"));
  bindRowClicks("#entryTable", r.entrypoints, openFile);

  $("#hotTable").replaceWith(withId(miniTable(r.hotspots, [
    { label: "File", get: (f) => `<code>${esc(f.rel_path)}</code>` },
    { label: "Dependents", num: true, get: (f) => num(f.dependents) },
    { label: "Lines", num: true, get: (f) => num(f.lines) },
  ]), "hotTable"));
  bindRowClicks("#hotTable", r.hotspots, openFile);
}

function withId(node, id) { node.id = id; return node; }

function bindRowClicks(sel, rows, fn) {
  const trs = document.querySelectorAll(`${sel} tbody tr`);
  trs.forEach((tr, i) => tr.addEventListener("click", () => fn(rows[i])));
}

/* ── Files ──────────────────────────────────────────────── */

async function loadFiles() {
  const { files } = await api(`/api/projects/${encodeURIComponent(state.project)}/files`);
  state.files = files;
  renderFileTable("");
  const focus = $("#mapFocus");
  focus.innerHTML = '<option value="">Whole project</option>';
  files.forEach((f) => focus.append(el("option", { value: f.rel_path, text: f.rel_path })));
}

function renderFileTable(filter) {
  const rows = state.files.filter((f) => !filter || f.rel_path.toLowerCase().includes(filter));
  const table = miniTable(rows, [
    { label: "File", get: (f) => `<code>${esc(f.rel_path)}</code>` },
    { label: "Sym", num: true, get: (f) => num(f.symbol_count) },
    { label: "In", num: true, get: (f) => num(f.in_degree) },
    { label: "Out", num: true, get: (f) => num(f.out_degree) },
    { label: "Lines", num: true, get: (f) => num(f.lines) },
  ]);
  table.id = "fileTable";
  $("#fileTable").replaceWith(table);
  bindRowClicks("#fileTable", rows, (f) => loadFileDetail(f.rel_path));
}

$("#fileFilter").addEventListener("input", (e) => renderFileTable(e.target.value.toLowerCase().trim()));

async function loadFileDetail(relPath) {
  const box = $("#fileDetail");
  box.innerHTML = '<div class="muted">Loading…</div>';
  let d;
  try {
    d = await api(`/api/projects/${encodeURIComponent(state.project)}/file?path=${encodeURIComponent(relPath)}`);
  } catch (e) { box.innerHTML = `<div class="muted">${esc(e.message)}</div>`; return; }

  const f = d.file;
  box.innerHTML = "";
  box.append(el("h3", { html: `<code>${esc(f.rel_path)}</code>` }));
  box.append(el("div", { class: "muted", style: "font-size:12px; margin-bottom:10px",
    text: `${f.language} · ${num(f.lines)} lines · ${d.symbols.length} symbols · ${d.dependents.length} files import this` }));

  if (d.explanation) {
    box.append(el("p", {text:d.explanation.summary}), el("button", {text:"Read implementation guide", onclick:()=>openFileGuide(f.rel_path)}));
  }
  if (d.source_status === "changed") box.append(el("p", {class:"notice",text:"Source changed after indexing. Re-index before trusting line links and analysis."}));
  if (d.symbols.length) {
    box.append(el("div", { class: "sec-label", text: "Declarations" }));
    const list = el("div", { class: "scroll", style: "max-height:220px" });
    d.symbols.forEach((s) => list.append(el("div", { class: "mono", style: "padding:2px 0" },
      [el("span", { class: "muted", text: `L${s.line_start} ` }),
       el("span", { class: "pill", text: s.kind }),
       el("span", { text: " " + s.name }),
       s.is_export ? el("span", { class: "muted", text: " ·exported" }) : null])));
    box.append(list);
  }

  if (d.dependencies.length || d.dependents.length) {
    box.append(el("div", { class: "sec-label", style: "margin-top:12px", text: "Dependencies" }));
    const wrap = el("div", { class: "mono", style: "font-size:12px" });
    d.dependencies.forEach((x) => wrap.append(el("div", { text: "→ " + x.target_rel_path })));
    d.dependents.forEach((x) => wrap.append(el("div", { class: "muted", text: "← " + x.source_rel_path })));
    box.append(wrap);
  }

  box.append(el("button", {
    style: "margin-top:12px",
    onclick: () => { $("#mapFocus").value = f.rel_path; showTab("map"); loadGraph(); },
    text: "Focus on the map",
  }));

  if (d.source) {
    box.append(el("div", { class: "sec-label", style: "margin-top:12px", text: "Source" }));
    box.append(el("pre", { class: "src", text: d.source }));
  } else if (window.CODEATLAS_SNAPSHOT) {
    box.append(el("p", {class:"muted",text:"Source bodies are excluded from this snapshot. Open CodeAtlas locally to read source."}));
  }
}

/* ── Symbols ────────────────────────────────────────────── */

let symTimer = null;
$("#symSearch").addEventListener("input", (e) => {
  clearTimeout(symTimer);
  const q = e.target.value.trim();
  symTimer = setTimeout(() => q.length >= 2 && searchSymbols(q), 180);
});

async function searchSymbols(q) {
  const d = await api(`/api/projects/${encodeURIComponent(state.project)}/search?q=${encodeURIComponent(q)}`);
  const table = miniTable(d.symbols, [
    { label: "Symbol", get: (s) => esc(s.name) },
    { label: "Kind", get: (s) => `<span class="pill">${esc(s.kind)}</span>` },
    { label: "File", get: (s) => `<code>${esc(s.rel_path)}:${s.line_start}</code>` },
  ]);
  table.id = "symTable";
  $("#symTable").replaceWith(table);
  bindRowClicks("#symTable", d.symbols, (s) => loadSymbolDetail(s.name, s.id));
}

async function loadSymbolDetail(name, symbolId) {
  const box = $("#symDetail");
  box.innerHTML = '<div class="muted">Loading…</div>';
  let d;
  try {
    d = await api(`/api/projects/${encodeURIComponent(state.project)}/symbol?name=${encodeURIComponent(name)}${symbolId ? "&symbol_id=" + symbolId : ""}`);
  } catch (e) { box.innerHTML = `<div class="muted">${esc(e.message)}</div>`; return; }

  const p = d.primary;
  box.innerHTML = "";
  box.append(el("h3", { text: p.name }));
  box.append(el("div", { class: "muted mono", style: "font-size:12px; margin-bottom:8px",
    text: `${p.kind} · ${p.rel_path}:${p.line_start}` }));
  if (d.matches.length > 1) {
    box.append(el("p", {class:"muted",text:"Multiple declarations share this name. Choose the exact file:"}));
    d.matches.forEach((s)=>box.append(el("button", {style:"margin:0 4px 6px 0", text:`${s.rel_path}:${s.line_start}`,
      onclick:()=>loadSymbolDetail(s.name,s.id)})));
  }
  if (d.note) box.append(el("p", {class:"muted",text:d.note}));
  if (["function","method","arrow_function"].includes(p.kind)) box.append(el("button", {text:"Explore call graph",onclick:()=>{$("#callFocus").value=p.id;showTab("calls");}}));
  if (p.signature) box.append(el("pre", { class: "src", style: "max-height:120px", text: p.signature }));

  box.append(el("div", { class: "sec-label", style: "margin-top:12px",
    text: `Linked callers (${d.callers.length})` }));
  const callers = el("div", { class: "mono scroll", style: "font-size:12px; max-height:170px" });
  if (!d.callers.length) callers.append(el("div", { class: "muted", text: "No caller linked by direct local/import names. Dynamic callers may be unresolved." }));
  d.callers.forEach((c) => callers.append(el("div", {
    text: `${c.caller_name || "(top-level)"} — ${c.rel_path}${c.line ? ":" + c.line : ""}`,
  })));
  box.append(callers);

  box.append(el("div", { class: "sec-label", style: "margin-top:12px",
    text: `Calls (${d.callees.length})` }));
  const callees = el("div", { class: "mono", style: "font-size:12px" });
  if (!d.callees.length) callees.append(el("div", { class: "muted", text: "Makes no recorded calls." }));
  d.callees.forEach((c) => callees.append(el("span", { class: "pill", style: "margin:0 4px 4px 0", text: c.callee_name + (c.resolution === "unresolved" ? " · unresolved" : "") })));
  box.append(callees);

  if (d.chain.length) {
    box.append(el("div", { class: "sec-label", style: "margin-top:12px", text: "Name-based call chain (may include same-name declarations)" }));
    const chain = el("div", { class: "chain scroll", style: "max-height:220px" });
    d.chain.forEach((step) => {
      chain.append(el("div", { html: `${"&nbsp;".repeat(step.depth * 3)}<b>${esc(step.symbol)}()</b>` }));
      step.callees.slice(0, 6).forEach((c) =>
        chain.append(el("div", { class: "lvl", html: `${"&nbsp;".repeat(step.depth * 3 + 3)}→ ${esc(c)}()` })));
    });
    box.append(chain);
  }
}

/* ── Cycles ─────────────────────────────────────────────── */

async function loadCycles() {
  const box = $("#cycleBox");
  box.innerHTML = '<div class="muted">Loading…</div>';
  const d = await api(`/api/projects/${encodeURIComponent(state.project)}/cycles`);
  box.innerHTML = "";
  if (!d.cycles.length) {
    box.append(el("div", { class: "empty", text: "No import cycles. The dependency graph is acyclic." }));
    return;
  }
  box.append(el("h3", { text: `${d.cycles.length} import cycle(s)` }));
  box.append(el("p", { class: "muted", text:
    "Each row is a strongly connected component of the file dependency graph — these files import each other, directly or transitively." }));
  d.cycles.forEach((c, i) => {
    box.append(el("div", { style: "margin:10px 0; padding:10px; background:var(--panel-2); border-radius:8px" }, [
      el("div", { class: "row", style: "justify-content:space-between; margin-bottom:4px" }, [
        el("b", { text: `Cycle ${i + 1}` }),
        el("span", { class: "pill bad", text: `${c.files.length} files` }),
      ]),
      el("div", { class: "mono", style: "font-size:12px", text: c.path.join("  →  ") }),
    ]));
  });
}


function showError(error) {
  const msg = $("#jobMsg");
  $("#jobBox").classList.remove("hidden");
  msg.textContent = error.message || String(error);
}

async function loadStructure() {
  state.structure = await api(`/api/projects/${encodeURIComponent(state.project)}/structure`);
  const focus = $("#callFocus");
  focus.replaceChildren(el("option", { value: "", text: "Whole project" }));
  state.structure.symbols.filter((s) => ["function", "method", "arrow_function", "generator"].includes(s.kind))
    .forEach((s) => focus.append(el("option", { value: s.id, text: `${s.name} — ${s.rel_path}:${s.line_start}` })));
  renderTree();
}

function renderTree() {
  const query = $("#treeFilter").value.toLowerCase().trim();
  const box = $("#tree");
  box.textContent = "";
  function branch(node) {
    if (node.kind === "file") {
      if (query && !node.rel_path.toLowerCase().includes(query) &&
          !node.symbols.some((s) => s.name.toLowerCase().includes(query))) return null;
      return el("button", { text: `${node.name} · ${node.symbols.length} declarations`,
        onclick: () => renderOutline(node) });
    }
    const children = node.children.map(branch).filter(Boolean);
    if (!children.length) return null;
    const d = el("details", {}, [el("summary", { text: node.name + "/" }), ...children]);
    d.open = Boolean(query) || node.name === "(root)";
    return d;
  }
  if (state.structure) box.append(branch(state.structure.tree) || el("p", { text: "No matching files or declarations." }));
}

function renderOutline(file) {
  const box = $("#outline");
  box.replaceChildren(el("h3", { text: file.rel_path }),
    el("p", { class: "muted", text: `${file.language} · ${file.lines} lines` }),
    el("button", {text:"Explain implementation",onclick:()=>openFileGuide(file.rel_path)}),
    el("button", { text: "Open source", onclick: () => { showTab("files"); loadFileDetail(file.rel_path); } }));
  file.symbols.forEach((s) => {
    const callable = ["function", "method", "arrow_function", "generator"].includes(s.kind);
    const item = el("div", { style: `margin:9px 0 9px ${s.parent_symbol ? 16 : 0}px` }, [
      el("span", { class: "pill", text: s.kind }),
      el("span", { class: "mono", text: ` ${s.parent_symbol ? s.parent_symbol + "." : ""}${s.name} · L${s.line_start}` }),
    ]);
    if (callable) item.append(el("button", { text: "Calls", style: "margin-left:8px; font-size:11px",
      onclick: () => { $("#callFocus").value = s.id; showTab("calls"); } }));
    box.append(item);
  });
  if (!file.symbols.length) box.append(el("p", { class: "muted", text: "No declarations recorded in this file." }));
}
$("#treeFilter").addEventListener("input", renderTree);

async function loadCallGraph() {
  const project = state.project;
  const params = new URLSearchParams({ depth: $("#callDepth").value, direction: $("#callDirection").value, limit: 150, include_unresolved: $("#callUnresolved").checked });
  if ($("#callFocus").value) params.set("focus", $("#callFocus").value);
  const graph = await api(`/api/projects/${encodeURIComponent(project)}/callgraph?${params}`);
  if (project !== state.project) return;
  $("#callNote").textContent = `${graph.shown_nodes} / ${graph.total_nodes} nodes${graph.truncated ? " · limited view: focus on a function to see its neighbourhood." : "."} ${graph.note}`;
  const svg = $("#callCanvas");
  svg.replaceChildren();
  const ns = "http://www.w3.org/2000/svg";
  const add = (tag, attrs = {}, text = "") => {
    const n = document.createElementNS(ns, tag);
    Object.entries(attrs).forEach(([k,v]) => n.setAttribute(k,v));
    n.textContent = text; return n;
  };
  if (!graph.nodes.length) { svg.setAttribute("viewBox", "0 0 800 420"); svg.append(add("text", {x:30,y:50}, "No callable declarations indexed.")); return; }
  // Deterministic layered layout; unresolved leaves occupy a separate column.
  const columns = new Map();
  graph.nodes.forEach((n) => {
    const level = params.has("focus") ? (n.layer ?? n.depth) : (n.unresolved ? 1 : 0);
    if (!columns.has(level)) columns.set(level, []);
    columns.get(level).push(n);
  });
  const positions = {};
  const levels = [...columns.keys()].sort((a,b) => a-b);
  let height = 420;
  levels.forEach((level,i) => {
    columns.get(level).forEach((n,j) => positions[n.id] = {x: 24+i*340, y: 24+j*88});
    height = Math.max(height, columns.get(level).length*88+48);
  });
  const width = Math.max(800, levels.length*340+24);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.dataset.width=width; svg.dataset.height=height;
  applyCallZoom();
  const defs = add("defs"); const marker = add("marker", {id:"callArrow",viewBox:"0 0 10 10",refX:9,refY:5,markerWidth:6,markerHeight:6,orient:"auto-start-reverse"});
  marker.append(add("path", {d:"M 0 0 L 10 5 L 0 10 z", fill:"#858580"})); defs.append(marker); svg.append(defs);
  graph.edges.forEach((e) => {
    const a=positions[e.source],b=positions[e.target];
    if (!a || !b) return;
    const startX=a.x+280, endX=b.x;
    const bend=Math.max(startX,endX)+32;
    svg.append(add("path", {d:`M${startX},${a.y+28} C${bend},${a.y+28} ${bend},${b.y+28} ${endX},${b.y+28}`,
      class:"call-edge", "marker-end":"url(#callArrow)", "stroke-dasharray":e.resolution==="unresolved"?"5 4":""}));
  });
  graph.nodes.forEach((n) => {
    const pos=positions[n.id]; const group=add("g", {class:"call-node"+(n.unresolved?" unresolved":""),transform:`translate(${pos.x} ${pos.y})`,tabindex:0,role:"button"});
    group.append(add("title", {}, `${n.label} · ${n.path}:${n.line} · ${n.kind}`));
    group.append(add("rect", {width:280,height:60,rx:8}));
    group.append(add("text", {x:12,y:23}, n.label.length>33?n.label.slice(0,30)+"…":n.label));
    group.append(add("text", {x:12,y:44,style:"font-size:10px; opacity:.7"}, n.unresolved?n.kind:`${n.path.length>36?"…"+n.path.slice(-33):n.path}:${n.line}`));
    const open = () => { if (!n.unresolved) { showTab("files"); loadFileDetail(n.path); } };
    group.addEventListener("click",open); group.addEventListener("keydown",(e)=>{if(e.key==="Enter")open();});
    svg.append(group);
  });
}
function applyCallZoom() {
  const svg=$("#callCanvas"),scale=Number($("#callZoom").value)/100;
  svg.style.width=Number(svg.dataset.width)*scale+"px";
  svg.style.height=Number(svg.dataset.height)*scale+"px";
}
$("#callZoom").addEventListener("input",applyCallZoom);
["#callFocus", "#callDirection", "#callDepth", "#callUnresolved"].forEach((id)=>$(id).addEventListener("change",()=>loadCallGraph().catch(showError)));
$("#callDownload").addEventListener("click",()=>{
  const clone=$("#callCanvas").cloneNode(true);
  const style=document.createElementNS("http://www.w3.org/2000/svg","style");
  style.textContent=".call-node rect{fill:#fff;stroke:#2f6f5e;stroke-width:1.5}.call-node.unresolved rect{stroke:#a5641b;stroke-dasharray:5 4}.call-node text{fill:#222;font-family:monospace;font-size:12px}.call-edge{stroke:#888;fill:none}";
  clone.prepend(style);
  const url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)],{type:"image/svg+xml"}));
  const a=el("a",{href:url,download:"codeatlas-calls.svg"});a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});

/* ── Dependency map (force-directed, no dependencies) ───── */

const map = { nodes: [], edges: [], sim: null, tx: 0, ty: 0, scale: 1, drag: null, hover: null };
const PALETTE = ["#4c8fbd", "#c98b3a", "#5aa576", "#b4677f", "#8a7bc0", "#3f9c9c", "#b8734a", "#7a9a3c"];
const moduleColor = (m, idx) => PALETTE[idx % PALETTE.length];

async function loadGraph() {
  const focus = $("#mapFocus").value;
  const depth = $("#mapDepth").value;
  const qs = new URLSearchParams({ depth, direction: "both" });
  if (focus) qs.set("focus", focus);
  const g = await api(`/api/projects/${encodeURIComponent(state.project)}/graph?${qs}`);

  const modules = [...new Set(g.nodes.map((n) => n.module))].sort();
  const colorOf = {};
  modules.forEach((m, i) => (colorOf[m] = moduleColor(m, i)));

  map.nodes = g.nodes.map((n, i) => ({
    ...n,
    color: colorOf[n.module],
    x: Math.cos((i / g.nodes.length) * Math.PI * 2) * (60 + g.nodes.length * 7)
       + (Math.random() - 0.5) * 60,
    y: Math.sin((i / g.nodes.length) * Math.PI * 2) * (60 + g.nodes.length * 7)
       + (Math.random() - 0.5) * 60,
    vx: 0, vy: 0,
    r: Math.max(4, Math.min(20, 4 + Math.sqrt(n.in_degree || 0) * 3.2)),
  }));
  const byId = Object.fromEntries(map.nodes.map((n) => [n.id, n]));
  map.edges = g.edges.map((e) => ({ s: byId[e.source], t: byId[e.target] })).filter((e) => e.s && e.t);

  const legend = $("#legend");
  legend.innerHTML = "";
  modules.slice(0, 9).forEach((m) =>
    legend.append(el("div", { html: `<i style="background:${colorOf[m]}"></i>${esc(m)}` })));
  legend.append(el("div", { class: "muted", text: `${g.shown_nodes} / ${g.total_nodes} files${g.truncated ? " · limited view; choose a file to focus" : ""}` }));

  map.tx = 0; map.ty = 0; map.scale = 1;
  runSim();
}

function runSim() {
  const canvas = $("#map");
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  let alpha = 1;
  let fitted = false;
  cancelAnimationFrame(map.sim);

  // Scale the layout to the graph size so a 300-node project does not collapse
  // into the same blob as a 10-node one.
  const n = Math.max(map.nodes.length, 2);
  const REST = 55 + Math.sqrt(n) * 12;
  const REPEL = REST * REST * 2.4;

  const step = () => {
    if (alpha > 0.004) {
      alpha *= 0.988;
      const cutoff = (REST * 6) ** 2;
      for (let i = 0; i < map.nodes.length; i++) {
        const a = map.nodes[i];
        for (let j = i + 1; j < map.nodes.length; j++) {
          const b = map.nodes[j];
          const dx = b.x - a.x, dy = b.y - a.y;
          const d2 = dx * dx + dy * dy || 0.01;
          if (d2 > cutoff) continue;
          const d = Math.sqrt(d2);
          const f = (REPEL * alpha) / d2;
          const fx = (dx / d) * f, fy = (dy / d) * f;
          a.vx -= fx; a.vy -= fy; b.vx += fx; b.vy += fy;
        }
      }
      map.edges.forEach((e) => {
        const dx = e.t.x - e.s.x, dy = e.t.y - e.s.y;
        const d = Math.hypot(dx, dy) || 0.01;
        const f = (d - REST) * 0.05 * alpha;
        const fx = (dx / d) * f, fy = (dy / d) * f;
        e.s.vx += fx; e.s.vy += fy; e.t.vx -= fx; e.t.vy -= fy;
      });
      map.nodes.forEach((nd) => {
        if (nd === map.drag) return;
        nd.vx -= nd.x * 0.006 * alpha;
        nd.vy -= nd.y * 0.006 * alpha;
        nd.vx *= 0.84; nd.vy *= 0.84;
        nd.x += Math.max(-40, Math.min(40, nd.vx));
        nd.y += Math.max(-40, Math.min(40, nd.vy));
      });
    } else if (!fitted) {
      fitted = true;
      fitToView(rect);
    }
    draw(ctx, rect);
    map.sim = requestAnimationFrame(step);
  };
  step();
}

function fitToView(rect) {
  if (!map.nodes.length) return;
  const xs = map.nodes.map((n) => n.x), ys = map.nodes.map((n) => n.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const w = Math.max(maxX - minX, 1) + 90;
  const h = Math.max(maxY - minY, 1) + 90;
  // 0.88 leaves room for labels, which sit above each node.
  const fit = Math.min(rect.width / w, rect.height / h) * 0.88;
  map.scale = Math.max(0.25, Math.min(2.2, fit));
  map.tx = -((minX + maxX) / 2) * map.scale;
  map.ty = -((minY + maxY) / 2) * map.scale;
}

function draw(ctx, rect) {
  const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  ctx.clearRect(0, 0, rect.width, rect.height);
  ctx.save();
  ctx.translate(rect.width / 2 + map.tx, rect.height / 2 + map.ty);
  ctx.scale(map.scale, map.scale);

  ctx.strokeStyle = dark ? "rgba(255,255,255,.13)" : "rgba(0,0,0,.13)";
  ctx.lineWidth = 1 / map.scale;
  map.edges.forEach((e) => {
    const lit = map.hover && (e.s === map.hover || e.t === map.hover);
    ctx.strokeStyle = lit
      ? (dark ? "rgba(111,184,160,.9)" : "rgba(47,111,94,.8)")
      : (dark ? "rgba(255,255,255,.11)" : "rgba(0,0,0,.11)");
    ctx.beginPath();
    ctx.moveTo(e.s.x, e.s.y);
    ctx.lineTo(e.t.x, e.t.y);
    ctx.stroke();
  });

  map.nodes.forEach((n) => {
    ctx.beginPath();
    ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
    ctx.fillStyle = n.color;
    ctx.globalAlpha = map.hover && map.hover !== n && !isNeighbour(n) ? 0.3 : 1;
    ctx.fill();
    if (n.in_cycle) {
      ctx.strokeStyle = "#d0453a"; ctx.lineWidth = 2 / map.scale; ctx.stroke();
    }
    if (n.is_focus) {
      ctx.strokeStyle = dark ? "#fff" : "#111"; ctx.lineWidth = 2.5 / map.scale; ctx.stroke();
    }
    ctx.globalAlpha = 1;
  });

  // Labels last, skipping ones that would overlap: a cramped graph is worse
  // than a partly-labelled one.
  const taken = new Set();
  const cell = 46;
  const sorted = [...map.nodes].sort((a, b) => (b.r - a.r) || (b.in_degree - a.in_degree));
  ctx.font = `${11 / map.scale}px ui-sans-serif, system-ui, sans-serif`;
  ctx.textAlign = "center";
  sorted.forEach((n) => {
    const forced = n === map.hover || n.is_focus;
    const sx = n.x * map.scale, sy = n.y * map.scale;
    const key = `${Math.round(sx / cell)},${Math.round(sy / cell)}`;
    if (!forced) {
      if (taken.has(key) || n.r < 6) return;
      taken.add(key);
    }
    ctx.fillStyle = forced ? (dark ? "#fff" : "#000") : (dark ? "#cfccc8" : "#43413d");
    ctx.fillText(n.label, n.x, n.y - n.r - 5 / map.scale);
  });
  ctx.restore();
}

function isNeighbour(n) {
  if (!map.hover) return true;
  return map.edges.some((e) => (e.s === map.hover && e.t === n) || (e.t === map.hover && e.s === n));
}

function toWorld(evt) {
  const canvas = $("#map");
  const rect = canvas.getBoundingClientRect();
  return {
    x: (evt.clientX - rect.left - rect.width / 2 - map.tx) / map.scale,
    y: (evt.clientY - rect.top - rect.height / 2 - map.ty) / map.scale,
  };
}

function nodeAt(pt) {
  for (let i = map.nodes.length - 1; i >= 0; i--) {
    const n = map.nodes[i];
    if (Math.hypot(n.x - pt.x, n.y - pt.y) <= n.r + 4) return n;
  }
  return null;
}

(() => {
  const canvas = $("#map");
  let panning = false, last = null;

  canvas.addEventListener("mousedown", (e) => {
    const hit = nodeAt(toWorld(e));
    if (hit) { map.drag = hit; } else { panning = true; last = { x: e.clientX, y: e.clientY }; }
  });
  window.addEventListener("mouseup", () => { map.drag = null; panning = false; });
  canvas.addEventListener("mousemove", (e) => {
    const pt = toWorld(e);
    if (map.drag) { map.drag.x = pt.x; map.drag.y = pt.y; map.drag.vx = map.drag.vy = 0; return; }
    if (panning) {
      map.tx += e.clientX - last.x; map.ty += e.clientY - last.y;
      last = { x: e.clientX, y: e.clientY };
      return;
    }
    const hit = nodeAt(pt);
    map.hover = hit;
    const tip = $("#tip");
    if (hit) {
      const rect = canvas.getBoundingClientRect();
      tip.style.display = "block";
      tip.style.left = e.clientX - rect.left + 12 + "px";
      tip.style.top = e.clientY - rect.top + 12 + "px";
      tip.innerHTML = `<b>${esc(hit.id)}</b><br>${hit.in_degree} importers · ${hit.out_degree} imports · ${num(hit.lines)} lines`;
    } else tip.style.display = "none";
  });
  canvas.addEventListener("mouseleave", () => { $("#tip").style.display = "none"; map.hover = null; });
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    map.scale = Math.max(0.2, Math.min(4, map.scale * factor));
  }, { passive: false });
  canvas.addEventListener("click", (e) => {
    const hit = nodeAt(toWorld(e));
    const card = $("#nodeCard");
    if (!hit) { card.classList.add("hidden"); return; }
    card.classList.remove("hidden");
    card.innerHTML = "";
    card.append(el("h3", { html: `<code>${esc(hit.id)}</code>` }));
    card.append(el("div", { class: "muted", style: "font-size:12.5px",
      text: `${hit.language} · ${num(hit.lines)} lines · ${hit.symbols} symbols · imported by ${hit.in_degree} · imports ${hit.out_degree}${hit.in_cycle ? " · in an import cycle" : ""}` }));
    card.append(el("div", { class: "row", style: "margin-top:10px" }, [
      el("button", { text: "Open file", onclick: () => { showTab("files"); loadFileDetail(hit.id); } }),
      el("button", { text: "Focus here", onclick: () => { $("#mapFocus").value = hit.id; loadGraph(); } }),
    ]));
  });

  $("#mapFocus").addEventListener("change", loadGraph);
  $("#mapDepth").addEventListener("change", loadGraph);
  $("#mapReset").addEventListener("click", () =>
    fitToView($("#map").getBoundingClientRect()));
  window.addEventListener("resize", () => { if (state.tab === "map") runSim(); });
})();

async function boot() {
  const initialTab=location.hash.slice(1);
  if(["overview","architecture","flow","guide","map","structure","calls","files","symbols","cycles"].includes(initialTab))state.tab=initialTab;
  if (window.CODEATLAS_SNAPSHOT) {
    ["#pathInput", "#indexBtn", "#drop", "#fileInput", "#reindexBtn"].forEach((id) => { $(id).disabled = true; $(id).style.pointerEvents = "none"; });
    $("#ver").textContent = "offline snapshot";
    $("#drop").textContent = "Read-only snapshot. Run CodeAtlas locally to import your own project.";
    $("#mdLink").classList.add("hidden");
    await selectProject(window.CODEATLAS_SNAPSHOT.name);
  } else {
    await loadProjects();
    const projects = (await api("/api/projects")).projects;
    if (projects.length) await selectProject(projects[0].name);
  }
}
document.addEventListener("DOMContentLoaded",()=>boot().catch(showError));
