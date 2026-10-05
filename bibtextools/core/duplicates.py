"""Find duplicate entries, i.e., the same work stored more than once."""
import itertools
import logging
import re
from difflib import SequenceMatcher

from ..const import (KEY_AUTHOR, KEY_BOOKTITLE, KEY_DATE, KEY_DOI, KEY_EDITOR,
                     KEY_ENTRYTYPE, KEY_EPRINT, KEY_ID, KEY_ISBN, KEY_PAGES,
                     KEY_TITLE, KEY_YEAR, KEYS_JOURNAL)
from ..util import getnames


def _normalize_doi(doi):
    doi = doi.strip().lower().replace("\\", "")
    return re.sub(r'^(https?://(dx\.)?doi\.org/|doi:)', '', doi)

def _normalize_eprint(eprint):
    eprint = re.sub(r'^arxiv:', '', eprint.strip().lower())
    return re.sub(r'v\d+$', '', eprint)

def _normalize_isbn(isbn):
    return re.sub(r'[^0-9x]', '', isbn.lower())

IDENTIFIERS = {KEY_DOI: _normalize_doi,
               KEY_EPRINT: _normalize_eprint,
               KEY_ISBN: _normalize_isbn}

def _have_different_identifiers(entry1, entry2):
    """Entries with different DOIs, arXiv IDs, or ISBNs are different works,
    no matter how similar their titles and authors are."""
    for _key, _normalize in IDENTIFIERS.items():
        if _key in entry1 and _key in entry2:
            if _normalize(entry1[_key]) != _normalize(entry2[_key]):
                return True
    return False

def _get_year(entry):
    return entry.get(KEY_YEAR, entry.get(KEY_DATE, "")[:4])

def _index_pairs(count, among=None):
    """The index pairs `(i, j)` with `i < j` of `count` entries, only the
    pairs with an index in `among` if it is given."""
    if among is None:
        return itertools.combinations(range(count), 2)
    among = set(among)
    return sorted(set((min(_idx1, _idx2), max(_idx1, _idx2))
                      for _idx1 in among for _idx2 in range(count)
                      if _idx2 != _idx1))

#: Types of papers that are often stored as each other, e.g., a conference
#: paper as @article with the proceedings as journal, like Google Scholar
#: exports it
_PAPER_TYPES = ("article", "inproceedings", "conference")

def _venue(entry):
    """The journal or the proceedings of a paper."""
    for _key in (*KEYS_JOURNAL, KEY_BOOKTITLE):
        if entry.get(_key):
            return entry[_key]
    return ""

def _same_pages(entry1, entry2):
    """Whether the pages are similar, or not in both entries."""
    if KEY_PAGES not in entry1 or KEY_PAGES not in entry2:
        return True
    return SequenceMatcher(None, entry1[KEY_PAGES], entry2[KEY_PAGES]).ratio() >= .75

def _same_paper(entry1, entry2):
    """Whether papers of different types, e.g., @article and @inproceedings,
    are in the same venue in the same year, e.g., "Proceedings of Machine
    Learning and Systems" as journal and as booktitle."""
    if _get_year(entry1) != _get_year(entry2):
        return False
    venue_ratio = SequenceMatcher(None, _venue(entry1).lower(),
                                  _venue(entry2).lower()).ratio()
    return venue_ratio > .7 and _same_pages(entry1, entry2)

def get_duplicate_index_pairs(entries, among=None):
    """Return the index pairs `(i, j)` with `i < j` of all entries that are
    duplicates, i.e., the same work stored more than once. Entries of
    different types are only compared if both are papers, e.g., @article and
    @inproceedings. Whether two entries are duplicates does not depend on the
    other entries. With
    `among`, e.g., the indices of the cited entries, only the pairs with one
    of these entries are searched, which is much faster."""
    seq_matcher_title = SequenceMatcher()
    seq_matcher_authors = SequenceMatcher()
    duplicates = []
    for _idx1, _idx2 in _index_pairs(len(entries), among):
        _entry1, _entry2 = entries[_idx1], entries[_idx2]
        _type1 = _entry1[KEY_ENTRYTYPE].lower()
        _type2 = _entry2[KEY_ENTRYTYPE].lower()
        if _type1 != _type2 and not (_type1 in _PAPER_TYPES
                                     and _type2 in _PAPER_TYPES):
            continue
        _names1 = _entry1.get(KEY_AUTHOR, _entry1.get(KEY_EDITOR))
        _names2 = _entry2.get(KEY_AUTHOR, _entry2.get(KEY_EDITOR))
        if not (_entry1.get(KEY_TITLE) and _entry2.get(KEY_TITLE)
                and _names1 and _names2):
            continue
        if _have_different_identifiers(_entry1, _entry2):
            continue
        seq_matcher_title.set_seqs(_entry2[KEY_TITLE], _entry1[KEY_TITLE])
        # The quick ratios are upper bounds of the ratio, which is slow
        if (seq_matcher_title.real_quick_ratio() < .8
                or seq_matcher_title.quick_ratio() < .8):
            continue
        _title_ratio = seq_matcher_title.ratio()
        if _title_ratio < .8:
            continue
        #print('---')
        #print(f"T1: {_entry1[KEY_TITLE]}\nT2: {_entry2[KEY_TITLE]}")
        #print(f"Ratio: {_title_ratio}")
        _authors1 = getnames([i.strip() for i in _names1.replace('\n', ' ').split(" and ")])
        _authors1 = " and ".join(_authors1)
        _authors2 = getnames([i.strip() for i in _names2.replace('\n', ' ').split(" and ")])
        _authors2 = " and ".join(_authors2)
        seq_matcher_authors.set_seqs(_authors2, _authors1)
        _author_ratio = seq_matcher_authors.ratio()
        if _author_ratio < .9:
            continue
        _same_misc = True
        if _type1 != _type2:
            _same_misc = _same_paper(_entry1, _entry2)
        elif _entry1[KEY_ENTRYTYPE] == "inproceedings":
            _same_misc = _same_misc and (_get_year(_entry1) == _get_year(_entry2))
            _same_misc = _same_misc and (SequenceMatcher(None, _entry1.get(KEY_BOOKTITLE, ""), _entry2.get(KEY_BOOKTITLE, "")).ratio() > .7)
        elif _entry1[KEY_ENTRYTYPE] == "article":
            for _key in KEYS_JOURNAL:
                _journal1 = _entry1.get(_key, "")
                if _journal1: break
            for _key in KEYS_JOURNAL:
                _journal2 = _entry2.get(_key, "")
                if _journal2: break
            _same_misc = SequenceMatcher(None, _journal1, _journal2).ratio() > .7
            if KEY_PAGES in _entry1 and KEY_PAGES in _entry2:
                _same_misc = _same_misc and (SequenceMatcher(None, _entry1[KEY_PAGES], _entry2[KEY_PAGES]).ratio() >= .75)
        else:
            # e.g., two editions of a book or two versions of a software
            _same_misc = _get_year(_entry1) == _get_year(_entry2)
        if not _same_misc:
            continue
        duplicates.append((_idx1, _idx2))
    return duplicates

#: Groups of duplicates, i.e., copies of the same work, with more entries are
#: not searched further, since their pairs grow quickly
MAX_DUPLICATES = 5

def get_duplicate_index_pairs_of(entries, among, max_duplicates=MAX_DUPLICATES):
    """Return the index pairs of the duplicates of the entries with the
    indices `among`, e.g., the cited ones, and of their duplicates in turn,
    so that all copies of the same work are compared with each other.
    Groups of copies with more than `max_duplicates` entries are not searched
    further, and a warning lists them. Returns the sorted pairs and the
    warnings as `(logging level, message)`."""
    parent = {}
    def root(idx):
        while parent.setdefault(idx, idx) != idx:
            idx = parent[idx]
        return idx

    pairs = set()
    searched = set()
    search = set(among)
    while search:
        searched |= search
        found = get_duplicate_index_pairs(entries, among=search)
        pairs.update(found)
        for _idx1, _idx2 in found:
            parent[root(_idx1)] = root(_idx2)
        sizes = {}
        for _idx in parent:
            sizes[root(_idx)] = sizes.get(root(_idx), 0) + 1
        search = set(_idx for _pair in found for _idx in _pair
                     if _idx not in searched
                     and sizes[root(_idx)] <= max_duplicates)

    groups = {}
    for _idx in parent:
        groups.setdefault(root(_idx), []).append(_idx)
    too_large = [sorted(_group) for _group in groups.values()
                 if len(_group) > max_duplicates]
    warnings = [(logging.WARNING,
                 "{} entries seem to be the same work: {}. Since that is more "
                 "than {}, not all of their pairs are compared. Remove some "
                 "copies from the bib files to compare all of them.".format(
                     len(_group), ", ".join(entries[_idx][KEY_ID]
                                            for _idx in _group),
                     max_duplicates))
                for _group in sorted(too_large)]
    return sorted(pairs), warnings

def remove_shorter_duplicate(entry1, entry2):
    """Resolver for `remove_duplicate_entries` that removes the entry with
    less fields."""
    return sorted((entry1, entry2), key=len)[0]
