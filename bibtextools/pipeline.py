"""Run the steps of `core` on bib files at once, e.g., for the live preview
of the GUI.

Unlike the main functions of the commands, the pipeline works on strings,
never asks for input, and keeps track of where each entry comes from and what
changed. Each step is independent and runs only if its setting is on. The
steps are run in the following order:

1. read the sources, expanding the abbreviations (`@string`)
2. combine the entries of all sources
3. remove duplicate entries (`core.duplicates`)
4. keep only cited entries (`core.cited`): with duplicates of cited
   entries, the kept entry takes over the cited key of the removed one
5. on each entry, see `entry_steps`: clean the fields, e.g., months and
   pages, protect the titles, write arXiv preprints in one style, add arXiv
   categories, convert the fields to biblatex or BibTeX, remove fields,
   generate keys, abbreviate journal names, and replace unicode characters
6. rename duplicate keys (`core.keys`)
"""
import copy
import functools
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

from bibtexparser.bibdatabase import BibDatabase

from .const import KEY_ENTRYTYPE, KEY_ID
from .core.arxiv import add_arxiv_category, convert_arxiv_style, get_arxiv_category
from .core.cited import add_referenced_ids, resolve_cited_duplicates
from .core.duplicates import (get_duplicate_index_pairs,
                              get_duplicate_index_pairs_of,
                              remove_shorter_duplicate)
from .core.fields import clean_fields, remove_fields
from .core.formats import to_biblatex, to_bibtex
from .core.journals import abbreviate_journalname
from .core.keys import generate_key_in_entry, rename_duplicate_keys
from .core.latex import replace_unicode_in_entry
from .core.titles import TITLE_KEEP, protect_title_in_entry
from .util import format_bib_entries, read_bib_string

#: The output is for biblatex (with biber) or for BibTeX
OUTPUT_BIBLATEX = "biblatex"
OUTPUT_BIBTEX = "bibtex"
OUTPUTS = (OUTPUT_BIBLATEX, OUTPUT_BIBTEX)

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
    #: Backend of the .bbl file with the cited keys, e.g., "biblatex", which
    #: resolves other keys of an entry in its ids field
    bbl_backend: Optional[str] = None
    #: The output is for `OUTPUT_BIBLATEX` or `OUTPUT_BIBTEX`, or None for
    #: the backend of the .bbl file, see `output_format`
    output: Optional[str] = None
    #: One of `DUPLICATES_KEEP`, `DUPLICATES_REMOVE_SHORTER`, and
    #: `DUPLICATES_CHOOSE`
    duplicates: str = DUPLICATES_KEEP
    #: For `DUPLICATES_CHOOSE`: pair of origins -> origin of the entry to
    #: remove, or `None` to keep both. Pairs without a decision are kept.
    duplicate_decisions: dict = field(default_factory=dict)
    #: Fields that are cleaned with `core.fields.FIELD_CLEANERS`
    clean_fields: tuple = ()
    #: How titles are protected, one of `core.titles.TITLE_MODES`
    titles: str = TITLE_KEEP
    #: How arXiv preprints are written, one of `core.arxiv.ARXIV_STYLES`, or
    #: None to keep them as they are
    arxiv_style: Optional[str] = None
    #: Add the categories of arXiv eprints
    arxiv: bool = False
    #: Returns the primary category of an arXiv eprint, or None (default:
    #: `core.arxiv.get_arxiv_category`, which downloads it)
    arxiv_lookup: Optional[Callable] = None
    #: Use the fields and entry types of the output, see `output_format`
    #: (default: biblatex) and `core.formats`
    convert_fields: bool = False
    remove_fields: tuple = ()
    #: Replace the keys with keys of the author, year, and title. This is
    #: skipped while filtering by cited keys, which must stay.
    generate_keys: bool = False
    iso4: bool = False
    replace_unicode: bool = False
    rename_duplicate_keys: bool = False
    sort_by_id: bool = True

    def output_format(self):
        """One of `OUTPUTS`: `output`, or else the backend of the .bbl file
        if it is known, or else None."""
        if self.output is not None:
            if self.output not in OUTPUTS:
                raise ValueError("Unknown output: {}".format(self.output))
            return self.output
        return self.bbl_backend if self.bbl_backend in OUTPUTS else None


def entry_steps(options, generate_keys=None):
    """The steps on each entry for the options, in their order, as functions
    that take an entry and return it."""
    if generate_keys is None:
        generate_keys = options.generate_keys
    steps = []
    if options.clean_fields:
        steps.append(functools.partial(clean_fields,
                                       fields=options.clean_fields))
    if options.titles != TITLE_KEEP:
        steps.append(functools.partial(protect_title_in_entry,
                                       mode=options.titles))
    if options.arxiv_style is not None:
        steps.append(functools.partial(convert_arxiv_style,
                                       style=options.arxiv_style))
    if options.arxiv:
        steps.append(functools.partial(
            add_arxiv_category,
            lookup=options.arxiv_lookup or get_arxiv_category))
    if options.convert_fields:
        steps.append(to_bibtex if options.output_format() == OUTPUT_BIBTEX
                     else to_biblatex)
    if options.remove_fields:
        steps.append(functools.partial(remove_fields,
                                       fields=options.remove_fields))
    if generate_keys:
        steps.append(generate_key_in_entry)
    if options.iso4:
        steps.append(abbreviate_journalname)
    if options.replace_unicode:
        steps.append(replace_unicode_in_entry)
    return steps


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
    #: The entry type changed, e.g., from @misc to @article
    type_changed: bool
    added: set
    changed: set
    removed: set
    #: Other cited keys of the entry, which were added to its ids
    aliases: tuple = ()


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
    #: Origins of the entries whose own key is cited, or that cited entries
    #: refer to
    cited_origins: set = field(default_factory=set)
    #: Pairs of duplicate entries that are both kept, since both keys are
    #: cited and the .bbl file is not from biblatex, which has aliases
    both_cited: list = field(default_factory=list)
    #: Pairs of duplicate entries with a decision. Pairs whose other entry
    #: was already removed no longer matter and are in neither this list nor
    #: `unresolved_pairs`.
    decided_pairs: list = field(default_factory=list)
    #: index of the source -> undefined abbreviations (`@string`), which are
    #: kept as text
    undefined_strings: dict = field(default_factory=dict)


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
        the entries, their origins, the IDs of unreadable entries, and the
        undefined abbreviations (`@string`), both by the index of the
        source."""
        key = (tuple(sources), abbr)
        if self._loaded is None or self._loaded_key != key:
            entries, origins, unreadable, undefined = [], [], {}, {}
            for _src_idx, (_name, _text) in enumerate(sources):
                bib_database, skipped, _undefined = read_bib_string(
                    _text, abbr=abbr, source=_name)
                if skipped:
                    unreadable[_src_idx] = skipped
                if _undefined:
                    undefined[_src_idx] = _undefined
                for _idx, _entry in enumerate(bib_database.entries):
                    entries.append(_entry)
                    origins.append((_src_idx, _idx))
            self._loaded_key = (tuple(sources), copy.copy(abbr))
            self._loaded = (entries, origins, unreadable, undefined)
        return self._loaded

    def find_duplicates(self, entries, origins, among=None):
        """Return the pairs of origins of duplicate entries, and warnings.
        With the indices `among`, only the duplicates of these entries and
        of their duplicates in turn, see `get_duplicate_index_pairs_of`."""
        key = (self._loaded_key, tuple(origins),
               None if among is None else tuple(among))
        if self._pairs is None or self._pairs_key != key:
            if among is None:
                index_pairs, warnings = get_duplicate_index_pairs(entries), []
            else:
                index_pairs, warnings = get_duplicate_index_pairs_of(entries,
                                                                     among)
            self._pairs = ([(origins[_idx1], origins[_idx2])
                            for _idx1, _idx2 in index_pairs], warnings)
            self._pairs_key = key
        return self._pairs

    def run(self, sources, options):
        """Run all steps on the sources, a list of `(name, text)` of bib
        files, and return a `PipelineResult`."""
        loaded, origins, unreadable, undefined = self.load(sources,
                                                           options.abbr)
        originals = dict(zip(origins, loaded))
        entries = copy.deepcopy(loaded)
        messages = []
        for _src_idx, _ids in unreadable.items():
            messages.append((logging.WARNING,
                             "Could not read {} from {} (check for syntax "
                             "errors): {}".format(
                                 _count(len(_ids), "entry", "entries"),
                                 sources[_src_idx][0], ", ".join(_ids))))
        for _src_idx, _names in undefined.items():
            messages.append((logging.WARNING,
                             "{} not defined in {}, so the names are kept as "
                             "text: {}. Add the file with their @string "
                             "definitions.".format(
                                 _count(len(_names), "abbreviation is",
                                        "abbreviations are"),
                                 sources[_src_idx][0], ", ".join(_names))))

        removed = {}
        missing = set()
        pairs = None
        unresolved = []
        decided = []
        aliases = {}
        cited_origins = set()
        both_cited = []

        def resolve(idx1, idx2):
            """The index of the duplicate entry to remove, or None."""
            pair = (origins[idx1], origins[idx2])
            if options.duplicates == DUPLICATES_REMOVE_SHORTER:
                shorter = remove_shorter_duplicate(entries[idx1], entries[idx2])
                return idx1 if shorter is entries[idx1] else idx2
            if pair in options.duplicate_decisions:
                decided.append(pair)
                remove = options.duplicate_decisions[pair]
                if remove is None:
                    return None
                return idx1 if remove == pair[0] else idx2
            unresolved.append(pair)
            return None

        # The cited entries and the entries they refer to, which must stay
        needed = None
        if options.cited_keys is not None:
            needed = add_referenced_ids(options.cited_keys, entries)
            cited_origins = set(_origin for _entry, _origin
                                in zip(entries, origins)
                                if _entry[KEY_ID] in needed)

        index_pairs = []
        if options.duplicates != DUPLICATES_KEEP:
            # Only duplicates of the entries that must stay matter
            among = None if needed is None else [
                _idx for _idx, _entry in enumerate(entries)
                if _entry[KEY_ID] in needed]
            pairs, warnings = self.find_duplicates(entries, origins, among)
            messages.extend(warnings)
            index = {_origin: _idx for _idx, _origin in enumerate(origins)}
            index_pairs = [(index[_origin1], index[_origin2])
                           for _origin1, _origin2 in pairs]

        if options.cited_keys is not None:
            # The kept entry of duplicates takes over the cited key of the
            # removed one, so that every cited key stays
            cited = resolve_cited_duplicates(
                entries, options.cited_keys, index_pairs, resolve,
                aliases=options.output_format() == OUTPUT_BIBLATEX)
            missing = (set(options.cited_keys)
                       - set(_entry[KEY_ID] for _entry in entries))
            if missing:
                messages.append((logging.WARNING,
                                 "{} not in the bib files: {}".format(
                                     _count(len(missing), "cited key is",
                                            "cited keys are"),
                                     ", ".join(sorted(missing)))))
            messages.extend(cited.notes)
            removed = {origins[_idx]: _reason
                       for _idx, _reason in cited.removed.items()}
            aliases = {origins[_idx]: tuple(_keys)
                       for _idx, _keys in cited.aliases.items()}
            both_cited = [(origins[_idx1], origins[_idx2])
                          for _idx1, _idx2 in cited.both_cited]
            kept = sorted(cited.kept)
            entries = [cited.kept[_idx] for _idx in kept]
            origins = [origins[_idx] for _idx in kept]
        else:
            for _idx1, _idx2 in index_pairs:
                if origins[_idx1] in removed or origins[_idx2] in removed:
                    continue
                _remove = resolve(_idx1, _idx2)
                if _remove is None:
                    continue
                _keep = _idx2 if _remove == _idx1 else _idx1
                removed[origins[_remove]] = "duplicate of {}".format(
                    entries[_keep][KEY_ID])
            entries, origins = _drop(entries, origins, removed)
        if unresolved:
            messages.append((logging.INFO,
                             "{} of duplicate entries kept until you "
                             "choose which entry to remove".format(
                                 _count(len(unresolved), "pair", "pairs"))))

        # The keys must stay the cited ones
        generate_keys = options.generate_keys and options.cited_keys is None
        if options.generate_keys and not generate_keys:
            messages.append((logging.INFO,
                             "Generate keys is skipped while filtering by a "
                             ".bbl file, since the keys must stay the cited "
                             "ones"))

        steps = entry_steps(options, generate_keys=generate_keys)
        for _idx, _entry in enumerate(entries):
            for _step in steps:
                _entry = _step(_entry)
            entries[_idx] = _entry

        renamed = {}
        if options.rename_duplicate_keys:
            entries, renamed = rename_duplicate_keys(entries)
            if renamed:
                messages.append((logging.INFO,
                                 "Renamed entries with duplicate keys (the "
                                 "first entry keeps its key): {}".format(
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
                type_changed=(_entry[KEY_ENTRYTYPE].lower()
                              != _original[KEY_ENTRYTYPE].lower()),
                added=_added, changed=_changed, removed=_removed,
                aliases=aliases.get(_origin, ())))
            line += _text.count("\n") + 1
        text = "\n".join(_out.text for _out in output)
        return PipelineResult(text=text, entries=output, originals=originals,
                              removed=removed, duplicate_pairs=pairs,
                              unresolved_pairs=unresolved,
                              missing_keys=missing, unreadable=unreadable,
                              renamed_ids=renamed, messages=messages,
                              cited_origins=cited_origins,
                              both_cited=both_cited, decided_pairs=decided,
                              undefined_strings=undefined)


def _drop(entries, origins, removed):
    kept = [(_entry, _origin) for _entry, _origin in zip(entries, origins)
            if _origin not in removed]
    return [k[0] for k in kept], [k[1] for k in kept]


def run_pipeline(sources, options=None):
    """Run all steps on the sources, a list of `(name, text)` of bib files."""
    if options is None:
        options = PipelineOptions()
    return Pipeline().run(sources, options)

