// BibTeX Tools web app: the settings and both panes. The work is done by
// bibtextools (Python) in worker.js.

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

// Bumped when the defaults change, so that they apply to everybody once
const SETTINGS_KEY = "bibtextools.settings.v2";
const ARXIV_KEY = "bibtextools.arxiv.v1";
const THEME_KEY = "bibtextools.theme";
const DUPLICATE_MODES = ["keep", "remove-shorter", "choose"];

// Replaced by the defaults of bibtextools once Python is ready
let defaults = {
  remove_fields: ["abstract", "annote", "bdsk-url-1", "date-added", "date-modified", "file", "owner", "timestamp"],
  clean_fields: ["pages", "month", "eprint", "title", "author"],
};

const DEFAULT_SETTINGS = {
  filter: { enabled: false },
  clean: { enabled: false, unicode: false },
  modernize: { enabled: true, fields: null, shield: true, iso4: false, ids: false, arxiv: false },
  remove: { enabled: true, fields: null },
  duplicates: { mode: "choose", rename: true },
  sort: true,
};

const state = {
  settings: loadSettings(),
  sources: [],          // {name, text} of the bib files
  bbl: null,            // {name, text}
  abbr: null,           // {name, text}
  decisions: new Map(), // "origin|origin" of a duplicate pair -> origin to remove, or null to keep both
  arxiv: loadJson(ARXIV_KEY, {}), // eprint -> primary category
  arxivTried: new Set(),
  arxivBusy: false,
  response: null,
  runId: 0,
  ready: false,
  busy: false,
  error: null,
  selected: null,
  linkScroll: true,
  lastPane: "preview",
};

// Each pane has blank space above and below its content, which lets an entry
// be shown at any height, e.g., to align it with the selected entry
function makePane(el) {
  const [padTop, content, padBottom] = ["pad", "content", "pad"].map((cls) =>
    Object.assign(document.createElement("div"), { className: cls }));
  el.append(padTop, content, padBottom);
  return { el, content, padTop, padBottom, top: 0, bottom: 0, entries: [], byOrigin: new Map() };
}

const panes = {
  original: makePane($("#original")),
  preview: makePane($("#preview")),
};

/* Helpers */

function loadJson(key, fallback) {
  try {
    const value = JSON.parse(localStorage.getItem(key));
    return value === null ? fallback : value;
  } catch {
    return fallback;
  }
}

function saveJson(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode */ }
}

// Settings from storage or a shared link: keep only known keys with the
// right type. Lists of fields default to null (the defaults of bibtextools).
function merge(base, extra) {
  const result = structuredClone(base);
  if (!extra || typeof extra !== "object") return result;
  for (const [key, value] of Object.entries(extra)) {
    if (!(key in result)) continue;
    const current = result[key];
    if (current && typeof current === "object") {
      result[key] = merge(current, value);
    } else if (current === null) {
      if (value === null || (Array.isArray(value) && value.every((v) => typeof v === "string"))) {
        result[key] = value;
      }
    } else if (typeof value === typeof current) {
      result[key] = value;
    }
  }
  return result;
}


function validSettings(settings) {
  if (!DUPLICATE_MODES.includes(settings.duplicates.mode)) {
    settings.duplicates.mode = DEFAULT_SETTINGS.duplicates.mode;
  }
  return settings;
}

function loadSettings() {
  return validSettings(merge(DEFAULT_SETTINGS, loadJson(SETTINGS_KEY, {})));
}

function saveSettings() {
  saveJson(SETTINGS_KEY, state.settings);
}

function getPath(obj, path) {
  return path.split(".").reduce((value, key) => value[key], obj);
}

function setPath(obj, path, value) {
  const keys = path.split(".");
  const last = keys.pop();
  keys.reduce((target, key) => target[key], obj)[last] = value;
}

function escapeHtml(text) {
  return text.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}

function splitLines(text) {
  const lines = text.split("\n").map((line) => (line.endsWith("\r") ? line.slice(0, -1) : line));
  if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
  return lines;
}

function plural(count, word, words = word + "s") {
  return `${count} ${count === 1 ? word : words}`;
}

let toastTimer;
function toast(text) {
  const el = $("#toast");
  el.textContent = text;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}

const removeFields = () => state.settings.remove.fields ?? defaults.remove_fields;
const cleanFields = () => state.settings.modernize.fields ?? defaults.clean_fields;

/* Python worker */

const worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });

worker.onmessage = ({ data }) => {
  if (data.type === "progress") {
    setEngine("loading", data.text);
    $("#overlay-text").textContent = data.text;
  } else if (data.type === "ready") {
    defaults = data.defaults;
    state.ready = true;
    setEngine("ready", "Ready");
    applySettingsToUI();
    schedule(0);
  } else if (data.type === "result") {
    if (data.id !== state.runId) return; // a newer run is on its way
    setBusy(false);
    const response = JSON.parse(data.response);
    if (response.error) {
      showError(response.error);
      return;
    }
    state.error = null;
    state.response = response;
    render();
    maybeFetchArxiv();
  } else if (data.type === "error") {
    if (data.id !== state.runId) return;
    setBusy(false);
    showError(data.message);
  } else if (data.type === "fatal") {
    setEngine("error", "Python could not start");
    showError(`Python could not start: ${data.message}`);
  }
};

worker.onerror = (event) => {
  setEngine("error", "Python could not start");
  showError(`Python could not start: ${event.message || "unknown error"}`);
};

function setEngine(kind, text) {
  $("#engine-dot").className = `dot ${kind === "ready" ? "ready" : kind === "error" ? "error" : ""}`;
  $("#engine-state").textContent = text;
}

function setBusy(busy) {
  state.busy = busy;
  $("#pane-preview").classList.toggle("busy", busy && state.ready);
  if (state.ready) setEngine("ready", busy ? "Working…" : "Ready");
}

function buildRequest() {
  const s = state.settings;
  const modernize = s.modernize.enabled;
  return {
    sources: state.sources,
    bbl: s.filter.enabled && state.bbl ? state.bbl.text : null,
    abbr: s.clean.enabled && state.abbr ? state.abbr.text : null,
    options: {
      clean_fields: modernize ? cleanFields() : [],
      shield_title: modernize && s.modernize.shield,
      iso4: modernize && s.modernize.iso4,
      replace_ids: modernize && s.modernize.ids,
      arxiv: modernize && s.modernize.arxiv,
      remove_fields: s.remove.enabled ? removeFields() : [],
      replace_unicode: s.clean.enabled && s.clean.unicode,
      duplicates: s.duplicates.mode,
      decisions: [...state.decisions].map(([pair, remove]) => [pair.split("|"), remove]),
      rename_duplicate_ids: s.duplicates.rename,
      sort_by_id: s.sort,
    },
    arxiv_categories: state.arxiv,
  };
}

let runTimer;
function schedule(delay = 120) {
  clearTimeout(runTimer);
  runTimer = setTimeout(run, delay);
}

function run() {
  if (!state.sources.length) return;
  state.runId += 1;
  if (!state.ready) return;
  setBusy(true);
  worker.postMessage({ type: "run", id: state.runId, request: buildRequest() });
}

function showError(message) {
  state.error = message;
  const overlay = $("#overlay");
  overlay.classList.add("show", "error");
  $("#overlay-text").textContent = message;
  renderStatus();
}

/* Settings */

function applySettingsToUI() {
  const s = state.settings;
  for (const input of $$("[data-setting]")) {
    input.checked = Boolean(getPath(s, input.dataset.setting));
  }
  for (const input of $$("[data-field]")) {
    input.checked = cleanFields().includes(input.dataset.field);
  }
  for (const input of $$("input[name=duplicates]")) {
    input.checked = input.value === s.duplicates.mode;
  }
  for (const card of $$(".card")) {
    const toggle = $(".card-head [data-setting]", card);
    const on = toggle ? toggle.checked : true;
    card.classList.toggle("on", on && Boolean(toggle));
    card.classList.toggle("off", !on);
  }
  $("[data-setting='modernize.shield']").disabled = !cleanFields().includes("title");
  renderTags();
  renderFilesInfo();
  renderReview();
}

function settingChanged() {
  saveSettings();
  applySettingsToUI();
  schedule();
}

function enableSectionOf(element) {
  const card = element.closest(".card");
  const toggle = card && $(".card-head [data-setting]", card);
  if (toggle && !toggle.checked && !toggle.contains(element) && element !== toggle) {
    setPath(state.settings, toggle.dataset.setting, true);
  }
}

$("#options").addEventListener("change", (event) => {
  const input = event.target;
  if (input.dataset.setting) {
    setPath(state.settings, input.dataset.setting, input.checked);
  } else if (input.dataset.field) {
    const fields = new Set(cleanFields());
    if (input.checked) fields.add(input.dataset.field);
    else fields.delete(input.dataset.field);
    state.settings.modernize.fields = defaults.clean_fields.filter((f) => fields.has(f));
  } else if (input.name === "duplicates") {
    state.settings.duplicates.mode = input.value;
  } else {
    return;
  }
  if (input.closest(".card-body")) enableSectionOf(input);
  settingChanged();
});

$("#pane-preview").addEventListener("change", (event) => {
  if (event.target.dataset.setting) {
    setPath(state.settings, event.target.dataset.setting, event.target.checked);
    settingChanged();
  }
});

$("#link-scroll").addEventListener("change", (event) => {
  state.linkScroll = event.target.checked;
  if (state.linkScroll) syncScroll(panes[state.lastPane], panes[other(state.lastPane)]);
});

/* Remove fields */

function renderTags() {
  const container = $("#remove-tags");
  const input = $("#remove-input");
  $$(".tag", container).forEach((tag) => tag.remove());
  const used = new Set(state.response ? state.response.fields : []);
  for (const field of removeFields()) {
    const tag = document.createElement("span");
    tag.className = "tag" + (used.has(field) ? " used" : "");
    tag.title = used.has(field) ? "Present in your file" : "Not present in your file";
    tag.append(field);
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "×";
    button.setAttribute("aria-label", `Keep the field ${field}`);
    button.addEventListener("click", () => setRemoveFields(removeFields().filter((f) => f !== field)));
    tag.append(button);
    container.insertBefore(tag, input);
  }
  const suggestions = $("#field-suggestions");
  suggestions.replaceChildren(...[...used].filter((f) => !removeFields().includes(f))
    .map((f) => Object.assign(document.createElement("option"), { value: f })));
}

function setRemoveFields(fields) {
  state.settings.remove.fields = fields;
  state.settings.remove.enabled = true;
  settingChanged();
}

function addRemoveField(value) {
  const fields = value.split(/[\s,;]+/).map((f) => f.trim().toLowerCase()).filter(Boolean);
  const current = removeFields();
  const added = fields.filter((f) => !current.includes(f));
  if (added.length) setRemoveFields([...current, ...added]);
}

$("#remove-input").addEventListener("keydown", (event) => {
  const input = event.target;
  if ((event.key === "Enter" || event.key === ",") && input.value.trim()) {
    event.preventDefault();
    addRemoveField(input.value);
    input.value = "";
  } else if (event.key === "Backspace" && !input.value && removeFields().length) {
    setRemoveFields(removeFields().slice(0, -1));
  }
});
$("#remove-input").addEventListener("change", (event) => {
  if (event.target.value.trim()) {
    addRemoveField(event.target.value);
    event.target.value = "";
  }
});
$("#remove-tags").addEventListener("click", (event) => {
  if (event.target.id === "remove-tags") $("#remove-input").focus();
});
$("#remove-reset").addEventListener("click", () => setRemoveFields(null));

/* Files */

async function readFiles(files) {
  return Promise.all([...files].map(async (file) => ({ name: file.name, text: await file.text() })));
}

function setSources(sources) {
  state.sources = sources;
  state.decisions.clear();
  state.response = null;
  state.error = null;
  state.selected = null;
  document.body.classList.toggle("has-files", sources.length > 0);
  for (const pane of Object.values(panes)) {
    setPad(pane, 0, 0);
    pane.el.scrollTop = 0;
  }
  render();
  schedule(0);
}

async function openFiles(files, { add = true } = {}) {
  const read = await readFiles(files);
  const bbl = read.filter((f) => /\.bbl$/i.test(f.name));
  const bib = read.filter((f) => !/\.bbl$/i.test(f.name));
  if (bbl.length) setAuxFile("bbl", bbl[bbl.length - 1]);
  if (bib.length) setSources(add ? [...state.sources, ...bib] : bib);
}

function setAuxFile(kind, file) {
  state[kind] = file;
  if (file) state.settings[kind === "bbl" ? "filter" : "clean"].enabled = true;
  saveSettings();
  applySettingsToUI();
  schedule(0);
}

function pick(kind) {
  $(`#pick-${kind}`).click();
}

$("#pick-bib").addEventListener("change", async (event) => {
  await openFiles(event.target.files);
  event.target.value = "";
});
$("#pick-bbl").addEventListener("change", async (event) => {
  const [file] = await readFiles(event.target.files);
  if (file) setAuxFile("bbl", file);
  event.target.value = "";
});
$("#pick-abbr").addEventListener("change", async (event) => {
  const [file] = await readFiles(event.target.files);
  if (file) setAuxFile("abbr", file);
  event.target.value = "";
});

document.addEventListener("click", (event) => {
  const picker = event.target.closest("[data-pick]");
  if (picker) pick(picker.dataset.pick);
  const clear = event.target.closest("[data-clear]");
  if (clear) setAuxFile(clear.dataset.clear, null);
});

/* Paste */

const pasteDialog = $("#paste-dialog");
const looksLikeBib = (text) => /@\s*\w+\s*[{(]/.test(text);

function pastedName() {
  const names = new Set(state.sources.map((source) => source.name));
  let name = "pasted.bib";
  for (let i = 2; names.has(name); i++) name = `pasted-${i}.bib`;
  return name;
}

// Add pasted BibTeX as another bib file. Returns whether it was added.
function addPasted(text) {
  if (!looksLikeBib(text)) return false;
  const name = pastedName();
  setSources([...state.sources, { name, text }]);
  toast(`Added the pasted text as ${name}`);
  return true;
}

function openPasteDialog() {
  $("#paste-text").value = "";
  $("#paste-error").textContent = "";
  pasteDialog.showModal();
  $("#paste-text").focus();
}

function addFromDialog() {
  const text = $("#paste-text").value;
  if (addPasted(text)) pasteDialog.close();
  else $("#paste-error").textContent = "This does not look like BibTeX: no entry like @article{…} found.";
}

$("#paste-add").addEventListener("click", addFromDialog);
$("#paste-text").addEventListener("input", () => { $("#paste-error").textContent = ""; });
$("#paste-text").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) addFromDialog();
});
pasteDialog.addEventListener("click", (event) => {
  if (event.target === pasteDialog || event.target.closest("[data-dialog-close]")) pasteDialog.close();
});
document.addEventListener("click", (event) => {
  if (event.target.closest("[data-paste]")) openPasteDialog();
});

// Paste anywhere on the page, except into fields and dialogs
document.addEventListener("paste", async (event) => {
  if (event.target.closest("input, textarea, [contenteditable]") || document.querySelector("dialog[open]")) return;
  const data = event.clipboardData;
  if (data.files.length) {
    event.preventDefault();
    await openFiles(data.files);
    return;
  }
  const text = data.getData("text/plain");
  if (!text.trim()) return;
  event.preventDefault();
  if (!addPasted(text)) toast("The pasted text does not look like BibTeX");
});

if (/Mac|iPhone|iPad/.test(navigator.platform)) {
  $$(".paste-key").forEach((key) => { key.textContent = "⌘V"; });
}

$("#example").addEventListener("click", async () => {
  const response = await fetch("examples/old.bib");
  setSources([{ name: "old.bib", text: await response.text() }]);
});

function renderFiles() {
  const files = $("#files");
  files.replaceChildren();
  state.sources.forEach((source, idx) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    const count = state.response && state.response.sources[idx]
      ? state.response.sources[idx].entries.length : null;
    chip.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></svg>`;
    chip.append(source.name);
    if (count !== null) {
      const span = document.createElement("span");
      span.className = "count";
      span.textContent = `· ${count}`;
      chip.append(span);
    }
    const button = document.createElement("button");
    button.textContent = "×";
    button.title = `Close ${source.name}`;
    button.addEventListener("click", () => setSources(state.sources.filter((_, i) => i !== idx)));
    chip.append(button);
    files.append(chip);
  });
}

/* Menu to add another bib file */

const addButton = $("#add-button");
const addMenu = $("#add-menu");

function setAddMenu(open) {
  addMenu.hidden = !open;
  addButton.setAttribute("aria-expanded", String(open));
  if (open) $("button", addMenu).focus();
}

addButton.addEventListener("click", () => setAddMenu(addMenu.hidden));
document.addEventListener("click", (event) => {
  if (!addMenu.hidden && !event.target.closest("#add-wrap")) setAddMenu(false);
});
addMenu.addEventListener("click", (event) => {
  if (event.target.closest("[data-pick], [data-paste]")) setAddMenu(false);
});
addMenu.addEventListener("keydown", (event) => {
  const items = $$("[role=menuitem]", addMenu);
  const idx = items.indexOf(document.activeElement);
  if (event.key === "Escape") {
    setAddMenu(false);
    addButton.focus();
  } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    items[(idx + (event.key === "ArrowDown" ? 1 : items.length - 1)) % items.length].focus();
  }
});

function renderFilesInfo() {
  for (const kind of ["bbl", "abbr"]) {
    const file = state[kind];
    const name = $(`#${kind}-name`);
    name.textContent = file ? file.name : kind === "bbl" ? "No file" : "None";
    name.classList.toggle("set", Boolean(file));
    $(`[data-clear=${kind}]`).hidden = !file;
  }
  const info = $("#bbl-info");
  const cited = state.response && state.response.cited;
  info.classList.remove("warn");
  if (!state.bbl) {
    info.innerHTML = "Compile your document, then pick its <code>.bbl</code> file.";
  } else if (!state.settings.filter.enabled) {
    info.textContent = "Turned off.";
  } else if (cited) {
    const missing = cited.missing.length;
    info.innerHTML = `<strong>${cited.count}</strong> cited · <strong>${cited.kept}</strong> entries kept` +
      (missing ? ` · <strong>${missing}</strong> not in your files` : "");
    info.title = `Read from a ${cited.backend} .bbl file`;
    if (missing) {
      info.classList.add("warn");
      info.title += `. Not in your files: ${cited.missing.join(", ")}`;
    }
  } else {
    info.textContent = "Reading…";
  }
}

/* Drag and drop */

let dragDepth = 0;
window.addEventListener("dragenter", (event) => {
  if (![...event.dataTransfer.types].includes("Files")) return;
  dragDepth += 1;
  document.body.classList.add("dragging");
});
window.addEventListener("dragleave", () => {
  dragDepth = Math.max(0, dragDepth - 1);
  if (!dragDepth) document.body.classList.remove("dragging");
});
window.addEventListener("dragover", (event) => event.preventDefault());
window.addEventListener("drop", async (event) => {
  event.preventDefault();
  dragDepth = 0;
  document.body.classList.remove("dragging");
  if (event.dataTransfer.files.length) await openFiles(event.dataTransfer.files);
});

/* Rendering */

function lineHtml(number, text, cls = "", extra = "") {
  return `<div class="l${cls ? " " + cls : ""}"><span class="n">${number}</span>` +
    `<span class="t">${escapeHtml(text) || " "}</span>${extra}</div>`;
}

function badge(kind, text, attrs = "") {
  return `<span class="badge ${kind}"${attrs}>${escapeHtml(text)}</span>`;
}

function renderOriginal(outByOrigin, unresolved) {
  const r = state.response;
  const parts = [];
  state.sources.forEach((source, sourceIdx) => {
    const lines = splitLines(source.text);
    if (state.sources.length > 1) parts.push(lineHtml("", source.name, "sep"));
    const entries = r ? r.sources[sourceIdx].entries : [];
    let next = 0;
    for (const entry of entries) {
      const [first, last] = entry.lines;
      if (first < next) continue;
      for (let i = next; i < first; i++) parts.push(lineHtml(i + 1, lines[i]));
      const out = entry.origin && outByOrigin.get(entry.origin);
      const removed = entry.origin && r.removed[entry.origin];
      let cls = "entry";
      let label = "";
      if (!entry.origin) {
        cls += " gone";
        label = badge("err", "could not be read");
      } else if (removed) {
        cls += " gone";
        label = badge("rm", `removed · ${removed}`);
      } else {
        // An entry can be a possible duplicate and have a new ID at once
        if (unresolved.has(entry.origin)) {
          cls += " dup";
          label += badge("dup", "duplicate?", ` data-dup="${entry.origin}" title="Choose which entry to keep"`);
        }
        if (out && out.id_changed) label += badge("chg", `→ ${out.id}`);
      }
      const lineCls = new Array(last - first + 1).fill("");
      if (out) {
        for (const [field, [a, b]] of Object.entries(entry.fields)) {
          const kind = out.removed.includes(field) ? "rm" : out.changed.includes(field) ? "chg" : "";
          for (let i = a; kind && i <= b; i++) lineCls[i - first] = kind;
        }
        if (out.id_changed) lineCls[0] = "chg";
      }
      if (entry.origin === state.selected) cls += " selected";
      parts.push(`<div class="${cls}" data-origin="${entry.origin || ""}">`);
      for (let i = first; i <= last; i++) {
        parts.push(lineHtml(i + 1, lines[i] ?? "", lineCls[i - first], i === first ? label : ""));
      }
      parts.push("</div>");
      next = last + 1;
    }
    for (let i = next; i < lines.length; i++) parts.push(lineHtml(i + 1, lines[i]));
  });
  panes.original.content.innerHTML = parts.join("");
}

function renderPreview(unresolved) {
  const r = state.response;
  if (!r) {
    panes.preview.content.innerHTML = "";
    return;
  }
  const parts = [];
  r.entries.forEach((out, idx) => {
    const lines = out.text.split("\n");
    lines.pop();
    const lineCls = new Array(lines.length).fill("");
    for (const [field, [a, b]] of Object.entries(out.fields)) {
      const kind = out.added.includes(field) ? "add" : out.changed.includes(field) ? "chg" : "";
      for (let i = a; kind && i <= b; i++) lineCls[i] = kind;
    }
    let label = "";
    let cls = "entry";
    if (unresolved.has(out.origin)) {
      cls += " dup";
      label += badge("dup", "duplicate?", ` data-dup="${out.origin}" title="Choose which entry to keep"`);
    }
    if (out.id_changed) {
      lineCls[0] = "chg";
      label += badge("chg", `was ${out.original_id}`);
    }
    if (out.origin === state.selected) cls += " selected";
    parts.push(`<div class="${cls}" data-origin="${out.origin}">`);
    lines.forEach((text, i) => parts.push(lineHtml(out.line + i, text, lineCls[i], i === 0 ? label : "")));
    parts.push("</div>");
    if (idx < r.entries.length - 1) parts.push(lineHtml(out.line + lines.length, ""));
  });
  if (!r.entries.length) {
    parts.push(`<div class="l"><span class="n"></span><span class="t muted">No entries left with these settings.</span></div>`);
  }
  panes.preview.content.innerHTML = parts.join("");
}

function indexPane(pane) {
  pane.entries = $$(".entry", pane.el).filter((el) => el.dataset.origin);
  pane.byOrigin = new Map(pane.entries.map((el) => [el.dataset.origin, el]));
}

function render() {
  const r = state.response;
  const anchor = captureAnchor(panes[state.lastPane]);
  const outByOrigin = new Map(r ? r.entries.map((out) => [out.origin, out]) : []);
  const unresolved = new Set(r ? r.unresolved_pairs.flat() : []);
  renderOriginal(outByOrigin, unresolved);
  renderPreview(unresolved);
  indexPane(panes.original);
  indexPane(panes.preview);
  restoreAnchor(panes[state.lastPane], anchor);
  if (state.linkScroll) syncScroll(panes[state.lastPane], panes[other(state.lastPane)]);

  const overlay = $("#overlay");
  const waiting = state.sources.length && (!state.ready || !r);
  overlay.classList.toggle("show", Boolean(waiting || state.error));
  if (!state.error) overlay.classList.remove("error");
  if (waiting && state.ready) $("#overlay-text").textContent = "Working…";

  $("#copy").disabled = !r;
  $("#download").disabled = !r;
  renderFiles();
  renderFilesInfo();
  renderTags();
  renderReview();
  renderMeta();
  renderStatus();
  renderArxivState();
  if (dialog.open) renderDuplicate();
}

function renderMeta() {
  const r = state.response;
  const files = state.sources.length;
  const inCount = r ? r.sources.reduce((sum, s) => sum + s.entries.filter((e) => e.origin).length, 0) : null;
  $("#original-meta").textContent = [
    inCount === null ? null : plural(inCount, "entry", "entries"),
    files > 1 ? `${files} files combined` : state.sources[0]?.name,
  ].filter(Boolean).join(" · ");
  if (!r) {
    $("#preview-meta").textContent = "";
    return;
  }
  const changed = r.entries.filter((e) => e.id_changed || e.added.length || e.changed.length || e.removed.length).length;
  const removed = Object.keys(r.removed).length;
  $("#preview-meta").textContent = [
    plural(r.entries.length, "entry", "entries"),
    `${changed} changed`,
    removed ? `${removed} removed` : null,
  ].filter(Boolean).join(" · ");
}

const ICON_WARN = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 2 21h20z"/><path d="M12 10v5"/><path d="M12 18h.01"/></svg>`;
const ICON_INFO = `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><path d="M12 7h.01"/></svg>`;

function renderStatus() {
  const r = state.response;
  const counts = $("#status-counts");
  const messages = $("#status-messages");
  messages.replaceChildren();
  if (!r || !state.sources.length) {
    counts.textContent = state.sources.length ? "" : "No file opened";
  } else {
    const inCount = r.sources.reduce((sum, s) => sum + s.entries.filter((e) => e.origin).length, 0);
    counts.innerHTML = `<strong>${inCount}</strong> in → <strong>${r.entries.length}</strong> out`;
    for (const [level, text] of r.messages) {
      const msg = document.createElement("span");
      msg.className = `msg ${level}`;
      msg.title = text;
      msg.innerHTML = level === "warning" || level === "error" ? ICON_WARN : ICON_INFO;
      msg.append(text);
      if (/of duplicate entries kept/.test(text)) {
        const button = document.createElement("button");
        button.textContent = "Review";
        button.addEventListener("click", () => openDuplicates());
        msg.append(" ", button);
      }
      messages.append(msg);
    }
  }
  if (state.error) {
    const msg = document.createElement("span");
    msg.className = "msg error";
    msg.innerHTML = ICON_WARN;
    msg.append(state.error);
    messages.prepend(msg);
  }
}

function renderReview() {
  const button = $("#review");
  const r = state.response;
  const pairs = r && r.duplicate_pairs;
  const choose = state.settings.duplicates.mode === "choose";
  button.hidden = !(choose && pairs && pairs.length);
  if (!button.hidden) {
    const open = r.unresolved_pairs.length;
    button.textContent = open ? `Review ${plural(open, "pair")}` : `Review (${pairs.length})`;
  }
}

/* Selection and linked scrolling */

const other = (name) => (name === "original" ? "preview" : "original");

function entryAt(pane, y) {
  const entries = pane.entries;
  let lo = 0;
  let hi = entries.length - 1;
  let found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (entries[mid].offsetTop <= y) {
      found = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return found;
}

function captureAnchor(pane) {
  const idx = entryAt(pane, pane.el.scrollTop);
  if (idx < 0) return { origin: null, offset: pane.el.scrollTop };
  const el = pane.entries[idx];
  return { origin: el.dataset.origin, offset: pane.el.scrollTop - el.offsetTop };
}

function restoreAnchor(pane, anchor) {
  const el = anchor.origin && pane.byOrigin.get(anchor.origin);
  pane.el.scrollTop = el ? el.offsetTop + anchor.offset : anchor.offset;
}

/* Positions without the blank space above the content ("view") */

const contentTop = (pane, el) => el.offsetTop - pane.top;
const view = (pane) => pane.el.scrollTop - pane.top;
const maxView = (pane) =>
  Math.max(0, pane.el.scrollHeight - pane.top - pane.bottom - pane.el.clientHeight);
const viewOffset = (pane, el) => el.offsetTop - pane.el.scrollTop;

function setPad(pane, top, bottom) {
  if (top !== pane.top) {
    pane.top = top;
    pane.padTop.style.height = `${top}px`;
  }
  if (bottom !== pane.bottom) {
    pane.bottom = bottom;
    pane.padBottom.style.height = `${bottom}px`;
  }
}

// Scroll the pane to a view position, with blank space where there is no
// content, e.g., a negative view shows blank space above the first line
function setView(pane, position) {
  const max = maxView(pane);
  setPad(pane, Math.max(0, Math.round(-position)), Math.max(0, Math.round(position - max)));
  setScroll(pane, position + pane.top);
}

// Remove the blank space when it is scrolled out of view
function trimPads(pane) {
  const position = view(pane);
  const top = position >= 0 ? 0 : pane.top;
  const bottom = position <= maxView(pane) ? 0 : pane.bottom;
  if (top === pane.top && bottom === pane.bottom) return;
  setPad(pane, top, bottom);
  setScroll(pane, position + top);
}

const isVisible = (pane, el) =>
  viewOffset(pane, el) < pane.el.clientHeight && viewOffset(pane, el) + el.offsetHeight > 0;

let syncing = null;

function syncScroll(from, to) {
  if (!from.entries.length || !to.entries.length) return;
  // Keep the selected entry at the same height on both sides while it is visible
  const selected = state.selected && from.byOrigin.get(state.selected);
  const counterpart = state.selected && to.byOrigin.get(state.selected);
  if (selected && counterpart && isVisible(from, selected)) {
    setView(to, contentTop(to, counterpart) - viewOffset(from, selected));
    return;
  }
  const y = from.el.scrollTop;
  let idx = entryAt(from, y);
  if (idx < 0) {
    setView(to, 0);
    return;
  }
  const el = from.entries[idx];
  const fraction = Math.min(1, (y - el.offsetTop) / Math.max(1, el.offsetHeight));
  // Removed entries have no counterpart: use the next entry that has one
  let target = to.byOrigin.get(el.dataset.origin);
  const exact = Boolean(target);
  while (!target && ++idx < from.entries.length) {
    target = to.byOrigin.get(from.entries[idx].dataset.origin);
  }
  if (!target) return;
  const position = contentTop(to, target) + (exact ? fraction * target.offsetHeight : 0);
  setView(to, Math.min(position, maxView(to)));
}

function setScroll(pane, top) {
  if (Math.abs(pane.el.scrollTop - top) < 1) return;
  syncing = pane;
  pane.el.scrollTop = top;
  requestAnimationFrame(() => { if (syncing === pane) syncing = null; });
}

for (const name of ["original", "preview"]) {
  const pane = panes[name];
  pane.el.addEventListener("scroll", () => {
    clearTimeout(pane.trimTimer);
    pane.trimTimer = setTimeout(() => trimPads(pane), 250);
    if (syncing === pane) return;
    state.lastPane = name;
    if (state.linkScroll) syncScroll(pane, panes[other(name)]);
  }, { passive: true });
  pane.el.addEventListener("click", (event) => {
    const dup = event.target.closest("[data-dup]");
    if (dup) {
      openDuplicates(dup.dataset.dup);
      return;
    }
    const entry = event.target.closest(".entry");
    if (!entry || !entry.dataset.origin || !window.getSelection().isCollapsed) return;
    select(entry.dataset.origin, name);
  });
}

// Select an entry on one side and show it at the same height on the other
function select(origin, fromName) {
  state.selected = state.selected === origin ? null : origin;
  state.lastPane = fromName;
  for (const pane of Object.values(panes)) {
    pane.entries.forEach((el) => el.classList.toggle("selected", el.dataset.origin === state.selected));
  }
  if (!state.selected) return;
  const from = panes[fromName];
  const to = panes[other(fromName)];
  const el = from.byOrigin.get(origin);
  const target = to.byOrigin.get(origin);
  if (el && target) setView(to, contentTop(to, target) - viewOffset(from, el));
}

/* Duplicates dialog */

const dialog = $("#dup-dialog");
let dupIndex = 0;

function openDuplicates(origin) {
  const pairs = (state.response && state.response.duplicate_pairs) || [];
  if (!pairs.length) return;
  const unresolved = pairs.findIndex(([a, b]) => !state.decisions.has(`${a}|${b}`));
  dupIndex = origin ? Math.max(0, pairs.findIndex((pair) => pair.includes(origin)))
    : Math.max(0, unresolved);
  renderDuplicate();
  if (!dialog.open) dialog.showModal();
}

function renderDuplicate() {
  const r = state.response;
  const pairs = (r && r.duplicate_pairs) || [];
  if (!pairs.length) {
    dialog.close();
    return;
  }
  dupIndex = Math.min(dupIndex, pairs.length - 1);
  const pair = pairs[dupIndex];
  const key = pair.join("|");
  const decided = state.decisions.has(key);
  const decision = state.decisions.get(key);
  const texts = pair.map((origin) => r.pair_entries[origin].split("\n").slice(0, -1));
  const lineSets = texts.map((lines) => new Set(lines.slice(1)));
  const undecided = pairs.filter(([a, b]) => !state.decisions.has(`${a}|${b}`)).length;
  $("#dup-counter").textContent = `Pair ${dupIndex + 1} of ${pairs.length}` +
    (undecided ? ` · ${undecided} not decided` : " · all decided");
  $$(".dup-side", dialog).forEach((side, i) => {
    const origin = pair[i];
    const lines = texts[i];
    const otherLines = lineSets[1 - i];
    $(".dup-id", side).textContent = (lines[0].match(/\{(.*),$/) || [, origin])[1];
    $(".code", side).innerHTML = lines.map((text, n) =>
      lineHtml(n + 1, text, n > 0 && !otherLines.has(text) ? "only" : "")).join("");
    const removedElsewhere = r.removed[origin] && decision !== origin;
    side.classList.toggle("removed", decision === origin || Boolean(removedElsewhere));
    side.classList.toggle("kept", decided && decision !== origin && !removedElsewhere);
    $(".dup-state", side).textContent = removedElsewhere ? "removed with another pair"
      : !decided ? "not decided — kept for now" : decision === origin ? "will be removed" : "kept";
    $("[data-remove]", side).disabled = decision === origin;
  });
  $("#dup-keep").disabled = decided && decision === null;
  $("#dup-prev").disabled = dupIndex === 0;
  $("#dup-next").disabled = dupIndex === pairs.length - 1;
}

function decide(remove) {
  const pairs = state.response.duplicate_pairs;
  state.decisions.set(pairs[dupIndex].join("|"), remove);
  schedule(0);
  const next = pairs.findIndex(([a, b], i) => i > dupIndex && !state.decisions.has(`${a}|${b}`));
  if (next >= 0) dupIndex = next;
  renderDuplicate();
}

dialog.addEventListener("click", (event) => {
  if (event.target === dialog || event.target.closest("[data-dialog-close]")) dialog.close();
  const remove = event.target.closest("[data-remove]");
  if (remove) decide(state.response.duplicate_pairs[dupIndex][Number(remove.dataset.remove)]);
});
dialog.addEventListener("keydown", (event) => {
  if (event.key === "1" || event.key === "2") decide(state.response.duplicate_pairs[dupIndex][Number(event.key) - 1]);
  else if (event.key === "0" || event.key.toLowerCase() === "k") decide(null);
  else if (event.key === "ArrowLeft" && dupIndex > 0) { dupIndex -= 1; renderDuplicate(); }
  else if (event.key === "ArrowRight") { dupIndex += 1; renderDuplicate(); }
});
$("#dup-keep").addEventListener("click", () => decide(null));
$("#dup-prev").addEventListener("click", () => { dupIndex -= 1; renderDuplicate(); });
$("#dup-next").addEventListener("click", () => { dupIndex += 1; renderDuplicate(); });
$("#review").addEventListener("click", () => openDuplicates());

/* arXiv */

function missingEprints() {
  const r = state.response;
  if (!r || !state.settings.modernize.enabled || !state.settings.modernize.arxiv) return [];
  return r.eprints.filter((e) => !(e in state.arxiv) && !state.arxivTried.has(e));
}

async function maybeFetchArxiv() {
  const eprints = missingEprints();
  if (!eprints.length || state.arxivBusy) return;
  state.arxivBusy = true;
  renderArxivState();
  let found = 0;
  try {
    for (let i = 0; i < eprints.length; i += 50) {
      const chunk = eprints.slice(i, i + 50);
      chunk.forEach((e) => state.arxivTried.add(e));
      const url = "https://export.arxiv.org/api/query?id_list=" +
        chunk.map(encodeURIComponent).join(",") + `&max_results=${chunk.length}`;
      const response = await fetch(url);
      if (!response.ok) throw new Error(`arXiv answered with ${response.status}`);
      const xml = new DOMParser().parseFromString(await response.text(), "application/xml");
      const wanted = new Map(chunk.map((e) => [e.replace(/v\d+$/, ""), e]));
      for (const entry of xml.getElementsByTagName("entry")) {
        const id = (entry.getElementsByTagName("id")[0]?.textContent || "").trim()
          .replace(/^https?:\/\/arxiv\.org\/abs\//, "").replace(/v\d+$/, "");
        const category = entry.getElementsByTagNameNS("http://arxiv.org/schemas/atom", "primary_category")[0]
          ?.getAttribute("term");
        if (wanted.has(id) && category) {
          state.arxiv[wanted.get(id)] = category;
          found += 1;
        }
      }
    }
    saveJson(ARXIV_KEY, state.arxiv);
    if (found) schedule(0);
  } catch (err) {
    toast(`Could not look up the arXiv categories: ${err.message}`);
  } finally {
    state.arxivBusy = false;
    renderArxivState();
  }
}

function renderArxivState() {
  const label = $("#arxiv-state");
  const r = state.response;
  if (state.arxivBusy) label.textContent = "(looking up…)";
  else if (r && state.settings.modernize.arxiv && r.eprints.length) {
    const known = r.eprints.filter((e) => e in state.arxiv).length;
    label.textContent = `(${known}/${r.eprints.length})`;
  } else label.textContent = "";
}

/* Actions */

function downloadName() {
  if (state.sources.length === 1) return `clean-${state.sources[0].name.replace(/\.bib$/i, "")}.bib`;
  return "combined.bib";
}

function download() {
  if (!state.response) return;
  const blob = new Blob([state.response.text], { type: "text/x-bibtex;charset=utf-8" });
  const link = Object.assign(document.createElement("a"), {
    href: URL.createObjectURL(blob), download: downloadName(),
  });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

$("#download").addEventListener("click", download);
$("#copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(state.response.text);
    toast("Copied the result to the clipboard");
  } catch {
    toast("Could not copy to the clipboard");
  }
});
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "s") {
    event.preventDefault();
    download();
  }
});

function encodeSettings(settings) {
  const bytes = new TextEncoder().encode(JSON.stringify(settings));
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function decodeSettings(text) {
  const binary = atob(text.replace(/-/g, "+").replace(/_/g, "/"));
  return JSON.parse(new TextDecoder().decode(Uint8Array.from(binary, (c) => c.charCodeAt(0))));
}

$("#share").addEventListener("click", async () => {
  const url = new URL(location.href);
  url.hash = `settings=${encodeSettings(state.settings)}`;
  try {
    await navigator.clipboard.writeText(url.href);
    toast("Link copied. It contains your settings, not your files.");
  } catch {
    prompt("Copy this link. It contains your settings, not your files.", url.href);
  }
});

function loadSharedSettings() {
  const match = location.hash.match(/settings=([\w-]+)/);
  if (!match) return;
  try {
    state.settings = validSettings(merge(DEFAULT_SETTINGS, decodeSettings(match[1])));
    saveSettings();
    toast("Loaded the shared settings");
  } catch {
    toast("Could not read the shared settings");
  }
  history.replaceState(null, "", location.pathname + location.search);
}

function applyTheme(theme) {
  if (theme) document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
}

$("#theme").addEventListener("click", () => {
  const dark = document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  const theme = dark ? "light" : "dark";
  applyTheme(theme);
  try { localStorage.setItem(THEME_KEY, theme); } catch { /* private mode */ }
});

/* Start */

try { applyTheme(localStorage.getItem(THEME_KEY)); } catch { /* private mode */ }
loadSharedSettings();
applySettingsToUI();
render();
