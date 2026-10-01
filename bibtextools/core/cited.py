"""Keep the entries that a .bbl file cites, and the entries they refer to,
e.g., with crossref."""
import logging
import re
from dataclasses import dataclass, field

from ..const import KEY_ID, KEY_IDS, KEYS_REFERENCE


_RE_BIBITEM = re.compile(r"\\bibitem(?![a-zA-Z])\s*")
_RE_BIBITEM_KEY = re.compile(r"\s*\{([^}]+)\}")

def get_bibitem_keys(content):
    """Return the keys of all `\\bibitem[label]{key}` in a BibTeX .bbl file.
    The optional label can span multiple lines, since BibTeX wraps long
    lines, and can contain braces, e.g., `[DSR{\\etalchar{+}}18]`."""
    keys = set()
    for _match in _RE_BIBITEM.finditer(content):
        idx = _match.end()
        if content.startswith("[", idx):
            depth = 0
            for idx in range(idx, len(content)):
                depth += {"{": 1, "}": -1}.get(content[idx], 0)
                if content[idx] == "]" and depth == 0:
                    break
            idx += 1
        _key = _RE_BIBITEM_KEY.match(content, idx)
        if _key:
            keys.add(_key.group(1))
    return keys

def parse_bbl_keys(content):
    """Extract citation keys from the content of a .bbl file, auto-detecting
    the backend."""
    biblatex_keys = set(re.findall(r"\\entry\{([^}]+)\}", content))
    bibtex_keys = get_bibitem_keys(content)
    if biblatex_keys and not bibtex_keys:
        return biblatex_keys, "biblatex"
    if bibtex_keys and not biblatex_keys:
        return bibtex_keys, "bibtex"
    return biblatex_keys | bibtex_keys, "unknown"


def get_referenced_ids(entry):
    """Return the IDs of all entries that an entry refers to, e.g., the
    parent of a crossref, whose fields the entry inherits."""
    ids = []
    for _key in KEYS_REFERENCE:
        ids.extend([k.strip() for k in entry.get(_key, "").split(",")
                    if k.strip()])
    return ids

def add_referenced_ids(ids, entries):
    """Add the IDs of all entries that the entries with the given IDs refer
    to, recursively. Only IDs of existing entries are added."""
    references = {}
    for entry in entries:
        references.setdefault(entry[KEY_ID], []).extend(get_referenced_ids(entry))
    ids = set(ids)
    stack = list(ids)
    while stack:
        for _ref in references.get(stack.pop(), []):
            if _ref in references and _ref not in ids:
                ids.add(_ref)
                stack.append(_ref)
    return ids

def filter_cited_entries(entries, cited_keys):
    """Return the entries that are cited and the entries that they refer to,
    e.g., with crossref, in their original order."""
    keep_ids = add_referenced_ids(cited_keys, entries)
    return [entry for entry in entries if entry.get(KEY_ID) in keep_ids]


@dataclass
class CitedEntries:
    """The result of `resolve_cited_duplicates`, by the index of the entry."""
    #: index -> entry, a copy if its ID or ids changed
    kept: dict = field(default_factory=dict)
    #: index -> reason why the entry is not kept
    removed: dict = field(default_factory=dict)
    #: index -> other cited keys of the entry, which were added to its ids
    aliases: dict = field(default_factory=dict)
    #: Index pairs of duplicates that are both kept, since both keys are
    #: cited and the backend has no aliases for keys
    both_cited: list = field(default_factory=list)
    #: (logging level, message)
    notes: list = field(default_factory=list)

def _plural(number, word, words):
    return "{:d} {}".format(number, word if number == 1 else words)

def resolve_cited_duplicates(entries, cited_keys, pairs=(), resolve=None,
                             aliases=False):
    """Keep the cited entries and the entries they refer to, e.g., with
    crossref, and remove duplicate entries, so that every cited key stays.

    `pairs` are the index pairs of duplicate entries, e.g., from
    `get_duplicate_index_pairs`, and `resolve(idx1, idx2)` returns the index
    of the entry to remove, or None to keep both. The kept entry takes over
    the cited keys of the removed one: it is renamed to the cited key, or, if
    its own key is cited as well, the other key is added to its `ids`, which
    biblatex resolves (`aliases`). BibTeX has no aliases for keys, so without
    `aliases`, both entries of a pair are kept if both keys are cited.

    Of other entries with the same key, only the first one is kept, since
    BibTeX and biber use the first one. The entries are not changed."""
    needed = add_referenced_ids(cited_keys, entries)
    # The cited keys of each entry, and its position among entries with the
    # same key, which is the position of the entry whose key it takes over
    keys = {_idx: [_entry[KEY_ID]] if _entry[KEY_ID] in needed else []
            for _idx, _entry in enumerate(entries)}
    position = list(range(len(entries)))
    result = CitedEntries()
    for _idx1, _idx2 in pairs:
        if _idx1 in result.removed or _idx2 in result.removed:
            continue
        _remove = resolve(_idx1, _idx2)
        if _remove is None:
            continue
        _keep = _idx2 if _remove == _idx1 else _idx1
        _new = [k for k in keys[_remove] if k not in keys[_keep]]
        if _new and keys[_keep] and not aliases:
            result.both_cited.append((_idx1, _idx2))
            continue
        result.removed[_remove] = "duplicate of {}".format(entries[_keep][KEY_ID])
        if _new:
            result.removed[_remove] += ", which takes over its key"
            if not keys[_keep]:
                position[_keep] = position[_remove]
            keys[_keep].extend(_new)

    renamed, merged = [], []
    for _idx, _entry in enumerate(entries):
        if _idx in result.removed:
            continue
        if not keys[_idx]:
            result.removed[_idx] = "not cited"
            continue
        _own = _entry[KEY_ID]
        _key = _own if _own in keys[_idx] else keys[_idx][0]
        _others = [k for k in keys[_idx] if k != _key]
        if _key != _own or _others:
            _entry = dict(_entry)
            _entry[KEY_ID] = _key
            if _key != _own:
                renamed.append("{} → {}".format(_own, _key))
            if _others:
                _ids = [k.strip() for k in _entry.get(KEY_IDS, "").split(",")
                        if k.strip()]
                _entry[KEY_IDS] = ", ".join(_ids + [k for k in _others
                                                    if k not in _ids])
                result.aliases[_idx] = _others
                merged.append("{} (also {})".format(_key, ", ".join(_others)))
        result.kept[_idx] = _entry

    # Of entries with the same key, LaTeX uses the first one
    same = []
    first = set()
    for _idx in sorted(result.kept, key=lambda k: position[k]):
        _key = result.kept[_idx][KEY_ID]
        if _key in first:
            del result.kept[_idx]
            result.removed[_idx] = "same key as an earlier entry, which LaTeX uses"
            same.append(_key)
        first.add(_key)

    if renamed:
        result.notes.append((logging.INFO,
            "{} of removed duplicates: {}".format(
                _plural(len(renamed), "entry takes over the cited key",
                        "entries take over the cited keys"),
                ", ".join(renamed))))
    if merged:
        result.notes.append((logging.INFO,
            "Merged {} whose keys are both cited, with the other keys in "
            "ids for biblatex: {}".format(
                _plural(len(merged), "pair of duplicates", "pairs of duplicates"),
                ", ".join(merged))))
    if result.both_cited:
        result.notes.append((logging.WARNING,
            "Kept both entries of {}, since both keys are cited and BibTeX has "
            "no aliases for keys: {}. Cite one key of each pair in your .tex "
            "file to remove the duplicates.".format(
                _plural(len(result.both_cited), "pair of duplicates",
                        "pairs of duplicates"),
                ", ".join("{} and {}".format(entries[_idx1][KEY_ID],
                                             entries[_idx2][KEY_ID])
                          for _idx1, _idx2 in result.both_cited))))
    if same:
        result.notes.append((logging.WARNING,
            "Removed {} with the same key as an earlier entry, which LaTeX "
            "uses: {}".format(_plural(len(same), "entry", "entries"),
                              ", ".join(sorted(set(same))))))
    return result
