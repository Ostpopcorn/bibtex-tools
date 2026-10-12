"""Abbreviations of conferences in parentheses at the end of their names,
e.g., `Advances in Neural Information Processing Systems (NeurIPS)`."""
import re

from ..const import KEY_BOOKTITLE, KEY_ENTRYTYPE

KEY_EVENTTITLE = "eventtitle"
#: The fields with the name of a conference
VENUE_FIELDS = (KEY_BOOKTITLE, KEY_EVENTTITLE)
#: The entry types that are conference papers or proceedings
CONFERENCE_TYPES = ("inproceedings", "conference", "proceedings")

#: Keep the abbreviations of conferences
CONF_ABBR_KEEP = "keep"
#: Remove the abbreviations of conferences, e.g., `(NeurIPS)`
CONF_ABBR_REMOVE = "remove"
CONF_ABBR_MODES = (CONF_ABBR_KEEP, CONF_ABBR_REMOVE)

# An abbreviation in parentheses at the end of a name, also in braces and
# with a year, e.g., `(NeurIPS)`, `({ICASSP})`, `(ICC 2020)`, and
# `(CVPR'20)`. Braces after it are kept, e.g., of `{Name (ICC)}`.
_RE_ABBR = re.compile(r"\s*\(\s*\{?(?P<abbr>[A-Za-z][\w&/.+-]*)\}?"
                      r"(?:\s*['’-]?\s*(?:\d{4}|\d{2}))?\s*\)"
                      r"(?P<end>\s*\}*)\s*$")


def split_conference_abbr(name):
    """Split the abbreviation off the name of a conference, e.g., `Advances
    in Neural Information Processing Systems (NeurIPS)` into the name
    without it and `NeurIPS`. An abbreviation has at least two capitals, so
    that, e.g., `(Workshops)` and `(Part 1)` are kept. Returns the name and
    None if there is no abbreviation."""
    _match = _RE_ABBR.search(name)
    if not _match or sum(_c.isupper() for _c in _match["abbr"]) < 2:
        return name, None
    return name[:_match.start()] + _match["end"].strip(), _match["abbr"]

def is_conference(entry):
    """Whether an entry is a conference paper or proceedings."""
    return entry.get(KEY_ENTRYTYPE, "").lower() in CONFERENCE_TYPES

def remove_conference_abbr(entry):
    """Remove the abbreviations of the conference of a conference paper or
    proceedings, e.g., `(NeurIPS)`, from `booktitle` and `eventtitle`."""
    if is_conference(entry):
        for _field in VENUE_FIELDS:
            if _field in entry:
                entry[_field] = split_conference_abbr(entry[_field])[0]
    return entry

def conference_venue(entry):
    """The name of the conference of a conference paper or proceedings and
    its abbreviation: from the first field of `VENUE_FIELDS` with an
    abbreviation, or else from the first field with a name. None if the
    entry has no name of a conference."""
    if not is_conference(entry):
        return None
    _venues = [(entry[_field], split_conference_abbr(entry[_field])[1])
               for _field in VENUE_FIELDS if entry.get(_field, "").strip()]
    if not _venues:
        return None
    return next((_venue for _venue in _venues if _venue[1]), _venues[0])

def sort_by_conference_abbr(entries):
    """Sort the conference papers and proceedings into those whose
    conference has an abbreviation and those without, as two lists of
    (index of the entry, name of the conference, abbreviation or None)."""
    with_abbr, without_abbr = [], []
    for _idx, _entry in enumerate(entries):
        _venue = conference_venue(_entry)
        if _venue is not None:
            (with_abbr if _venue[1] else without_abbr).append((_idx,) + _venue)
    return with_abbr, without_abbr
