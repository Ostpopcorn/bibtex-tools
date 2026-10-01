"""The `filter-cited` command, which keeps the entries that a .bbl file
cites. The steps are in `core.cited`."""
import logging

from .clean_bib_file import (ask_which_duplicate_to_remove,
                             get_duplicate_index_pairs_of,
                             remove_shorter_duplicate)
from .const import KEY_ID
# The steps moved to `core`, and their names are kept here for older code
from .core.cited import (CitedEntries, add_referenced_ids,
                         filter_cited_entries, get_bibitem_keys,
                         get_referenced_ids, parse_bbl_keys,
                         resolve_cited_duplicates)
from .util import load_bib_file


def get_bbl_keys(bbl_file, encoding="utf-8"):
    """Extract citation keys from a .bbl file, auto-detecting the backend."""
    with open(bbl_file, encoding=encoding) as _bbl_file:
        return parse_bbl_keys(_bbl_file.read())


def filter_cited_main(bib_file, bbl_file, remove_duplicates=False,
                      interactive=False, verbose=logging.WARN,
                      encoding="utf-8"):
    """Keep the entries of one or more bib files (`bib_file` can be a list)
    that are cited in a .bbl file. With `remove_duplicates` or
    `interactive`, duplicates of the cited entries are removed as well, and
    the kept entry of a pair takes over the cited key of the removed one."""
    logging.basicConfig(format="%(asctime)s - [%(levelname)8s]: %(message)s")
    logger = logging.getLogger("filter_cited")
    logger.setLevel(verbose)
    bib_files = [bib_file] if isinstance(bib_file, str) else list(bib_file)
    logger.info("Filtering entries of %s using citations from %s",
                ", ".join(bib_files), bbl_file)
    entries = []
    for _bib_file in bib_files:
        entries.extend(load_bib_file(_bib_file, abbr=None,
                                     encoding=encoding).get_entry_list())
    cited_keys, backend = get_bbl_keys(bbl_file, encoding=encoding)
    logger.info("Detected bbl backend: %s", backend)
    logger.info("Found %d cited keys in bbl file", len(cited_keys))

    pairs = []
    needed = add_referenced_ids(cited_keys, entries)
    if remove_duplicates or interactive:
        pairs, warnings = get_duplicate_index_pairs_of(
            entries, [_idx for _idx, _entry in enumerate(entries)
                      if _entry[KEY_ID] in needed])
        for _level, _warning in warnings:
            logger.log(_level, _warning)
        if pairs:
            logger.warning("Found %d pairs of duplicates of cited entries",
                           len(pairs))
    resolver = (ask_which_duplicate_to_remove if interactive
                else remove_shorter_duplicate)

    def resolve(idx1, idx2):
        entry1, entry2 = entries[idx1], entries[idx2]
        if interactive:
            cited = [str(_num) for _num, _entry in ((1, entry1), (2, entry2))
                     if _entry[KEY_ID] in needed]
            logger.warning("The .bbl file cites entry %s. If you remove a "
                           "cited entry, the other one takes over its key.",
                           " and ".join(cited))
        remove = resolver(entry1, entry2)
        if remove is None:
            return None
        return idx1 if remove is entry1 else idx2

    result = resolve_cited_duplicates(entries, cited_keys, pairs, resolve,
                                      aliases=backend == "biblatex")
    # The users should see when a key moves to another entry
    for _level, _note in result.notes:
        logger.log(max(_level, logging.WARNING), _note)
    kept = [result.kept[_idx] for _idx in sorted(result.kept)]
    keep_ids = set(entry[KEY_ID] for entry in kept)
    referenced = keep_ids - cited_keys
    unused = set(entries[_idx][KEY_ID] for _idx, _reason in result.removed.items()
                 if _reason == "not cited")
    missing = cited_keys - set(entry[KEY_ID] for entry in entries)
    logger.info("Keeping %d of %d entries", len(kept), len(entries))
    if referenced:
        logger.info("Keeping %d entries that cited entries refer to, e.g., "
                    "with crossref: %s", len(referenced),
                    ", ".join(sorted(referenced)))
    if unused:
        logger.info("Dropping %d uncited entries: %s",
                    len(unused), ", ".join(sorted(unused)))
    if missing:
        logger.warning("%d cited keys are not present in the bib file: %s",
                       len(missing), ", ".join(sorted(missing)))
    return kept
