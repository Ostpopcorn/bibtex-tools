"""The `clean` command, which expands abbreviations, removes fields, and
replaces unicode characters. The steps are in `core`."""
import logging
import copy
import functools
from pprint import pprint

from bibtexparser.bibdatabase import BibDatabase

from .const import KEY_ID
# The steps moved to `core`, and their names are kept here for older code
from .core.duplicates import (IDENTIFIERS, MAX_DUPLICATES,
                              get_duplicate_index_pairs,
                              get_duplicate_index_pairs_of,
                              remove_shorter_duplicate)
from .core.fields import remove_fields as _remove_fields
from .core.keys import get_duplicate_keys, rename_duplicate_keys
from .core.latex import (UNICODE_SKIP_FIELDS, replace_unicode_in_entry,
                         unicode_to_latex)
from .util import load_bib_file, write_bib_database, getnames

def repeat(num_times):
    def decorator_repeat(func):
        @functools.wraps(func)
        def wrapper_repeat(*args, **kwargs):
            for _ in range(num_times):
                value = func(*args, **kwargs)
            return value
        return wrapper_repeat
    return decorator_repeat


def cleaning_function(on_all_entries=False):
    def decorator_cleaning_function(func):
        @functools.wraps(func)
        def wrapper_clean_func(bib_database, *args, **kwargs):
            if isinstance(bib_database, BibDatabase):
                entries = bib_database.get_entry_list()
            else:
                entries = bib_database
            entries = copy.deepcopy(entries)
            if not on_all_entries:
                for entry in entries:
                    entry = func(entry, *args, **kwargs)
            else:
                entries = func(entries, *args, **kwargs)
            return entries
        return wrapper_clean_func
    return decorator_cleaning_function


def has_duplicates(bib_database):
    return len(bib_database.get_entry_dict()) != len(bib_database.get_entry_list())

@cleaning_function(on_all_entries=True)
def get_duplicate_ids(entries):
    return get_duplicate_keys(entries)

@cleaning_function(on_all_entries=True)
def replace_duplicate_ids(entries, return_dupl=False):
    entries, duplicates = rename_duplicate_keys(entries)
    if return_dupl:
        return entries, duplicates
    else:
        return entries

@cleaning_function(on_all_entries=True)
def get_duplicate_entries(entries):
    return [(entries[_idx1], entries[_idx2])
            for _idx1, _idx2 in get_duplicate_index_pairs(entries)]

def ask_which_duplicate_to_remove(entry1, entry2):
    """Resolver for `remove_duplicate_entries` that asks on the command line
    which entry to remove. Returns `None` to keep both entries."""
    logger = logging.getLogger('remove_duplicate_entries')
    logger.warning("Pair of duplicate entries:")
    logger.warning("Entry 1:")
    pprint(entry1)
    logger.warning("Entry 2:")
    pprint(entry2)
    _answer = input("Which entry do you want to REMOVE? Type 1 or 2 and hit enter. Simply hitting enter will remove the shorter entry. Type 0 for not deleting any entry.\n").strip()
    while _answer not in ("", "0", "1", "2"):
        _answer = input("Invalid input. Type 1 or 2 to remove that entry, 0 to keep both, or simply hit enter to remove the shorter entry.\n").strip()
    if _answer == "0":
        return None
    elif _answer:
        return (entry1, entry2)[int(_answer) - 1]
    return remove_shorter_duplicate(entry1, entry2)

@cleaning_function(on_all_entries=True)
def remove_duplicate_entries(entries, interactive=False, verbose=logging.WARN,
                             resolver=None):
    """Remove one entry of each pair of duplicate entries. The `resolver`
    is called with both entries of a pair and returns the one of them to
    remove, or `None` to keep both. By default, the entry with less fields is
    removed, or the user is asked if `interactive` is set. Pairs with an
    already removed entry are skipped."""
    logger = logging.getLogger('remove_duplicate_entries')
    logger.setLevel(verbose)
    automatic = resolver is None and not interactive
    if resolver is None:
        resolver = (ask_which_duplicate_to_remove if interactive
                    else remove_shorter_duplicate)
    duplicates = get_duplicate_index_pairs(entries)
    if duplicates:
        logger.warning("Found %d duplicate pairs", len(duplicates))
        if automatic:
            logger.warning("Removing the entry with less fields of each pair. "
                           "Use --interactive to choose which entry to remove.")
    else:
        logger.info("No duplicate citations found.")
    _removed = set()
    for _idx1, _idx2 in duplicates:
        if _idx1 in _removed or _idx2 in _removed:
            continue
        _entry1, _entry2 = entries[_idx1], entries[_idx2]
        _remove = resolver(_entry1, _entry2)
        if _remove is None:
            continue
        if _remove is _entry2:
            _idx_remove, _keep = _idx2, _entry1
        else:
            _idx_remove, _keep = _idx1, _entry2
        if automatic:
            logger.warning("Removing duplicate entry %s (keeping %s)",
                           entries[_idx_remove][KEY_ID], _keep[KEY_ID])
        _removed.add(_idx_remove)
        logger.info("Successfully removed duplicate entry.")
    return [_entry for _idx, _entry in enumerate(entries)
            if _idx not in _removed]

def remove_fields_from_entry(entry, remove_fields=None):
    if remove_fields is None:
        return entry
    return _remove_fields(entry, remove_fields)

remove_fields_from_database = cleaning_function()(remove_fields_from_entry)

replace_unicode_in_database = cleaning_function()(replace_unicode_in_entry)

def clean_bib_file_main(bib_file, abbr_file=None, remove_fields=None,
                        encoding="utf-8", remove_duplicates=False,
                        interactive=False, verbose=logging.WARN,
                        replace_unicode=False):
    logging.basicConfig(format="%(asctime)s - [%(levelname)8s]: %(message)s")
    logger = logging.getLogger('clean_bib_file')
    logger.setLevel(verbose)
    logger.info("Cleaning bib file: %s", bib_file)
    if abbr_file is not None:
        logger.info("Using the following abbreviation file: %s", abbr_file)
    bib_database = load_bib_file(bib_file, abbr=abbr_file, encoding=encoding)
    logger.debug("Loaded file and replaced abbreviation strings")
    if remove_duplicates or interactive:
        bib_database = remove_duplicate_entries(bib_database,
                                                interactive=interactive,
                                                verbose=verbose)
        logger.debug("Successfully removed duplicates")
    clean_entries, duplicates = replace_duplicate_ids(bib_database,
                                                      return_dupl=True)
    if duplicates:
        logger.warning("Renamed entries with duplicate IDs (the first entry "
                       "keeps its ID): %s", ", ".join(duplicates))
    if remove_fields is not None:
        logger.info("Removing fields: %s", remove_fields)
        clean_entries = remove_fields_from_database(clean_entries, remove_fields)
    if replace_unicode:
        logger.info("Converting unicode characters")
        clean_entries = replace_unicode_in_database(clean_entries)
    return clean_entries
