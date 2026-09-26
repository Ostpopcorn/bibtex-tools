"""Bridge between the web app in the `web` folder and the pipeline. The web
app runs this module in the browser with Pyodide and exchanges JSON strings
with it."""
import bisect
import functools
import json
import re
from collections import defaultdict

from bibtexparser.bibdatabase import UndefinedString

from .const import DEFAULT_REMOVE, KEY_CATEGORY, KEY_EPRINT, KEY_ID
from .filter_bib_file import parse_bbl_keys
from .modernize_bib_file import CLEAN_FUNC, convert_arxiv_style
from .pipeline import DUPLICATES_KEEP, Pipeline, PipelineOptions
from .util import (format_bib_entries, get_entry_spans, get_field_spans,
                   parse_abbr_string)

_PIPELINE = Pipeline()
_ABBR_CACHE = {}


def defaults():
    """Return the default settings of the web app."""
    return json.dumps({"remove_fields": DEFAULT_REMOVE,
                       "clean_fields": list(CLEAN_FUNC)})


def _origin_str(origin):
    return "{}:{}".format(*origin)

def _origin(origin_str):
    return tuple(int(k) for k in origin_str.split(":"))

def normalize_eprint(eprint):
    return re.sub(r'^arxiv:', '', eprint.strip(), flags=re.IGNORECASE)

def _parse_abbr(abbr_str):
    if abbr_str not in _ABBR_CACHE:
        _ABBR_CACHE.clear()
        _ABBR_CACHE[abbr_str] = parse_abbr_string(abbr_str)
    return _ABBR_CACHE[abbr_str]


class _Lines:
    """Converts indices of a string to line numbers (starting at 0)."""
    def __init__(self, text):
        self.newlines = [m.start() for m in re.finditer("\n", text)]

    def __call__(self, idx):
        return bisect.bisect_left(self.newlines, idx)


def _normalize_value(value):
    """The value of a field as it is shown, without the braces or quotes
    around it and with single spaces."""
    if len(value) >= 2 and value[0] + value[-1] in ("{}", '""'):
        value = value[1:-1]
    return " ".join(value.split())

def _locate_fields(text, start, end, line):
    """Return the lines, the value, and the written name of each field of the
    entry between `start` and `end`."""
    fields = {}
    for _key, (_start, _end, _vstart, _vend) in get_field_spans(
            text, start, end).items():
        fields[_key] = {"lines": [line(_start), line(_end-1)],
                        "value": _normalize_value(text[_vstart:_vend]),
                        "name": text[_start:_vstart].split("=")[0].strip().lower()}
    return fields

@functools.lru_cache(maxsize=16)
def _locate_entries(text):
    """Return the lines of the entries and their fields in a bib string."""
    line = _Lines(text)
    return [{"id": _id, "lines": [line(_start), line(_end-1)],
             "fields": _locate_fields(text, _start, _end, line)}
            for _id, _start, _end in get_entry_spans(text)]

def _source_entries(source_idx, text, originals):
    """Locate the entries of a source in its text and match them to the read
    entries."""
    origins = defaultdict(list)
    for _origin, _entry in originals.items():
        if _origin[0] == source_idx:
            origins[_entry[KEY_ID]].append(_origin)
    entries = []
    for _entry in _locate_entries(text):
        _origins = origins.get(_entry["id"])
        entries.append(dict(_entry, origin=(_origin_str(_origins.pop(0))
                                            if _origins else None)))
    return entries

def _output_entry(out, original, located):
    """An entry of the output for the web app. A field is changed if its
    value or name is shown differently than in the original, e.g., an
    expanded abbreviation (`@string`). Differences in whitespace and in
    braces or quotes around values are not changes."""
    fields = _locate_fields(out.text, 0, len(out.text), _Lines(out.text))
    if located is None:
        # the entry could not be found in the text of the original
        added, changed, removed = out.added, out.changed, out.removed
    else:
        before = located["fields"]
        added = set(fields) - set(before)
        removed = set(before) - set(fields)
        changed = set(_key for _key in set(fields) & set(before)
                      if fields[_key]["value"] != before[_key]["value"]
                      or before[_key]["name"] != _key)
    return {"origin": _origin_str(out.origin),
            "id": out.entry[KEY_ID],
            "original_id": original[KEY_ID],
            "text": out.text,
            "line": out.line,
            "id_changed": out.id_changed,
            "type_changed": out.type_changed,
            "added": sorted(added),
            "changed": sorted(changed),
            "removed": sorted(removed),
            "fields": {k: v["lines"] for k, v in fields.items()}}


def run(request_json):
    """Run the pipeline for a request of the web app, see `web/app.js`."""
    request = json.loads(request_json)
    try:
        return json.dumps(_run(request))
    except UndefinedString as err:
        return json.dumps({"error": "The abbreviation {} is not defined. Add "
                                    "the abbreviation file (@string) under "
                                    "Clean.".format(err)})


def _run(request):
    sources = [(_src["name"], _src["text"]) for _src in request["sources"]]
    opts = request["options"]
    categories = {normalize_eprint(k): v
                  for k, v in request.get("arxiv_categories", {}).items()}
    cited = None
    if request.get("bbl") is not None:
        cited, backend = parse_bbl_keys(request["bbl"])
        cited = frozenset(cited)
    abbr = None
    if request.get("abbr") is not None:
        abbr = _parse_abbr(request["abbr"])
    decisions = {}
    for (_first, _second), _remove in opts.get("decisions", []):
        decisions[(_origin(_first), _origin(_second))] = (
            _origin(_remove) if _remove else None)
    options = PipelineOptions(
        abbr=abbr, cited_keys=cited,
        duplicates=opts.get("duplicates", DUPLICATES_KEEP),
        duplicate_decisions=decisions,
        clean_fields=tuple(opts.get("clean_fields", ())),
        shield_title=opts.get("shield_title", False),
        arxiv=opts.get("arxiv", False),
        arxiv_lookup=lambda eprint: categories.get(normalize_eprint(eprint)),
        arxiv_style=opts.get("arxiv_style"),
        remove_fields=tuple(opts.get("remove_fields", ())),
        replace_ids=opts.get("replace_ids", False),
        iso4=opts.get("iso4", False),
        replace_unicode=opts.get("replace_unicode", False),
        rename_duplicate_ids=opts.get("rename_duplicate_ids", False),
        sort_by_id=opts.get("sort_by_id", True))
    result = _PIPELINE.run(sources, options)

    pair_origins = set()
    for _pair in result.duplicate_pairs or []:
        pair_origins.update(_pair)
    fields = set()
    eprints = set()
    for _entry in result.originals.values():
        fields.update(_entry)
        # The eprints after changing the style of arXiv preprints
        if options.arxiv_style is not None:
            _entry = convert_arxiv_style(dict(_entry), options.arxiv_style)
        if KEY_EPRINT in _entry and KEY_CATEGORY not in _entry:
            eprints.add(normalize_eprint(_entry[KEY_EPRINT]))
    sources_out = [{"name": _name,
                    "entries": _source_entries(_idx, _text, result.originals)}
                   for _idx, (_name, _text) in enumerate(sources)]
    located = {_entry["origin"]: _entry for _source in sources_out
               for _entry in _source["entries"] if _entry["origin"]}
    entries = [_output_entry(_out, result.originals[_out.origin],
                             located.get(_origin_str(_out.origin)))
               for _out in result.entries]
    # The web app only needs the lines of the fields
    for _source in sources_out:
        _source["entries"] = [dict(_entry, fields={
            k: v["lines"] for k, v in _entry["fields"].items()})
            for _entry in _source["entries"]]
    return {
        "text": result.text,
        "entries": entries,
        "sources": sources_out,
        "removed": {_origin_str(k): v for k, v in result.removed.items()},
        "duplicate_pairs": (None if result.duplicate_pairs is None else
                            [[_origin_str(k) for k in _pair]
                             for _pair in result.duplicate_pairs]),
        "unresolved_pairs": [[_origin_str(k) for k in _pair]
                             for _pair in result.unresolved_pairs],
        "pair_entries": {_origin_str(k): format_bib_entries(
                             [result.originals[k]], order_entries_by=None)
                         for k in sorted(pair_origins)},
        "cited": (None if cited is None else
                  {"count": len(cited), "backend": backend,
                   "kept": len(result.originals) - list(
                       result.removed.values()).count("not cited"),
                   "missing": sorted(result.missing_keys)}),
        "fields": sorted(fields - {KEY_ID, "ENTRYTYPE"}),
        "eprints": sorted(eprints),
        "renamed_ids": sorted(result.renamed_ids),
        "messages": [[{10: "debug", 20: "info", 30: "warning"}.get(_level, "error"),
                      _msg] for _level, _msg in result.messages],
    }
