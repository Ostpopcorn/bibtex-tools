"""Build the web app into a folder that can be served as a static site, e.g.,
with GitHub Pages. The web app runs bibtextools in the browser with Pyodide,
which is downloaded from npm and served with the app.

    python web/build.py                 # build into web/dist
    python web/build.py --serve         # build and serve on http://localhost:8000
    python web/build.py --out _site     # build into another folder
    uv run web/build.py --serve         # the same with uv
"""
import argparse
import base64
import functools
import hashlib
import http.server
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

PYODIDE_VERSION = "314.0.7"
PYODIDE_FILES = ["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm",
                 "python_stdlib.zip", "pyodide-lock.json"]
STATIC_FILES = ["index.html", "style.css", "app.js", "worker.js", "favicon.svg"]
EXAMPLES = ["old.bib"]

WEB_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(WEB_DIR)
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "bibtextools-web")


def download_pyodide(version=PYODIDE_VERSION):
    """Return the npm package of Pyodide, which is cached."""
    path = os.path.join(CACHE_DIR, "pyodide-{}.tgz".format(version))
    if os.path.isfile(path):
        with open(path, "rb") as _file:
            return _file.read()
    url = "https://registry.npmjs.org/pyodide/{}".format(version)
    with urllib.request.urlopen(url) as response:
        dist = json.load(response)["dist"]
    print("Downloading", dist["tarball"])
    with urllib.request.urlopen(dist["tarball"]) as response:
        data = response.read()
    algorithm, digest = dist["integrity"].split("-", 1)
    if base64.b64encode(hashlib.new(algorithm, data).digest()).decode() != digest:
        raise RuntimeError("The download of Pyodide is corrupted")
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "wb") as _file:
        _file.write(data)
    return data


def copy_pyodide(out_dir):
    target = os.path.join(out_dir, "pyodide")
    os.makedirs(target)
    with tarfile.open(fileobj=io.BytesIO(download_pyodide())) as archive:
        for name in PYODIDE_FILES:
            member = archive.extractfile("package/" + name)
            with open(os.path.join(target, name), "wb") as _file:
                shutil.copyfileobj(member, _file)


def pip_command():
    """Return the command to run pip with. Virtual environments created by uv
    do not include pip, in which case uv runs pip."""
    if importlib.util.find_spec("pip") is not None:
        return [sys.executable, "-m", "pip"]
    uv = shutil.which("uv")
    if uv is not None:
        return [uv, "tool", "run", "pip"]
    sys.exit("Building the web app needs pip or uv. Install pip with "
             "'python -m ensurepip' or install uv.")


def get_version():
    with open(os.path.join(ROOT_DIR, "bibtextools", "__init__.py"),
              encoding="utf-8") as _file:
        return re.search(r'__version__ = "(.*?)"', _file.read()).group(1)


def build_wheels(out_dir):
    """Build the wheels of bibtextools and its dependencies, which are all
    pure Python, and list them in a manifest."""
    target = os.path.join(out_dir, "wheels")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(pip_command() + ["wheel", "--quiet", "--wheel-dir",
                                        tmp, ROOT_DIR], check=True)
        wheels = sorted(k for k in os.listdir(tmp) if k.endswith(".whl"))
        not_pure = [k for k in wheels if not k.endswith("-none-any.whl")]
        if not_pure:
            raise RuntimeError("Pyodide needs pure Python wheels: {}".format(
                ", ".join(not_pure)))
        os.makedirs(target)
        for wheel in wheels:
            shutil.copy(os.path.join(tmp, wheel), target)
    with open(os.path.join(target, "manifest.json"), "w") as _file:
        json.dump({"version": get_version(), "wheels": wheels}, _file, indent=2)
    return wheels


def _versioned(text, link, content):
    """Add a hash of the content to a link in the text, e.g., app.js?v=1a2b,
    so that browsers load the new file after an update instead of an old
    cached one, which may not fit the new index.html."""
    version = hashlib.sha256(content.encode("utf-8")).hexdigest()[:10]
    if text.count(link) != 1:
        raise RuntimeError("Expected {} once to add its version".format(link))
    # the link ends with a quote, e.g., src="app.js"
    return text.replace(link, "{}?v={}{}".format(link[:-1], version, link[-1]))

def copy_static(out_dir):
    files = {}
    for name in STATIC_FILES:
        with open(os.path.join(WEB_DIR, name), encoding="utf-8") as _file:
            files[name] = _file.read()
    files["app.js"] = _versioned(files["app.js"], '"./worker.js"',
                                 files["worker.js"])
    files["index.html"] = _versioned(files["index.html"], 'href="style.css"',
                                     files["style.css"])
    files["index.html"] = _versioned(files["index.html"], 'src="app.js"',
                                     files["app.js"])
    for name, content in files.items():
        with open(os.path.join(out_dir, name), "w", encoding="utf-8",
                  newline="\n") as _file:
            _file.write(content)


def build(out_dir):
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    copy_static(out_dir)
    os.makedirs(os.path.join(out_dir, "examples"))
    for name in EXAMPLES:
        shutil.copy(os.path.join(ROOT_DIR, "examples", name),
                    os.path.join(out_dir, "examples"))
    copy_pyodide(out_dir)
    wheels = build_wheels(out_dir)
    print("Built the web app in {} with {}".format(out_dir, ", ".join(wheels)))


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".mjs": "text/javascript", ".js": "text/javascript",
                      ".wasm": "application/wasm", ".bib": "text/plain"}


def serve(out_dir, port):
    handler = functools.partial(Handler, directory=out_dir)
    with http.server.ThreadingHTTPServer(("localhost", port), handler) as server:
        print("Serving the web app on http://localhost:{}".format(port))
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=os.path.join(WEB_DIR, "dist"),
                        help="Output folder (default: web/dist)")
    parser.add_argument("--serve", nargs="?", type=int, const=8000,
                        metavar="PORT", help="Serve the web app after building")
    args = parser.parse_args()
    build(args.out)
    if args.serve:
        serve(args.out, args.serve)


if __name__ == "__main__":
    main()
