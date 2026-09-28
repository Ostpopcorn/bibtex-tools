"""Run the steps of all commands on bib files at once, e.g., for the live
preview of the GUI.

Unlike the main functions of the commands, the pipeline works on strings,
never asks for input, and keeps track of where each entry comes from and what
changed. The steps are run in the following order:

1. read the sources, expanding the abbreviations (`clean`)
2. combine the entries of all sources (`combine`)
3. remove duplicate entries
4. keep only cited entries (`filter-cited`): with duplicates of cited
   entries, the kept entry takes over the cited key of the removed one
5. clean the fields, e.g., months and pages, write arXiv preprints in one
   style, and add arXiv categories (`modernize`)
6. remove fields
7. replace the IDs (`modernize`)
8. abbreviate journal names (`modernize`)
9. replace unicode characters (`clean`)
10. rename duplicate IDs
"""
import copy
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

from bibtexparser.bibdatabase import BibDatabase

from .clean_bib_file import (get_duplicate_index_pairs,
                             get_duplicate_index_pairs_of,
                             remove_shorter_duplicate, replace_duplicate_ids,
                             replace_unicode_in_entry)
from .const import KEY_ENTRYTYPE, KEY_ID
from .filter_bib_file import add_referenced_ids, resolve_cited_duplicates
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
    #: Backend of the .bbl file with the cited keys, e.g., "biblatex", which
    #: resolves other keys of an entry in its ids field
    bbl_backend: Optional[str] = None
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
    #: How arXiv preprints are written, one of
    #: `modernize_bib_file.ARXIV_STYLES`, or None to keep them as they are
    arxiv_style: Optional[str] = None
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
        pairs = None
        unresolved = []
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
                aliases=options.bbl_backend == "biblatex")
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
        replace_ids = options.replace_ids and options.cited_keys is None
        if options.replace_ids and not replace_ids:
            messages.append((logging.INFO,
                             "Generate IDs is skipped while filtering by a "
                             ".bbl file, since the keys must stay the cited "
                             "ones"))

        for _idx, _entry in enumerate(entries):
            _entry = modernize_entry(_entry,
                                     remove_fields=options.remove_fields,
                                     replace_ids=replace_ids,
                                     arxiv=options.arxiv, iso4=options.iso4,
                                     clean_fields=options.clean_fields,
                                     arxiv_lookup=options.arxiv_lookup,
                                     arxiv_style=options.arxiv_style,
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
                              both_cited=both_cited)


def _drop(entries, origins, removed):
    kept = [(_entry, _origin) for _entry, _origin in zip(entries, origins)
            if _origin not in removed]
    return [k[0] for k in kept], [k[1] for k in kept]


def run_pipeline(sources, options=None):
    """Run all steps on the sources, a list of `(name, text)` of bib files."""
    if options is None:
        options = PipelineOptions()
    return Pipeline().run(sources, options)

