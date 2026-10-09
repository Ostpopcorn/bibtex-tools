// BibTeX Tools web app: the settings and both panes. The work is done by
// bibtextools (Python) in worker.js.

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

// Bumped when the settings change their shape. Settings of older versions
// are converted, see `fromV2`.
const SETTINGS_KEY = "bibtextools.settings.v3";
const SETTINGS_V2_KEY = "bibtextools.settings.v2";
const ARXIV_KEY = "bibtextools.arxiv.v1";
const ARXIV_CONSENT_KEY = "bibtextools.arxiv-allowed.v1";
const THEME_KEY = "bibtextools.theme";
const SIDEBAR_KEY = "bibtextools.sidebar-hidden.v1";
const SEARCH_FILTER_KEY = "bibtextools.search-only-matches.v1";
const FOLD_KEY = "bibtextools.fold.v1";
const DUPLICATE_MODES = ["keep", "remove-shorter", "choose"];
const ARXIV_STYLES = ["keep", "eprint", "journal"];
const TITLE_MODES = ["keep", "acronyms", "whole"];
const FORMATS = ["biblatex", "bibtex"];
const FORMAT_NAMES = { biblatex: "biblatex", bibtex: "BibTeX" };
// Settings that BibTeX styles cannot use, with the reason shown on hover. In
// BibTeX mode they are shown off and not applied, but keep their value.
const BIBLATEX_ONLY = {
  eprintStyle: "standard BibTeX styles ignore eprint and archivePrefix, so the preprint would show no arXiv ID.",
  lookup: "standard BibTeX styles ignore primaryClass.",
};
const ARXIV_STYLE_HINTS = {
  keep: "",
  eprint: "<code>@misc</code> with <code>eprint = {2009.09852}</code>, like arXiv. Published papers are not changed.",
  journal: "<code>@article</code> with <code>journal = {arXiv preprint arXiv:2009.09852}</code>, like Google Scholar. Published papers are not changed.",
};
// Converting the fields, which follows the output
const CONVERT = {
  biblatex: {
    label: "Convert to biblatex fields",
    example: "E.g., <code>journal</code> → <code>journaltitle</code>, <code>@phdthesis</code> → <code>@thesis</code>",
    title: "Use the names of biblatex, e.g., journal → journaltitle, address → location, school → institution, " +
      "@phdthesis → @thesis, and @techreport → @report. biber reads the BibTeX names as well.",
  },
  bibtex: {
    label: "Convert to BibTeX fields",
    example: "E.g., <code>journaltitle</code> → <code>journal</code>, <code>@online</code> → <code>@misc</code>",
    title: "Use the names that BibTeX reads, e.g., journaltitle → journal, location → address, " +
      "date → year and month, @online → @misc, and @thesis → @phdthesis. BibTeX ignores the biblatex names.",
  },
};
// Writing the months, which follows the output
const MONTHS = {
  biblatex: {
    label: "Write months as numbers",
    example: "E.g., <code>jul</code> → <code>7</code>",
    title: "biblatex reads the month as a number, and prints it in the language of your document.",
  },
  bibtex: {
    label: "Write months as abbreviations",
    example: "E.g., <code>{August}</code> → <code>aug</code>",
    title: "BibTeX styles define jan to dec, and print them in their own way, e.g., as “Aug.” or “August”. " +
      "A month in braces is printed as it is, e.g., “aug”.",
  },
};
const TITLE_HINTS = {
  keep: "Titles stay as they are in your files.",
  acronyms: "Braces around acronyms, e.g., <code>The {IEEE} Standard</code>, so that styles keep their case.",
  whole: "Braces around the whole title, e.g., <code>{The IEEE Standard}</code>, so that styles keep its case.",
};

// Replaced by the defaults of bibtextools once Python is ready
let defaults = {
  remove_fields: ["abstract", "annote", "bdsk-url-1", "date-added", "date-modified", "file", "owner", "timestamp"],
  clean_fields: ["pages", "month", "eprint", "author"],
};

// Every setting works on its own. Lists of fields are null for the defaults
// of bibtextools.
const DEFAULT_SETTINGS = {
  format: "biblatex",          // the output is for biblatex or BibTeX
  cited: { enabled: false },   // keep only the entries cited in the .bbl file
  strings: { enabled: false }, // expand the @string abbreviations
  duplicates: { mode: "choose" },
  fields: { convert: false, clean: null, titles: "whole", iso4: false, unicode: false },
  arxiv: { style: "keep", lookup: false },
  keys: { rename: true, generate: false },
  remove: { fields: null },
  // The output is always sorted by ID. The preview keeps the order of the
  // files by default, so that linked scrolling moves both panes together.
  sortPreview: false,
};

// The settings before version 3, where the switch of a group, e.g.,
// Modernize, turned off all of its settings
const V2_SETTINGS = {
  filter: { enabled: false },
  clean: { enabled: false, unicode: false },
  modernize: { enabled: true, fields: null, shield: true, iso4: false, ids: false, arxiv: false, arxivStyle: "keep" },
  remove: { enabled: true, fields: null },
  duplicates: { mode: "choose", rename: true },
  sortPreview: false,
};
const V2_CLEAN_FIELDS = ["pages", "month", "eprint", "title", "author"];

const state = {
  settings: loadSettings(),
  sources: [],          // {name, text} of the bib files
  bbl: null,            // {name, text}
  bblBackend: null,     // "biblatex" or "bibtex" if the .bbl file is from one of them
  abbr: null,           // {name, text}
  decisions: new Map(), // "origin|origin" of a duplicate pair -> origin to remove, or null to keep both
  arxiv: loadJson(ARXIV_KEY, {}), // eprint -> primary category
  arxivAllowed: loadJson(ARXIV_CONSENT_KEY, false), // the lookup on arXiv was allowed
  arxivTried: new Set(),
  arxivBusy: false,
  response: null,
  runId: 0,
  ready: false,
  busy: false,
  error: null,
  selected: null,
  linkScroll: true,
  fold: loadJson(FOLD_KEY, false) === true, // fold the unchanged entries
  unfolded: new Set(),  // origins of the entries that you unfolded
  lastPane: "preview",
};

// Each pane has blank space above and below its content, which lets an entry
// be shown at any height, e.g., to align it with the selected entry
function makePane(el) {
  const [padTop, content, padBottom] = ["pad", "content", "pad"].map((cls) =>
    Object.assign(document.createElement("div"), { className: cls }));
  // Shown while searching without a match
  const empty = Object.assign(document.createElement("p"), {
    className: "search-empty", hidden: true, textContent: "No entries match the search.",
  });
  el.append(padTop, content, padBottom, empty);
  return { el, content, padTop, padBottom, empty, top: 0, bottom: 0, all: [], allByOrigin: new Map(),
           entries: [], byOrigin: new Map(), folds: [], last: 0, expected: null, link: null };
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
  if (!ARXIV_STYLES.includes(settings.arxiv.style)) {
    settings.arxiv.style = DEFAULT_SETTINGS.arxiv.style;
  }
  if (!TITLE_MODES.includes(settings.fields.titles)) {
    settings.fields.titles = DEFAULT_SETTINGS.fields.titles;
  }
  if (!FORMATS.includes(settings.format)) settings.format = DEFAULT_SETTINGS.format;
  return settings;
}

// Convert settings of version 2, so that they give the same result
function fromV2(stored) {
  const old = merge(V2_SETTINGS, stored);
  const modern = old.modernize;
  const on = modern.enabled;
  const fields = modern.fields ?? V2_CLEAN_FIELDS;
  const titles = on && fields.includes("title");
  return validSettings({
    format: "biblatex",
    cited: { enabled: old.filter.enabled },
    strings: { enabled: old.clean.enabled },
    duplicates: { mode: old.duplicates.mode },
    fields: {
      convert: false,
      clean: !on ? [] : modern.fields === null ? null : fields.filter((f) => f !== "title"),
      titles: !titles ? "keep" : modern.shield ? "whole" : "acronyms",
      iso4: on && modern.iso4,
      unicode: old.clean.enabled && old.clean.unicode,
    },
    arxiv: { style: on ? modern.arxivStyle : "keep", lookup: on && modern.arxiv },
    keys: { rename: old.duplicates.rename, generate: on && modern.ids },
    remove: { fields: old.remove.enabled ? old.remove.fields : [] },
    sortPreview: old.sortPreview,
  });
}

function loadSettings() {
  const stored = loadJson(SETTINGS_KEY, null);
  if (stored) return validSettings(merge(DEFAULT_SETTINGS, stored));
  const old = loadJson(SETTINGS_V2_KEY, null);
  if (!old) return structuredClone(DEFAULT_SETTINGS);
  const settings = fromV2(old);
  saveJson(SETTINGS_KEY, settings);
  return settings;
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
const cleanFields = (settings = state.settings) => settings.fields.clean ?? defaults.clean_fields;

// The backend of a .bbl file like `parse_bbl_keys` in Python: biblatex
// writes \entry{key}, and BibTeX \bibitem{key}. Null if it is not clear.
function bblBackend(text) {
  const biblatex = /\\entry\{/.test(text);
  const bibtex = /\\bibitem(?![a-zA-Z])/.test(text);
  return biblatex === bibtex ? null : biblatex ? "biblatex" : "bibtex";
}

// The output is for biblatex or BibTeX: as the .bbl file says, or else as
// chosen
const outputFormat = () => (state.bbl && state.bblBackend) || state.settings.format;

// The settings that are applied: in BibTeX mode, without the settings that
// BibTeX styles cannot use
function effectiveSettings() {
  const s = structuredClone(state.settings);
  s.format = outputFormat();
  // New keys would break the citations of the .bbl file
  if (s.cited.enabled && state.bbl) s.keys.generate = false;
  if (s.format === "bibtex") {
    if (s.arxiv.style === "eprint") s.arxiv.style = "keep";
    s.arxiv.lookup = false;
  }
  return s;
}

/* Python worker */

const worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });

worker.onmessage = ({ data }) => {
  if (data.type === "progress") {
    setEngine("loading", data.text);
    $("#overlay-text").textContent = data.text;
  } else if (data.type === "ready") {
    defaults = data.defaults;
    $("#about-version").textContent = `bibtextools ${data.version} · Pyodide ${data.pyodide}`;
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
  const s = effectiveSettings();
  return {
    sources: state.sources,
    bbl: s.cited.enabled && state.bbl ? state.bbl.text : null,
    abbr: s.strings.enabled && state.abbr ? state.abbr.text : null,
    options: {
      clean_fields: cleanFields(s),
      titles: s.fields.titles,
      iso4: s.fields.iso4,
      replace_unicode: s.fields.unicode,
      arxiv: s.arxiv.lookup,
      arxiv_style: s.arxiv.style !== "keep" ? s.arxiv.style : null,
      generate_keys: s.keys.generate,
      rename_duplicate_keys: s.keys.rename,
      remove_fields: removeFields(),
      duplicates: s.duplicates.mode,
      decisions: [...state.decisions].map(([pair, remove]) => [pair.split("|"), remove]),
      output: s.format,
      convert_fields: s.fields.convert,
      sort_by_id: true,
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

// Turn a setting off with the reason on hover, or on again with its own hint
function setAvailable(input, reason) {
  const label = input.closest("label");
  label.dataset.title ??= label.title;
  input.disabled = Boolean(reason);
  label.classList.toggle("off", Boolean(reason));
  input.closest(".opt")?.classList.toggle("off", Boolean(reason));
  label.title = reason || label.dataset.title;
}

function applySettingsToUI() {
  // Settings that cannot be used show as off, but keep their value
  const s = effectiveSettings();
  const bibtex = s.format === "bibtex";
  const notForBibtex = (reason) => (bibtex ? `Not available for BibTeX: ${reason}` : "");
  for (const input of $$("[data-setting]")) {
    input.checked = Boolean(getPath(s, input.dataset.setting));
  }
  for (const input of $$("[data-field]")) {
    input.checked = cleanFields(s).includes(input.dataset.field);
  }
  const radios = { format: s.format, duplicates: s.duplicates.mode, "arxiv-style": s.arxiv.style, titles: s.fields.titles };
  for (const [name, value] of Object.entries(radios)) {
    for (const input of $$(`input[name=${name}]`)) input.checked = input.value === value;
  }
  // In BibTeX mode, the settings that BibTeX styles cannot use
  setAvailable($("input[name=arxiv-style][value=eprint]"), notForBibtex(BIBLATEX_ONLY.eprintStyle));
  setAvailable($("[data-setting='arxiv.lookup']"), notForBibtex(BIBLATEX_ONLY.lookup));
  renderFormat();
  const convert = CONVERT[s.format];
  $("#convert-label").textContent = convert.label;
  $("#convert-hint").innerHTML = convert.example;
  for (const rules of $$("[data-rules]")) rules.hidden = rules.dataset.rules !== s.format;
  $("#convert-label").closest("label").title = convert.title;
  const months = MONTHS[s.format];
  $("#month-label").textContent = months.label;
  $("#month-hint").innerHTML = months.example;
  $("#month-label").closest("label").title = months.title;
  const hint = $("#arxiv-style-hint");
  hint.innerHTML = ARXIV_STYLE_HINTS[s.arxiv.style];
  hint.hidden = !hint.innerHTML;
  $("#titles-hint").innerHTML = TITLE_HINTS[s.fields.titles];
  // New keys would break the citations of the .bbl file
  const filtering = s.cited.enabled && Boolean(state.bbl);
  setAvailable($("[data-setting='keys.generate']"),
    filtering ? "Off while keeping only cited entries, since the keys must stay the cited ones" : "");
  $("#generate-keys-hint").innerHTML = filtering
    ? "Off while keeping only cited entries, since the keys must stay the cited ones."
    : "E.g., <code>Shannon1948mathematical</code>";
  renderTags();
  renderFilesInfo();
  renderReview();
}

// The switch between biblatex and BibTeX, which a .bbl file sets
function renderFormat() {
  const locked = Boolean(state.bbl && state.bblBackend);
  const format = outputFormat();
  for (const input of $$("input[name=format]")) {
    setAvailable(input, locked ? `Set by your .bbl file. Remove it to choose.` : "");
  }
  const note = $("#format-note");
  note.hidden = !locked;
  if (locked) {
    $("#format-note-text").innerHTML = `Your <code>.bbl</code> file is from <strong>${FORMAT_NAMES[format]}</strong>, ` +
      `so the output is for ${FORMAT_NAMES[format]}.`;
  }
  $("#format-hint").textContent = format === "bibtex"
    ? "Settings that BibTeX styles cannot use are off. Hover over them to see why." : "";
  $("#format-hint").hidden = !$("#format-hint").textContent;
}

function settingChanged() {
  saveSettings();
  applySettingsToUI();
  schedule();
}

$("#options").addEventListener("change", (event) => {
  const input = event.target;
  if (input.dataset.setting === "arxiv.lookup" && input.checked) {
    // The lookup uses the internet, so it is only turned on after asking
    input.checked = false;
    askArxiv().then((allowed) => {
      if (!allowed) return;
      input.checked = true;
      state.settings.arxiv.lookup = true;
      settingChanged();
    });
    return;
  }
  if (input.dataset.setting) {
    setPath(state.settings, input.dataset.setting, input.checked);
  } else if (input.dataset.field) {
    const fields = new Set(cleanFields());
    if (input.checked) fields.add(input.dataset.field);
    else fields.delete(input.dataset.field);
    state.settings.fields.clean = defaults.clean_fields.filter((f) => fields.has(f));
  } else if (input.name === "duplicates") {
    state.settings.duplicates.mode = input.value;
  } else if (input.name === "arxiv-style") {
    state.settings.arxiv.style = input.value;
  } else if (input.name === "titles") {
    state.settings.fields.titles = input.value;
  } else if (input.name === "format") {
    state.settings.format = input.value;
  } else {
    return;
  }
  settingChanged();
});

$("#pane-preview").addEventListener("change", (event) => {
  if (event.target.dataset.setting) {
    setPath(state.settings, event.target.dataset.setting, event.target.checked);
    // Sorting the preview does not change the output, so Python is not needed
    if (event.target.dataset.setting === "sortPreview") {
      saveSettings();
      if (state.response) render();
      return;
    }
    settingChanged();
  }
});

function renderLinkScroll() {
  const button = $("#link-scroll");
  button.setAttribute("aria-pressed", String(state.linkScroll));
  button.parentElement.classList.toggle("linked", state.linkScroll);
  button.title = state.linkScroll
    ? "Scrolling is linked: both sides show the same entries. Click to scroll them separately."
    : "Scrolling is not linked. Click to scroll both sides together.";
}

$("#link-scroll").addEventListener("click", () => {
  state.linkScroll = !state.linkScroll;
  renderLinkScroll();
  if (state.linkScroll) align(panes[state.lastPane], panes[other(state.lastPane)]);
});
renderLinkScroll();

/* Sidebar with the settings */

// On wide screens, the settings are next to the panes and can be hidden to
// a bar on the left, which is remembered. On narrow screens, they are hidden
// to the bar and open over the panes.
const narrow = matchMedia("(max-width: 1100px)");
const sidebar = { hidden: loadJson(SIDEBAR_KEY, false) === true, open: false };

function renderSidebar() {
  const shown = narrow.matches ? sidebar.open : !sidebar.hidden;
  document.body.classList.toggle("settings-shown", shown);
  document.body.classList.toggle("settings-overlay", narrow.matches && shown);
  $("#sidebar-show").setAttribute("aria-expanded", String(shown));
}

function showSettings(show) {
  if (narrow.matches) {
    sidebar.open = show;
  } else {
    sidebar.hidden = !show;
    saveJson(SIDEBAR_KEY, sidebar.hidden);
  }
  renderSidebar();
  $(show ? "#sidebar-hide" : "#sidebar-show").focus();
}

$("#rail").addEventListener("click", () => showSettings(true));
$("#sidebar-hide").addEventListener("click", () => showSettings(false));
$("#sidebar-backdrop").addEventListener("click", () => showSettings(false));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && narrow.matches && sidebar.open && !document.querySelector("dialog[open]")) {
    showSettings(false);
  }
});
narrow.addEventListener("change", () => {
  sidebar.open = false;
  renderSidebar();
});
renderSidebar();

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
  state.unfolded.clear();
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
  if (kind === "bbl") state.bblBackend = file ? bblBackend(file.text) : null;
  if (file) state.settings[kind === "bbl" ? "cited" : "strings"].enabled = true;
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
const PASTE_KINDS = {
  bib: {
    title: "Paste BibTeX",
    help: "Paste the content of a bib file, e.g., copied from Google Scholar or your reference manager.",
    placeholder: "@article{key,\n  author = {…},\n  title = {…},\n}",
    error: "This does not look like BibTeX: no entry like @article{…} found.",
  },
  bbl: {
    title: "Paste a .bbl file",
    help: "Paste the content of the .bbl file that LaTeX creates next to your document.",
    placeholder: "\\entry{key}{article}{}\n…\n\nor\n\n\\bibitem{key}\n…",
    error: "This does not look like a .bbl file: no \\entry{…} or \\bibitem{…} found.",
  },
  abbr: {
    title: "Paste abbreviations",
    help: "Paste @string definitions, e.g., the content of IEEEabbr.bib.",
    placeholder: '@string{IEEE_J_COM = "IEEE Trans. Commun."}',
    error: "No abbreviations found: paste definitions like @string{name = \"…\"}.",
  },
};
let pasteKind = "bib";

// What pasted text is: bib entries, abbreviations (@string only), or a .bbl file
function pastedKinds(text) {
  const types = [...text.matchAll(/@\s*(\w+)\s*[{(]/g)].map((match) => match[1].toLowerCase());
  return {
    bib: types.some((type) => !["string", "comment", "preamble"].includes(type)),
    abbr: types.includes("string"),
    bbl: /\\entry\s*\{|\\bibitem\b/.test(text),
  };
}

function pastedName() {
  const names = new Set(state.sources.map((source) => source.name));
  let name = "pasted.bib";
  for (let i = 2; names.has(name); i++) name = `pasted-${i}.bib`;
  return name;
}

// Add pasted text as a bib file, a .bbl file, or abbreviations. Returns
// whether it was added.
function addPasted(kind, text) {
  if (!pastedKinds(text)[kind]) return false;
  if (kind === "bib") {
    const name = pastedName();
    setSources([...state.sources, { name, text }]);
    toast(`Added the pasted text as ${name}`);
  } else if (kind === "bbl") {
    setAuxFile("bbl", { name: "pasted.bbl", text });
    toast("Added the pasted .bbl file: only cited entries are kept");
  } else {
    setAuxFile("abbr", { name: "pasted abbreviations", text });
    toast("Added the pasted abbreviations, which are expanded now");
  }
  return true;
}

function openPasteDialog(kind = "bib") {
  const config = PASTE_KINDS[kind];
  pasteKind = kind;
  $("#paste-title").textContent = config.title;
  $("#paste-help").textContent = config.help;
  $("#paste-text").placeholder = config.placeholder;
  $("#paste-text").value = "";
  $("#paste-error").textContent = "";
  pasteDialog.showModal();
  $("#paste-text").focus();
}

function addFromDialog() {
  if (addPasted(pasteKind, $("#paste-text").value)) pasteDialog.close();
  else $("#paste-error").textContent = PASTE_KINDS[pasteKind].error;
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
  const paste = event.target.closest("[data-paste]");
  if (paste) openPasteDialog(paste.dataset.paste || "bib");
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
  const kinds = pastedKinds(text);
  const kind = ["bib", "abbr", "bbl"].find((k) => kinds[k]);
  if (kind) addPasted(kind, text);
  else toast("The pasted text is not BibTeX, abbreviations (@string), or a .bbl file");
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

function keyChips(list, keys) {
  list.replaceChildren(...keys.map((key) => {
    const chip = document.createElement("code");
    chip.textContent = key;
    chip.title = key;
    return chip;
  }));
  list.hidden = !keys.length;
}

function renderFilesInfo() {
  for (const kind of ["bbl", "abbr"]) {
    const file = state[kind];
    $(`#${kind}-actions`).hidden = Boolean(file);
    $(`#${kind}-field`).hidden = !file;
    $(`#${kind}-name`).textContent = file ? file.name : "";
  }
  const r = state.response;

  // The .bbl file: how many entries are cited, and which are not found
  const info = $("#bbl-info");
  const cited = r && r.cited;
  let missing = [];
  info.classList.remove("warn");
  info.title = "";
  if (!state.bbl) {
    info.textContent = "";
  } else if (!state.settings.cited.enabled) {
    info.textContent = "Turned off: all entries are kept.";
  } else if (!state.sources.length) {
    info.textContent = "Open your bib files to keep their cited entries.";
  } else if (cited) {
    missing = cited.missing;
    info.innerHTML = `<strong>${cited.count}</strong> cited · <strong>${cited.kept}</strong> ${cited.kept === 1 ? "entry" : "entries"} kept` +
      (missing.length ? ` · <strong>${missing.length}</strong> not in your files:` : "");
    info.title = `Read from a ${cited.backend} .bbl file`;
    info.classList.toggle("warn", missing.length > 0);
  } else {
    info.textContent = "Reading…";
  }
  info.hidden = !info.textContent;
  keyChips($("#bbl-missing"), missing);

  // Abbreviations (@string) that are used in the bib files but not defined,
  // which are kept as text
  const abbrInfo = $("#abbr-info");
  const undefinedNames = (r && r.undefined_strings) || [];
  const expanding = state.settings.strings.enabled && state.abbr;
  abbrInfo.classList.toggle("warn", Boolean(expanding && undefinedNames.length));
  if (undefinedNames.length) {
    abbrInfo.innerHTML = expanding
      ? `<strong>${undefinedNames.length}</strong> not defined in ${escapeHtml(state.abbr.name)}, kept as text:`
      : `<strong>${undefinedNames.length}</strong> in your files, kept as text${state.abbr ? "" : " until you add their definitions"}:`;
  } else {
    abbrInfo.textContent = state.abbr && !state.settings.strings.enabled ? "Turned off." : "";
  }
  abbrInfo.hidden = !abbrInfo.textContent;
  keyChips($("#abbr-undefined"), undefinedNames);
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

// `badges` are shown at the end of the line, or on a row below it when they
// do not fit next to the text, so that the key is not broken
function lineHtml(number, text, cls = "", badges = "") {
  if (badges) cls = cls ? `${cls} has-badges` : "has-badges";
  return `<div class="l${cls ? " " + cls : ""}"><span class="n">${number}</span>` +
    `<span class="t">${escapeHtml(text) || " "}</span>` +
    (badges ? `<span class="badges">${badges}</span>` : "") + "</div>";
}

const FILE_ICON = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></svg>`;

// The name of a file above its entries, which stays at the top of the pane
// while its entries are shown
function sourceHead(name, attrs = "") {
  return `<div class="l sep src-head"${attrs}><span class="n"></span>` +
    `<span class="t">${FILE_ICON}<span class="src-name">${escapeHtml(name)}</span></span></div>`;
}

function badge(kind, text, attrs = "") {
  return `<span class="badge ${kind}"${attrs}>${escapeHtml(text)}</span>`;
}

function renderOriginal(outByOrigin, unresolved) {
  const r = state.response;
  const parts = [];
  panes.original.folds = [];
  state.sources.forEach((source, sourceIdx) => {
    const lines = splitLines(source.text);
    const combined = state.sources.length > 1;
    if (combined) {
      parts.push(`<section class="src">`,
        sourceHead(source.name, ` title="Go to the start of ${escapeHtml(source.name)}"`));
    }
    // The folds end with the file
    const folder = makeFolder(parts, panes.original.folds);
    const entries = r ? r.sources[sourceIdx].entries : [];
    let next = 0;
    for (const entry of entries) {
      const [first, last] = entry.lines;
      if (first < next) continue;
      for (let i = next; i < first; i++) folder.line(lineHtml(i + 1, lines[i]));
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
        if (out && out.aliases.length) label += badge("chg", `also cited as ${out.aliases.join(", ")}`);
      }
      const lineCls = new Array(last - first + 1).fill("");
      if (out) {
        for (const [field, [a, b]] of Object.entries(entry.fields)) {
          const kind = out.removed.includes(field) ? "rm" : out.changed.includes(field) ? "chg" : "";
          for (let i = a; kind && i <= b; i++) lineCls[i - first] = kind;
        }
        if (out.id_changed || out.type_changed) lineCls[0] = "chg";
      }
      if (entry.origin === state.selected) cls += " selected";
      const html = [`<div class="${cls}" data-origin="${entry.origin || ""}">`];
      for (let i = first; i <= last; i++) {
        html.push(lineHtml(i + 1, lines[i] ?? "", lineCls[i - first], i === first ? label : ""));
      }
      html.push("</div>");
      folder.entry(html.join(""), out && !removed && isFolded(out, unresolved) ? entry.origin : null);
      next = last + 1;
    }
    for (let i = next; i < lines.length; i++) folder.line(lineHtml(i + 1, lines[i]));
    folder.close();
    if (combined) parts.push("</section>");
  });
  panes.original.content.innerHTML = parts.join("");
}

// The entries of the output in the order of the files, like in the original,
// or sorted by ID, like the output
function previewEntries(r) {
  if (state.settings.sortPreview) return r.entries;
  const rank = new Map();
  for (const source of r.sources) {
    for (const entry of source.entries) if (entry.origin) rank.set(entry.origin, rank.size);
  }
  return [...r.entries].sort((a, b) => rank.get(a.origin) - rank.get(b.origin));
}

function renderPreview(unresolved) {
  const r = state.response;
  if (!r) {
    panes.preview.content.innerHTML = "";
    return;
  }
  const parts = [];
  panes.preview.folds = [];
  const folder = makeFolder(parts, panes.preview.folds);
  let line = 1;
  previewEntries(r).forEach((out, idx) => {
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
    if (out.id_changed) label += badge("chg", `was ${out.original_id}`);
    if (out.aliases.length) label += badge("chg", `also cited as ${out.aliases.join(", ")}`);
    if (out.id_changed || out.type_changed) lineCls[0] = "chg";
    if (out.origin === state.selected) cls += " selected";
    const html = [`<div class="${cls}" data-origin="${out.origin}">`];
    lines.forEach((text, i) => html.push(lineHtml(line + i, text, lineCls[i], i === 0 ? label : "")));
    html.push("</div>");
    folder.entry(html.join(""), isFolded(out, unresolved) ? out.origin : null);
    if (idx < r.entries.length - 1) folder.line(lineHtml(line + lines.length, ""));
    line += lines.length + 1;
  });
  folder.close();
  if (!r.entries.length) {
    parts.push(`<div class="l"><span class="n"></span><span class="t muted">No entries left with these settings.</span></div>`);
  }
  panes.preview.content.innerHTML = parts.join("");
}

// The entries of a pane, and the shown ones: while searching, only the
// entries that match, and otherwise the entries that are not folded
function indexPane(pane) {
  pane.all = $$(".entry", pane.el).filter((el) => el.dataset.origin);
  pane.allByOrigin = new Map(pane.all.map((el) => [el.dataset.origin, el]));
  pane.entries = pane.all.filter(search.filter ? (el) => search.filter.has(el.dataset.origin)
    : (el) => !el.parentElement.classList.contains("folded"));
  pane.byOrigin = new Map(pane.entries.map((el) => [el.dataset.origin, el]));
  pane.link = null;
}

function render() {
  const r = state.response;
  const anchor = captureAnchor(panes[state.lastPane]);
  const outByOrigin = new Map(r ? r.entries.map((out) => [out.origin, out]) : []);
  const unresolved = new Set(r ? r.unresolved_pairs.flat() : []);
  renderOriginal(outByOrigin, unresolved);
  renderPreview(unresolved);
  search.words = null;
  search.marked = [];
  indexPane(panes.original);
  indexPane(panes.preview);
  // While searching, only the entries that match are shown
  if (search.tokens.length) runSearch({ keep: true });
  else renderSearch();
  // The new content can change the scroll positions, which are not the user's
  for (const pane of Object.values(panes)) handled(pane);
  restoreAnchor(panes[state.lastPane], anchor);
  if (state.linkScroll) align(panes[state.lastPane], panes[other(state.lastPane)]);

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
  const changed = r.entries.filter(isChanged).length;
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

// The pairs of duplicates to decide: pairs whose other entry was already
// removed no longer matter, and are not counted
function reviewProgress() {
  const r = state.response;
  if (!r || state.settings.duplicates.mode !== "choose" || !r.duplicate_pairs?.length) return null;
  const decided = r.decided_pairs.length;
  const total = decided + r.unresolved_pairs.length;
  return { decided, total, left: total - decided };
}

function renderReview() {
  const button = $("#review");
  const progress = reviewProgress();
  const sum = $("#dup-sum");
  const badge = $("#rail-badge");
  button.hidden = !progress;
  badge.hidden = !progress || !progress.left;
  sum.textContent = !progress ? "" : progress.left ? `${plural(progress.left, "pair")} left` : "all decided";
  if (!progress) return;
  const { decided, total, left } = progress;
  const done = left === 0;
  button.classList.toggle("done", done);
  button.classList.toggle("todo", decided === 0);
  $("#review-label").textContent = done ? "All pairs decided" : "Review duplicates";
  $("#review-count").textContent = `${decided} of ${total}`;
  $("#review-fill").style.width = `${total ? (100 * decided) / total : 100}%`;
  button.setAttribute("aria-label", `Review duplicates: ${decided} of ${plural(total, "pair")} decided`);
  badge.textContent = String(left);
  badge.title = `${plural(left, "pair")} of duplicates left to review`;
}

/* Folding */

// Runs of unchanged entries are folded in both panes, so that you see what
// changed. Each pane folds the runs in its own order. The folded entries are
// still there, hidden, so that the search finds them.

const UNFOLD_ICON = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 22v-6"/><path d="M12 8V2"/><path d="M4 12H2"/><path d="M10 12H8"/><path d="M16 12h-2"/><path d="M22 12h-2"/><path d="m15 19-3 3-3-3"/><path d="m15 5-3-3-3 3"/></svg>`;

// Whether an entry of the output differs from its original in what the panes
// highlight: its key, its type, or its fields. A new format, e.g., another
// order of the fields, does not count.
function isChanged(out) {
  return Boolean(out.id_changed || out.type_changed || out.aliases.length ||
    out.added.length || out.changed.length || out.removed.length);
}

// Possible duplicates are never folded, since you have to choose one of them
function isFolded(out, unresolved) {
  return state.fold && !isChanged(out) && !unresolved.has(out.origin) && !state.unfolded.has(out.origin);
}

// Adds the entries and the lines between them to the HTML of a pane, with a
// fold in place of each run of folded entries, followed by the hidden run.
// The lines between two folded entries are folded with them.
function makeFolder(parts, folds) {
  let run = null;   // {html, origins} of the run of folded entries
  let after = [];   // the lines after the run, until the next entry
  const close = () => {
    if (run) {
      const text = plural(run.origins.length, "unchanged entry", "unchanged entries");
      parts.push(`<div class="l fold" role="button" tabindex="0" data-fold="${folds.length}" title="Show the ${text}">` +
        `<span class="n">${UNFOLD_ICON}</span><span class="t">${text}</span></div>`,
        `<div class="folded">${run.html.join("")}</div>`);
      folds.push(run.origins);
      run = null;
    }
    parts.push(after.join(""));
    after = [];
  };
  return {
    line: (html) => (run ? after : parts).push(html),
    // `origin` is the origin of a folded entry, or null for a shown entry
    entry(html, origin) {
      if (!origin) {
        close();
        parts.push(html);
        return;
      }
      run = run || { html: [], origins: [] };
      run.html.push(...after, html);
      run.origins.push(origin);
      after = [];
    },
    close,
  };
}

// Show the entries of a fold in both panes, until folding is switched on again
function unfold(name, idx) {
  for (const origin of panes[name].folds[idx] || []) state.unfolded.add(origin);
  state.lastPane = name;
  render();
}

function renderFold() {
  const button = $("#fold");
  button.setAttribute("aria-pressed", String(state.fold));
  button.title = state.fold
    ? "Unchanged entries are folded. Click to show all entries."
    : "Fold the unchanged entries, to see only what changed.";
}

// Folding again folds the entries that you unfolded too
$("#fold").addEventListener("click", () => {
  state.fold = !state.fold;
  saveJson(FOLD_KEY, state.fold);
  state.unfolded.clear();
  renderFold();
  render();
});
renderFold();

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
  // A folded entry is in the place of its fold
  const group = el || search.filter ? null : pane.allByOrigin.get(anchor.origin)?.parentElement;
  if (group?.classList.contains("folded")) setScroll(pane, group.previousElementSibling.offsetTop);
  else setScroll(pane, el ? el.offsetTop + anchor.offset : anchor.offset);
}

/* Positions without the blank space above the content ("view") */

const contentTop = (pane, el) => el.offsetTop - pane.top;
const contentEnd = (pane) => pane.el.scrollHeight - pane.top - pane.bottom;
const view = (pane) => pane.el.scrollTop - pane.top;
const maxView = (pane) => Math.max(0, contentEnd(pane) - pane.el.clientHeight);
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

// Scroll a pane from the code. Its scroll event is recognized by the position,
// however late the browser sends it, so that it is not taken for the user's.
function setScroll(pane, top) {
  if (Math.abs(pane.el.scrollTop - top) >= 1) pane.el.scrollTop = top;
  handled(pane);
}

// The current position of a pane needs no scrolling of the other pane, e.g.,
// because the panes were just aligned
function handled(pane) {
  pane.expected = pane.el.scrollTop;
  pane.last = view(pane);
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

/* Linked scrolling */

// Map from the content of a pane to the content of the other pane, as points
// with straight lines between them. The middle of each entry is mapped to the
// middle of its counterpart, which spreads the space of removed entries over
// the entries around them, so that the other pane moves without leaps. If the
// counterparts are in another order, e.g., sorted, the entries are mapped
// exactly, and the map jumps in the middle of the space between them.
function linkMap(from, to) {
  if (from.link) return from.link;
  const order = new Map();
  for (const el of to.entries) {
    if (from.byOrigin.has(el.dataset.origin)) order.set(el.dataset.origin, order.size);
  }
  const points = [[0, 0]];
  let last = { idx: -1, end: [0, 0] };
  const add = (idx, top, targetTop, height, targetHeight) => {
    if (idx !== last.idx + 1) {
      const middle = (last.end[0] + top) / 2;
      points.push(last.end, [middle, last.end[1]], [middle, targetTop], [top, targetTop]);
    }
    points.push([top + height / 2, targetTop + targetHeight / 2]);
    last = { idx, end: [top + height, targetTop + targetHeight] };
  };
  for (const el of from.entries) {
    const target = to.byOrigin.get(el.dataset.origin);
    if (!target) continue;
    add(order.get(el.dataset.origin), contentTop(from, el), contentTop(to, target),
        el.offsetHeight, target.offsetHeight);
  }
  // The ends of both panes
  add(order.size, contentEnd(from), contentEnd(to), 0, 0);
  from.link = points;
  return points;
}

function mapLink(points, position) {
  if (position <= points[0][0]) return points[0][1];
  // The last point at or before the position
  let lo = 0;
  let hi = points.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (points[mid][0] <= position) lo = mid;
    else hi = mid - 1;
  }
  const [x, y] = points[lo];
  const next = points[lo + 1];
  return next ? y + (position - x) / (next[0] - x) * (next[1] - y) : y;
}

// The line at which the panes are linked, as a fraction of the height of a
// pane: the top at its start, the middle, and the bottom at its end, so that
// both panes start and end together
function linkLine(pane, position) {
  const max = maxView(pane);
  if (max <= 0) return 0;
  const zone = Math.min(pane.el.clientHeight, max) / 2;
  const clamped = Math.min(Math.max(position, 0), max);
  return (Math.min(clamped, zone) + zone - Math.min(max - clamped, zone)) / (2 * zone);
}

// The view of the other pane that shows the content of the line of a pane
function linkedView(from, to, position) {
  const line = linkLine(from, position);
  const at = mapLink(linkMap(from, to), position + line * from.el.clientHeight);
  return Math.min(Math.max(0, at - line * to.el.clientHeight), maxView(to));
}

// The selected entry and its counterpart, while the entry is visible in a pane
function selectedPair(from, to) {
  const el = state.selected && from.byOrigin.get(state.selected);
  const target = state.selected && to.byOrigin.get(state.selected);
  return el && target && isVisible(from, el) ? [el, target] : null;
}

// The view of the other pane that shows the counterpart at the same height
const alignedView = (from, to, [el, target], position) =>
  contentTop(to, target) - (contentTop(from, el) - position);

// Scroll the other pane to what a pane shows, e.g., after the panes changed
function align(from, to) {
  if (!from.entries.length || !to.entries.length) return;
  const pair = selectedPair(from, to);
  const position = view(from);
  setView(to, pair ? alignedView(from, to, pair, position) : linkedView(from, to, position));
  handled(from);
}

// Move the other pane with a pane that the user scrolls: as much as the view
// it should show moves, so that it never jumps, e.g., when the user switches
// panes or the selected entry leaves the view. If it does not show that view,
// e.g., after its end was reached, it catches up while the user scrolls.
function follow(from, to, previous) {
  const position = view(from);
  const delta = position - previous;
  if (!delta || !from.entries.length || !to.entries.length) return;
  const pair = selectedPair(from, to);
  const current = view(to);
  let move = delta;
  let goal;
  if (pair) {
    goal = alignedView(from, to, pair, position);
  } else {
    // As much as the content at the line moves. The line itself moves near the
    // ends, which is caught up with below, so that it cannot reverse the move.
    const line = linkLine(from, position) * from.el.clientHeight;
    const map = linkMap(from, to);
    move = mapLink(map, position + line) - mapLink(map, previous + line);
    goal = linkedView(from, to, position);
  }
  const offset = goal - (current + move);
  // Catch up at least half as fast as the user scrolls, and fully at the end of
  // the pane, by moving further or less far, but never backwards
  const remaining = Math.max(0, delta > 0 ? maxView(from) - position : position);
  const size = Math.abs(delta);
  const catchUp = Math.min(Math.abs(offset),
    Math.max(size / 2, Math.abs(offset) * size / (remaining + size)));
  const direction = Math.sign(move) || Math.sign(delta);
  let next = current + move;
  if (Math.sign(offset) === direction) next += direction * catchUp;
  else next -= direction * Math.min(catchUp, Math.abs(move));
  // Only the selected entry is aligned with blank space
  if (!pair) next = Math.min(Math.max(next, Math.min(0, current)), Math.max(maxView(to), current));
  setView(to, next);
}

for (const name of ["original", "preview"]) {
  const pane = panes[name];
  pane.el.addEventListener("scroll", () => {
    clearTimeout(pane.trimTimer);
    pane.trimTimer = setTimeout(() => trimPads(pane), 250);
    if (pane.expected !== null && Math.abs(pane.el.scrollTop - pane.expected) < 1) return;
    pane.expected = null;
    const previous = pane.last;
    pane.last = view(pane);
    state.lastPane = name;
    if (state.linkScroll) follow(pane, panes[other(name)], previous);
  }, { passive: true });
  pane.el.addEventListener("click", (event) => {
    const fold = event.target.closest(".fold");
    if (fold) {
      unfold(name, Number(fold.dataset.fold));
      return;
    }
    const head = event.target.closest(".src > .src-head");
    if (head) {
      pane.el.scrollTop = head.parentElement.offsetTop;
      return;
    }
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

// A fold is unfolded with Enter or Space too
for (const name of ["original", "preview"]) {
  panes[name].el.addEventListener("keydown", (event) => {
    const fold = event.target.closest(".fold");
    if (!fold || (event.key !== "Enter" && event.key !== " ")) return;
    event.preventDefault();
    unfold(name, Number(fold.dataset.fold));
    panes[name].el.focus({ preventScroll: true });
  });
}

// Lines wrap, so the positions of the entries change with the width
const resizeObserver = new ResizeObserver(() => {
  for (const pane of Object.values(panes)) pane.link = null;
});
for (const pane of Object.values(panes)) resizeObserver.observe(pane.content);

// Select an entry on one side and show it at the same height on the other
function select(origin, fromName) {
  state.selected = state.selected === origin ? null : origin;
  state.lastPane = fromName;
  for (const pane of Object.values(panes)) {
    pane.all.forEach((el) => el.classList.toggle("selected", el.dataset.origin === state.selected));
  }
  if (!state.selected) return;
  const from = panes[fromName];
  const to = panes[other(fromName)];
  const el = from.byOrigin.get(origin);
  const target = to.byOrigin.get(origin);
  if (el && target) setView(to, alignedView(from, to, [el, target], view(from)));
  handled(from);
}

/* Search */

// Fuzzy search in both panes: an entry matches if each word of the query is
// in it, as a part of a word or with a typo, in any order. Accents, case, and
// LaTeX, e.g., Erd{\H o}s, are ignored. Only the entries that match are
// shown.
const search = {
  query: "",      // the query of the matches
  tokens: [],     // its words
  matches: [],    // origins of the matching entries, in the order of the files
  current: -1,    // index of the shown match
  words: null,    // origin -> words of the entry in both panes
  marked: [],     // lines with marked words
  filter: null,   // origins of the shown entries while searching
  // Show only the entries that match, or all entries with the matches marked
  onlyMatches: loadJson(SEARCH_FILTER_KEY, true) !== false,
};

function normalizeText(text) {
  return text.replace(/\\[a-zA-Z]+\s*|\\./g, "").replace(/[{}]/g, "")
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

const searchWords = (text) => normalizeText(text).match(/[\p{L}\p{N}]+/gu) || [];

// The edit distance of two words, with swapped letters as one edit, or more
// than `max` if it is larger
function editDistance(a, b, max) {
  if (Math.abs(a.length - b.length) > max) return max + 1;
  let prev2 = null;
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const row = [i];
    let best = i;
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      let d = Math.min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + cost);
      if (prev2 && i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d = Math.min(d, prev2[j - 2] + 1);
      row.push(d);
      best = Math.min(best, d);
    }
    if (best > max) return max + 1;
    prev2 = prev;
    prev = row;
  }
  return prev[b.length];
}

// Whether a word of the query matches a word of an entry: as a part of it,
// or with a typo in the word or its start, e.g., "comunication"
function wordMatches(token, word) {
  if (word.includes(token)) return true;
  if (token.length < 4) return false;
  const max = token.length >= 8 ? 2 : 1;
  for (let len = token.length - max; len <= Math.min(word.length, token.length + max); len++) {
    if (editDistance(token, word.slice(0, len), max) <= max) return true;
  }
  return false;
}

// The words of each entry in both panes, by its origin
function searchIndex() {
  if (search.words) return search.words;
  const words = new Map();
  for (const pane of [panes.original, panes.preview]) {
    for (const el of pane.all) {
      const text = $$(".t", el).map((t) => t.textContent).join(" ");
      const set = words.get(el.dataset.origin) || new Set();
      for (const word of searchWords(text)) set.add(word);
      words.set(el.dataset.origin, set);
    }
  }
  search.words = words;
  return words;
}

// Mark the words that match in the entries that match
function markMatches() {
  for (const el of search.marked) el.textContent = el.dataset.text;
  search.marked = [];
  for (const origin of search.matches) {
    for (const pane of [panes.original, panes.preview]) {
      const entry = pane.allByOrigin.get(origin);
      for (const t of entry ? $$(".t", entry) : []) {
        const text = t.textContent;
        let html = "";
        let last = 0;
        for (const m of text.matchAll(/[\p{L}\p{N}]+/gu)) {
          const word = normalizeText(m[0]);
          if (!search.tokens.some((token) => wordMatches(token, word))) continue;
          html += escapeHtml(text.slice(last, m.index)) + `<mark>${escapeHtml(m[0])}</mark>`;
          last = m.index + m[0].length;
        }
        if (!html) continue;
        t.dataset.text = text;
        t.innerHTML = html + escapeHtml(text.slice(last));
        search.marked.push(t);
      }
    }
  }
}

function renderSearch() {
  const count = $("#search-count");
  const n = search.matches.length;
  count.textContent = !search.tokens.length ? "" : n ? `${search.current + 1} of ${n}` : "No match";
  count.classList.toggle("none", Boolean(search.tokens.length) && !n);
  $("#search-prev").disabled = $("#search-next").disabled = n === 0;
}

// Find the matches of the query. With `keep`, e.g., after the panes changed,
// the current match stays without scrolling, if it still matches.
function runSearch({ keep = false } = {}) {
  const current = search.matches[search.current];
  search.query = $("#search-input").value;
  search.tokens = searchWords(search.query);
  const words = searchIndex();
  search.matches = !search.tokens.length ? [] : panes.original.all.map((el) => el.dataset.origin)
    .filter((origin) => {
      const entryWords = [...words.get(origin)];
      return search.tokens.every((token) => entryWords.some((word) => wordMatches(token, word)));
    });
  markMatches();
  filterEntries();
  const kept = keep ? search.matches.indexOf(current) : -1;
  search.current = kept >= 0 ? kept : search.matches.length ? 0 : -1;
  renderSearch();
  if (keep) return;
  if (search.current >= 0) showMatch();
  else if (!search.tokens.length && state.selected) revealEntry(state.selected);
}

// Show only the entries that match, and the files with them, while searching
function filterEntries() {
  search.filter = search.tokens.length && search.onlyMatches ? new Set(search.matches) : null;
  for (const pane of [panes.original, panes.preview]) {
    pane.content.classList.toggle("filtering", Boolean(search.filter));
    for (const el of pane.all) el.classList.toggle("match", Boolean(search.filter?.has(el.dataset.origin)));
    for (const section of $$(".src", pane.content)) {
      section.classList.toggle("has-match", Boolean($(".entry.match", section)));
    }
    pane.empty.hidden = !search.filter || search.filter.size > 0;
    indexPane(pane);
  }
}

// Show the current match in both panes, at the same height, like a click on it
function showMatch() {
  revealEntry(search.matches[search.current]);
  renderSearch();
}

// Select an entry and show it in both panes at the same height. It is shown
// in the original, which has all entries, and the preview follows.
function revealEntry(origin) {
  const from = panes.original;
  const to = panes.preview;
  // A folded entry is unfolded, e.g., a match while all entries are shown
  if (!search.filter && !from.byOrigin.has(origin) && from.allByOrigin.has(origin)) {
    state.unfolded.add(origin);
    render();
  }
  const el = from.byOrigin.get(origin);
  if (!el) return;
  state.selected = origin;
  state.lastPane = "original";
  for (const pane of Object.values(panes)) {
    pane.all.forEach((entry) => entry.classList.toggle("selected", entry.dataset.origin === origin));
  }
  setView(from, Math.min(Math.max(0, contentTop(from, el) - from.el.clientHeight * 0.2), maxView(from)));
  const target = to.byOrigin.get(origin);
  if (target) setView(to, alignedView(from, to, [el, target], view(from)));
  else if (state.linkScroll) align(from, to);
  handled(from);
  handled(to);
}

function stepSearch(step) {
  const n = search.matches.length;
  if (!n) return;
  search.current = (search.current + step + n) % n;
  showMatch();
}

let searchTimer;
$("#search-input").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => runSearch(), 120);
});
$("#search-input").addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    clearTimeout(searchTimer);
    // A query that was typed but not searched yet is searched first
    if (event.target.value !== search.query) runSearch();
    else stepSearch(event.key === "ArrowUp" || (event.key === "Enter" && event.shiftKey) ? -1 : 1);
  } else if (event.key === "Escape") {
    if (event.target.value) {
      event.target.value = "";
      runSearch();
    } else {
      event.target.blur();
    }
  }
});
$("#search-prev").addEventListener("click", () => stepSearch(-1));
$("#search-next").addEventListener("click", () => stepSearch(1));

function renderSearchFilter() {
  const button = $("#search-filter");
  button.setAttribute("aria-pressed", String(search.onlyMatches));
  button.title = search.onlyMatches
    ? "Showing only the entries that match. Click to show all entries."
    : "Showing all entries, with the matches marked. Click to show only the entries that match.";
}

$("#search-filter").addEventListener("click", () => {
  search.onlyMatches = !search.onlyMatches;
  saveJson(SEARCH_FILTER_KEY, search.onlyMatches);
  renderSearchFilter();
  filterEntries();
  if (search.current >= 0) showMatch();
  else if (state.selected) revealEntry(state.selected);
});
renderSearchFilter();
// Ctrl+F searches the entries; pressed again in the search box, it opens the
// search of the browser
document.addEventListener("keydown", (event) => {
  if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "f") return;
  if (!state.sources.length || document.activeElement === $("#search-input") || document.querySelector("dialog[open]")) return;
  event.preventDefault();
  $("#search-input").focus();
  $("#search-input").select();
});

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
  const undecided = r.unresolved_pairs.length;
  $("#dup-counter").textContent = `Pair ${dupIndex + 1} of ${pairs.length}` +
    (undecided ? ` · ${undecided} not decided` : " · all decided");
  // With a .bbl file, the kept entry takes over the cited key of the other
  const cited = new Set(r.cited ? r.cited.origins : []);
  const bothKept = Boolean(r.cited) && r.cited.both_cited.some(([a, b]) => `${a}|${b}` === key);
  const ids = texts.map((lines, i) => (lines[0].match(/\{(.*),$/) || [, pair[i]])[1]);
  $$(".dup-side", dialog).forEach((side, i) => {
    const origin = pair[i];
    const lines = texts[i];
    const otherLines = lineSets[1 - i];
    $(".dup-id", side).textContent = ids[i];
    $(".badge.cited", side).hidden = !cited.has(origin);
    $(".code", side).innerHTML = lines.map((text, n) =>
      lineHtml(n + 1, text, n > 0 && !otherLines.has(text) ? "only" : "")).join("");
    const reason = bothKept ? null : r.removed[origin];
    const out = r.entries.find((e) => e.origin === origin);
    let text = decision === origin && !bothKept ? "will be removed"
      : reason === "not cited" ? "not cited — removed by the filter"
      : reason && reason.startsWith("duplicate of") ? "removed with another pair"
      : reason ? reason
      : !decided ? "not decided — kept for now" : "kept";
    if (out && !reason && out.id !== out.original_id) text += ` as ${out.id}`;
    if (out && !reason && out.aliases.length) text += `, also as ${out.aliases.join(", ")}`;
    side.classList.toggle("removed", Boolean(reason) || (decision === origin && !bothKept));
    side.classList.toggle("kept", !reason && decided && (decision !== origin || bothKept));
    $(".dup-state", side).textContent = text;
    $("[data-remove]", side).disabled = decision === origin;
  });
  const note = $("#dup-note");
  const citedIds = ids.filter((id, i) => cited.has(pair[i]));
  note.textContent = !r.cited || !citedIds.length ? ""
    : bothKept || (citedIds.length === 2 && outputFormat() !== "biblatex")
      ? "Both keys are cited, and BibTeX has no aliases for keys, so both entries are kept. Cite one of the keys in your .tex file to remove the duplicate."
    : citedIds.length === 2
      ? "Both keys are cited. The kept entry gets the other key in its ids field, which biblatex resolves."
    : `Your .bbl file cites ${citedIds[0]}. If you remove it, the other entry takes over this key.`;
  note.hidden = !note.textContent;
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
  if (!r || !effectiveSettings().arxiv.lookup) return [];
  return r.eprints.filter((e) => !(e in state.arxiv) && !state.arxivTried.has(e));
}

// Ask before the first request to arXiv, which sends the eprint IDs. The
// answer is remembered, so that the lookup can start by itself later, e.g.,
// after a reload. Turning the setting on always asks.
const arxivDialog = $("#arxiv-dialog");
$("#arxiv-allow").addEventListener("click", () => arxivDialog.close("allow"));
arxivDialog.addEventListener("click", (event) => {
  if (event.target === arxivDialog || event.target.closest("[data-dialog-close]")) arxivDialog.close();
});

function askArxiv() {
  return new Promise((resolve) => {
    arxivDialog.returnValue = "";
    arxivDialog.addEventListener("close", () => {
      const allowed = arxivDialog.returnValue === "allow";
      if (allowed) {
        state.arxivAllowed = true;
        saveJson(ARXIV_CONSENT_KEY, true);
      }
      resolve(allowed);
    }, { once: true });
    arxivDialog.showModal();
  });
}

async function maybeFetchArxiv() {
  const eprints = missingEprints();
  if (!eprints.length || state.arxivBusy || arxivDialog.open) return;
  if (!state.arxivAllowed) {
    // The setting came from a shared link or from before this question
    if (!(await askArxiv())) {
      state.settings.arxiv.lookup = false;
      settingChanged();
      return;
    }
    if (state.arxivBusy) return;
  }
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
  else if (r && effectiveSettings().arxiv.lookup && r.eprints.length) {
    const known = r.eprints.filter((e) => e in state.arxiv).length;
    label.textContent = `(${known}/${r.eprints.length})`;
  } else label.textContent = "";
}

/* About */

const aboutDialog = $("#about-dialog");
$("#about-open").addEventListener("click", () => aboutDialog.showModal());
aboutDialog.addEventListener("click", (event) => {
  if (event.target === aboutDialog || event.target.closest("[data-dialog-close]")) aboutDialog.close();
});

/* Actions */

function downloadName() {
  if (state.sources.length === 1) return `clean-${state.sources[0].name.replace(/\.bib$/i, "")}.bib`;
  return "combined.bib";
}

// A comment at the top of copied and downloaded files, which BibTeX and
// biber ignore. The preview leaves it out, so its lines match the entries.
const CREDIT = "% Made with the web version of bibtex-tools\n\n";

function outputText() {
  return CREDIT + state.response.text;
}

function download() {
  if (!state.response) return;
  const blob = new Blob([outputText()], { type: "text/x-bibtex;charset=utf-8" });
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
    await navigator.clipboard.writeText(outputText());
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

// Settings in shared links, e.g., #latex=on&duplicates=keep, by their name
// in the link. Only settings that differ from the defaults are listed.
const LINK_SETTINGS = {
  format: "format",
  convert: "fields.convert",
  cited: "cited.enabled",
  strings: "strings.enabled",
  duplicates: "duplicates.mode",
  cleanup: "fields.clean",
  titles: "fields.titles",
  iso4: "fields.iso4",
  latex: "fields.unicode",
  preprints: "arxiv.style",
  arxiv: "arxiv.lookup",
  rename: "keys.rename",
  ids: "keys.generate",
  fields: "remove.fields",
  sort: "sortPreview",
};

// Links of version 2, which are converted with `fromV2`. They are told apart
// by the names that only they have, e.g., modernize.
const LINK_SETTINGS_V2 = {
  filter: "filter.enabled",
  clean: "clean.enabled",
  unicode: "clean.unicode",
  modernize: "modernize.enabled",
  fix: "modernize.fields",
  shield: "modernize.shield",
  iso4: "modernize.iso4",
  ids: "modernize.ids",
  arxiv: "modernize.arxiv",
  preprints: "modernize.arxivStyle",
  remove: "remove.enabled",
  fields: "remove.fields",
  duplicates: "duplicates.mode",
  rename: "duplicates.rename",
  sort: "sortPreview",
};
const isV2Link = (params) => Object.keys(LINK_SETTINGS_V2).some((name) => !(name in LINK_SETTINGS) && params.has(name));

// The lists of fields that a setting can have, or null for any field
const LINK_LISTS = {
  "fields.clean": () => defaults.clean_fields,
  "remove.fields": () => null,
  "modernize.fields": () => V2_CLEAN_FIELDS,
};

// The value of a setting, with the default lists of fields filled in
function effectiveSetting(settings, path) {
  const value = getPath(settings, path);
  if (path === "fields.clean") return value ?? defaults.clean_fields;
  if (path === "remove.fields") return value ?? defaults.remove_fields;
  return value;
}

function settingsToLink(settings) {
  const parts = [];
  for (const [name, path] of Object.entries(LINK_SETTINGS)) {
    const value = effectiveSetting(settings, path);
    if (JSON.stringify(value) === JSON.stringify(effectiveSetting(DEFAULT_SETTINGS, path))) continue;
    const text = typeof value === "boolean" ? (value ? "on" : "off")
      : Array.isArray(value) ? value.map(encodeURIComponent).join(",")
      : encodeURIComponent(value);
    parts.push(`${name}=${text}`);
  }
  return parts.join("&");
}

function readLink(params, names, base) {
  const settings = structuredClone(base);
  for (const [name, path] of Object.entries(names)) {
    if (!params.has(name)) continue;
    const text = params.get(name).trim();
    const current = getPath(settings, path);
    if (typeof current === "boolean") {
      setPath(settings, path, ["on", "1", "true", "yes"].includes(text.toLowerCase()));
    } else if (path in LINK_LISTS) {
      const fields = text.split(",").map((f) => f.trim().toLowerCase()).filter(Boolean);
      const known = LINK_LISTS[path]();
      setPath(settings, path, known ? known.filter((f) => fields.includes(f)) : fields);
    } else {
      setPath(settings, path, text);
    }
  }
  return settings;
}

function settingsFromLink(params) {
  if (isV2Link(params)) return fromV2(readLink(params, LINK_SETTINGS_V2, V2_SETTINGS));
  return validSettings(readLink(params, LINK_SETTINGS, DEFAULT_SETTINGS));
}

// Links from before the plain format, with the settings of version 2 as
// base64 JSON
function decodeOldSettings(text) {
  const binary = atob(text.replace(/-/g, "+").replace(/_/g, "/"));
  const json = new TextDecoder().decode(Uint8Array.from(binary, (c) => c.charCodeAt(0)));
  return fromV2(JSON.parse(json));
}

$("#share").addEventListener("click", async () => {
  const url = new URL(location.href);
  url.hash = settingsToLink(state.settings);
  const href = url.hash ? url.href : url.href.replace(/#$/, "");
  const note = url.hash ? "It contains your settings, not your files."
    : "Your settings are the defaults, so it is the plain link.";
  try {
    await navigator.clipboard.writeText(href);
    toast(`Link copied. ${note}`);
  } catch {
    prompt(`Copy this link. ${note}`, href);
  }
});

function loadSharedSettings() {
  const params = new URLSearchParams(location.hash.slice(1));
  const old = params.get("settings");
  if (!old && ![...Object.keys(LINK_SETTINGS), ...Object.keys(LINK_SETTINGS_V2)].some((name) => params.has(name))) return;
  try {
    state.settings = old ? decodeOldSettings(old) : settingsFromLink(params);
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
