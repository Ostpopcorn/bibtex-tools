"""Abbreviate the names of journals and conferences with ISO 4."""
import functools
import logging

from pyiso4 import ltwa
from pyiso4.ltwa import Abbreviate

from ..const import KEY_BOOKTITLE, KEY_ENTRYTYPE, KEYS_JOURNAL
from .arxiv import match_arxiv_venue


def _open_utf8(file, mode="r", *args, **kwargs):
    if "b" not in mode:
        kwargs.setdefault("encoding", "utf-8")
    return open(file, mode, *args, **kwargs)

@functools.lru_cache(maxsize=None)
def get_abbreviator():
    """Load the ISO4 abbreviation list (LTWA) once, since this takes about a
    second. pyiso4 opens its UTF-8 data files with the default encoding,
    which fails on Windows (cp1252), so its open() is made to use UTF-8."""
    ltwa.open = _open_utf8
    try:
        return Abbreviate.create()
    finally:
        del ltwa.open

def abbreviate_name(name):
    """Abbreviate a journal or conference name according to ISO4. Names that
    pyiso4 fails on are kept, e.g., "Transactions on Different Work"."""
    try:
        return get_abbreviator()(name)
    except Exception:
        logging.getLogger('modernize_bib_file').warning(
            "Could not abbreviate %r, so it is kept", name)
        return name

def abbreviate_journalname(entry):
    """Return a copy of the entry with its journal, or the conference of
    @inproceedings, abbreviated. arXiv as the journal is kept."""
    entry = entry.copy()
    if entry[KEY_ENTRYTYPE] == "inproceedings":
        conf = entry.get(KEY_BOOKTITLE, False)
        if conf:
            entry[KEY_BOOKTITLE] = abbreviate_name(conf)
    for _key in KEYS_JOURNAL:
        journal = entry.get(_key, False)
        if not journal or match_arxiv_venue(journal):
            continue
        entry[_key] = abbreviate_name(journal)
    return entry
