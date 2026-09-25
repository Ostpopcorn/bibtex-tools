"""Run the steps of all commands on bib files at once, e.g., for the live
preview of the GUI.

Unlike the main functions of the commands, the pipeline works on strings,
never asks for input, and keeps track of where each entry comes from and what
changed. The steps are run in the following order:

1. read the sources, expanding the abbreviations (`clean`)
2. combine the entries of all sources (`combine`)
3. keep only cited entries (`filter-cited`)
4. remove duplicate entries
5. clean the fields, e.g., months and pages, and add arXiv categories
   (`modernize`)
6. remove fields
7. replace the IDs (`modernize`)
8. abbreviate journal names (`modernize`)
9. replace unicode characters (`clean`)
10. rename duplicate IDs
"""
import copy
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.bparser import BibTexParser

from .clean_bib_file import (get_duplicate_index_pairs, remove_shorter_duplicate,
                             replace_duplicate_ids, replace_unicode_in_entry)
from .const import KEY_ENTRYTYPE, KEY_ID
from .filter_bib_file import filter_cited_entries
from .modernize_bib_file import modernize_entry
from .util import format_bib_entries, parse_bib_string

DUPLICATES_KEEP = "keep"
DUPLICATES_REMOVE_SHORTER = "remove-shorter"
DUPLICATES_CHOOSE = "choose"


@dataclass
class PipelineOptions:
    """Settings of all steps. The defaults only format the entries."""
    #: Abbreviations that are expanded, e.g., from `util.load_abbr`
    abbr: Optional[dict] = None
    #: Keep only these cited keys and the entries they refer to (if not None)
    cited_keys: Optional[frozenset] = None
    #: One of `DUPLICATES_KEEP`, `DUPLICATES_REMOVE_SHORTER`, and
    #: `DUPLICATES_CHOOSE`
    duplicates: str = DUPLICATES_KEEP
    #: For `DUPLICATES_CHOOSE`: pair of origins -> origin of the entry to
    #: remove, or `None` to keep both. Pairs without a decision are kept.
    duplicate_decisions: dict = field(default_factory=dict)
    #: Fields that are cleaned with `modernize_bib_file.CLEAN_FUNC`
    clean_fields: tuple = ()
    shield_title: bool = False
    arxiv: bool = False
    #: Returns the primary category of an arXiv eprint, or None
    arxiv_lookup: Optional[Callable] = None
    remove_fields: tuple = ()
    replace_ids: bool = False
    iso4: bool = False
    replace_unicode: bool = False
    rename_duplicate_ids: bool = False
    sort_by_id: bool = True


@dataclass
class OutputEntry:
    #: (index of the source, index of the entry in the source)
    origin: tuple
    entry: dict
    #: The entry as it is written in the output
    text: str
    #: First line of the entry in the output, starting at 1
    line: int
    id_changed: bool
    added: set
    changed: set
    removed: set


@dataclass
class PipelineResult:
    #: Content of the output bib file
    text: str
    #: Entries in the order of the output
    entries: list
    #: origin -> entry as it was read from the source
    originals: dict
    #: origin -> reason why the entry is not in the output
    removed: dict
    #: Pairs of origins of duplicate entries (None if not searched)
    duplicate_pairs: Optional[list]
    #: Pairs of duplicate entries that were kept since no decision was made
    unresolved_pairs: list
    #: Cited keys that are not in the sources
    missing_keys: set
    #: index of the source -> IDs of entries that could not be read
    unreadable: dict
    #: Old ID -> number of entries with this ID, if they were renamed
    renamed_ids: dict
    #: (logging level, message)
    messages: list


def _count(number, word, words):
    return "{:d} {}".format(number, word if number == 1 else words)

def compare_entries(original, entry):
    """Return the names of the added, changed, and removed fields."""
    ignore = (KEY_ID, KEY_ENTRYTYPE)
    fields_orig = set(original) - set(ignore)
    fields_new = set(entry) - set(ignore)
    changed = set(_field for _field in fields_orig & fields_new
                  if original[_field] != entry[_field])
    return fields_new - fields_orig, changed, fields_orig - fields_new


class Pipeline:
    """Runs all steps on bib files. The read entries and the found duplicate
    pairs are cached, so that changing the other options is fast."""
    def __init__(self):
        self._loaded_key = None
        self._loaded = None
        self._pairs_key = None
        self._pairs = None

    def load(self, sources, abbr=None):
        """Read the sources, a list of `(name, text)` of bib files. Returns
        the entries, their origins, and the IDs of unreadable entries."""
        key = (tuple(sources), abbr)
        if self._loaded is None or self._loaded_key != key:
            entries, origins, unreadable = [], [], {}
            for _src_idx, (_name, _text) in enumerate(sources):
                bib_database, skipped = parse_bib_string(
                    _text, abbr=abbr, source=_name, return_skipped=True)
                if skipped:
                    unreadable[_src_idx] = skipped
                for _idx, _entry in enumerate(bib_database.entries):
                    entries.append(_entry)
                    origins.append((_src_idx, _idx))
            self._loaded_key = (tuple(sources), copy.copy(abbr))
            self._loaded = (entries, origins, unreadable)
        return self._loaded

    def find_duplicates(self, entries, origins):
        """Return the pairs of origins of duplicate entries."""
        key = (self._loaded_key, tuple(origins))
        if self._pairs is None or self._pairs_key != key:
            self._pairs = [(origins[_idx1], origins[_idx2])
                           for _idx1, _idx2 in get_duplicate_index_pairs(entries)]
            self._pairs_key = key
        return self._pairs

    def run(self, sources, options):
        """Run all steps on the sources, a list of `(name, text)` of bib
        files, and return a `PipelineResult`."""
        loaded, origins, unreadable = self.load(sources, options.abbr)
        originals = dict(zip(origins, loaded))
        entries = copy.deepcopy(loaded)
        messages = []
        for _src_idx, _ids in unreadable.items():
            messages.append((logging.WARNING,
                             "Could not read {} from {} (check for syntax "
                             "errors): {}".format(
                                 _count(len(_ids), "entry", "entries"),
                                 sources[_src_idx][0], ", ".join(_ids))))

        removed = {}
        missing = set()
        if options.cited_keys is not None:
            kept = set(map(id, filter_cited_entries(entries,
                                                    options.cited_keys)))
            for _entry, _origin in zip(entries, origins):
                if id(_entry) not in kept:
                    removed[_origin] = "not cited"
            missing = (set(options.cited_keys)
                       - set(_entry[KEY_ID] for _entry in entries))
            if missing:
                messages.append((logging.WARNING,
                                 "{} not in the bib files: {}".format(
                                     _count(len(missing), "cited key is",
                                            "cited keys are"),
                                     ", ".join(sorted(missing)))))
            entries, origins = _drop(entries, origins, removed)

        pairs = None
        unresolved = []
        if options.duplicates != DUPLICATES_KEEP:
            pairs = self.find_duplicates(entries, origins)
            by_origin = dict(zip(origins, entries))
            for _pair in pairs:
                if _pair[0] in removed or _pair[1] in removed:
                    continue
                _entry1, _entry2 = by_origin[_pair[0]], by_origin[_pair[1]]
                if options.duplicates == DUPLICATES_REMOVE_SHORTER:
                    _shorter = remove_shorter_duplicate(_entry1, _entry2)
                    _remove = _pair[0] if _shorter is _entry1 else _pair[1]
                elif _pair in options.duplicate_decisions:
                    _remove = options.duplicate_decisions[_pair]
                    if _remove is None:
                        continue
                else:
                    unresolved.append(_pair)
                    continue
                _keep = _pair[1] if _remove == _pair[0] else _pair[0]
                removed[_remove] = "duplicate of {}".format(
                    by_origin[_keep][KEY_ID])
            if unresolved:
                messages.append((logging.INFO,
                                 "{} of duplicate entries kept until you "
                                 "choose which entry to remove".format(
                                     _count(len(unresolved), "pair",
                                            "pairs"))))
            entries, origins = _drop(entries, origins, removed)

        for _idx, _entry in enumerate(entries):
            _entry = modernize_entry(_entry,
                                     remove_fields=options.remove_fields,
                                     replace_ids=options.replace_ids,
                                     arxiv=options.arxiv, iso4=options.iso4,
                                     clean_fields=options.clean_fields,
                                     arxiv_lookup=options.arxiv_lookup,
                                     shield_title=options.shield_title)
            if options.replace_unicode:
                _entry = replace_unicode_in_entry(_entry)
            entries[_idx] = _entry

        renamed = {}
        if options.rename_duplicate_ids:
            entries, renamed = replace_duplicate_ids(entries, return_dupl=True)
            if renamed:
                messages.append((logging.INFO,
                                 "Renamed entries with duplicate IDs (the "
                                 "first entry keeps its ID): {}".format(
                                     ", ".join(renamed))))

        order = list(range(len(entries)))
        if options.sort_by_id:
            order.sort(key=lambda _idx: BibDatabase.entry_sort_key(
                entries[_idx], (KEY_ID,)))
        output = []
        line = 1
        for _idx in order:
            _entry, _origin = entries[_idx], origins[_idx]
            _text = format_bib_entries([_entry], order_entries_by=None)
            _original = originals[_origin]
            _added, _changed, _removed = compare_entries(_original, _entry)
            output.append(OutputEntry(
                origin=_origin, entry=_entry, text=_text, line=line,
                id_changed=_entry[KEY_ID] != _original[KEY_ID],
                added=_added, changed=_changed, removed=_removed))
            line += _text.count("\n") + 1
        text = "\n".join(_out.text for _out in output)
        return PipelineResult(text=text, entries=output, originals=originals,
                              removed=removed, duplicate_pairs=pairs,
                              unresolved_pairs=unresolved,
                              missing_keys=missing, unreadable=unreadable,
                              renamed_ids=renamed, messages=messages)


def _drop(entries, origins, removed):
    kept = [(_entry, _origin) for _entry, _origin in zip(entries, origins)
            if _origin not in removed]
    return [k[0] for k in kept], [k[1] for k in kept]


def run_pipeline(sources, options=None):
    """Run all steps on the sources, a list of `(name, text)` of bib files."""
    if options is None:
        options = PipelineOptions()
    return Pipeline().run(sources, options)


_FIELD_ALIASES = {k: v for k, v in BibTexParser().alt_dict.items()
                  if k != "keywords"}
_RE_FIELD = re.compile(r'^[ \t]*([A-Za-z][\w:.+-]*)[ \t]*=', re.MULTILINE)

def get_field_spans(bib_str, start=0, end=None):
    """Return the start and end index of the fields of an entry in a bib
    string between `start` and `end`, by the field names that the parser
    uses. Only fields that start on a new line are found."""
    if end is None:
        end = len(bib_str)
    matches = list(_RE_FIELD.finditer(bib_str, start, end))
    spans = {}
    for _idx, _match in enumerate(matches):
        _end = matches[_idx+1].start() if _idx+1 < len(matches) else end
        _value = bib_str[_match.start():_end].rstrip()
        if _idx+1 == len(matches) and _value.endswith(("}", ")")):
            # the closing brace of the entry
            _value = _value[:-1].rstrip()
        _name = _match.group(1).lower()
        spans[_FIELD_ALIASES.get(_name, _name)] = (
            _match.start(), _match.start() + len(_value))
    return spans

_RE_OUTPUT_FIELD = re.compile(r'^\t(\S+) = ')

def get_output_field_lines(entry_text):
    """Return the first and last line (starting at 0) of each field in an
    entry as it is written in the output."""
    lines = entry_text.split("\n")
    spans = {}
    current = None
    for _idx, _line in enumerate(lines[1:], start=1):
        _match = _RE_OUTPUT_FIELD.match(_line)
        if _match:
            current = _match.group(1)
            spans[current] = [_idx, _idx]
        elif _line == "}":
            break
        elif current is not None:
            spans[current][1] = _idx
    return {k: tuple(v) for k, v in spans.items()}
