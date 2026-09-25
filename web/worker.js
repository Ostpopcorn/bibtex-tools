// Runs bibtextools with Pyodide, so that the page stays responsive while
// Python works. Only the latest request is processed.
import { loadPyodide } from "./pyodide/pyodide.mjs";

let bridge = null;
let latest = null;
let scheduled = false;

async function init() {
  postMessage({ type: "progress", text: "Starting Python…" });
  const pyodide = await loadPyodide({ indexURL: new URL("./pyodide/", import.meta.url).href });
  postMessage({ type: "progress", text: "Installing bibtextools…" });
  const manifest = await (await fetch(new URL("./wheels/manifest.json", import.meta.url))).json();
  const sitePackages = pyodide.runPython("import site; site.getsitepackages()[0]");
  await Promise.all(manifest.wheels.map(async (wheel) => {
    const response = await fetch(new URL("./wheels/" + wheel, import.meta.url));
    if (!response.ok) throw new Error(`Could not download ${wheel} (${response.status})`);
    pyodide.unpackArchive(await response.arrayBuffer(), "wheel", { extractDir: sitePackages });
  }));
  pyodide.runPython("import importlib; importlib.invalidate_caches()");
  bridge = pyodide.pyimport("bibtextools.web");
  postMessage({ type: "ready", defaults: JSON.parse(bridge.defaults()), version: manifest.version });
}

function process() {
  scheduled = false;
  if (!bridge || !latest) return;
  const { id, request } = latest;
  latest = null;
  try {
    const response = bridge.run(JSON.stringify(request));
    postMessage({ type: "result", id, response });
  } catch (err) {
    postMessage({ type: "error", id, message: pythonError(err) });
  }
}

function pythonError(err) {
  const text = String(err && err.message || err);
  // Show the last line of a Python traceback, e.g., "ValueError: ..."
  const lines = text.trim().split("\n");
  return lines[lines.length - 1];
}

self.onmessage = (event) => {
  if (event.data.type === "run") {
    latest = event.data;
    if (!scheduled) {
      scheduled = true;
      setTimeout(process, 0);
    }
  }
};

const ready = init().catch((err) => {
  postMessage({ type: "fatal", message: String(err && err.message || err) });
});
ready.then(() => { if (latest && !scheduled) { scheduled = true; setTimeout(process, 0); } });
