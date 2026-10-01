"""Protect titles with braces, so that bibliography styles keep their case,
e.g., `{IEEE}` instead of "Ieee"."""
import re

from ..const import KEY_TITLE

#: Keep the titles as they are
TITLE_KEEP = "keep"
#: Put braces around acronyms, e.g., `The {IEEE} Standard`
TITLE_ACRONYMS = "acronyms"
#: Put braces around the whole title, e.g., `{The IEEE Standard}`
TITLE_WHOLE = "whole"
TITLE_MODES = (TITLE_KEEP, TITLE_ACRONYMS, TITLE_WHOLE)

_RE_ACRONYM = re.compile(r'([0-9A-Z]+\b)|([a-zA-Z]+[A-Z0-9]+[a-zA-Z\b]*)|(\$[\w\\+-=]*\$)')
_RE_DOUBLE = re.compile(r'\{{2}((?:\{??[^\{]*?))\}{2}')
_RE_INNER = re.compile(r'\{((?:\{??[^\{]*?))\}')

def _surrounded_by_curly(title):
    return title.startswith(r"{") and title.endswith(r"}")

def is_wrapped(title):
    """Whether one pair of braces encloses the whole title, e.g.,
    `{A Title}`, but not `{A} and {B}`."""
    if not _surrounded_by_curly(title):
        return False
    depth = 0
    for _idx, _char in enumerate(title):
        if _idx > 0 and title[_idx-1] == "\\":
            continue
        depth += {"{": 1, "}": -1}.get(_char, 0)
        if depth == 0:
            return _idx == len(title) - 1
    return False

def protect_acronyms(title):
    """Put braces around the acronyms of a title, e.g., `IEEE`, `5G`, and
    `mmWave`, and around math. Braces around the whole title are removed."""
    _shielded = _RE_ACRONYM.sub(r'{\g<0>}', title)
    _shielded = _RE_DOUBLE.sub(r'{\g<1>}', _shielded)
    _without_inner = _RE_INNER.sub(r"\g<1>", _shielded)
    _remove_curly_w_acros = _surrounded_by_curly(_without_inner)
    _remove_curly_wo_acros = ((len(_RE_INNER.findall(_shielded)) == 1)
                              and _surrounded_by_curly(title))
    if _remove_curly_w_acros or _remove_curly_wo_acros:
        _shielded = _shielded[1:-1]
    return _shielded

def protect_title(title, mode):
    """Protect a title in a mode of `TITLE_MODES`. Braces inside the title,
    e.g., around an acronym or of `{\\"a}`, are kept."""
    if mode not in TITLE_MODES:
        raise ValueError("Unknown way to protect titles: {}".format(mode))
    if mode == TITLE_ACRONYMS:
        return protect_acronyms(title)
    if mode == TITLE_WHOLE and title.strip() and not is_wrapped(title):
        return "{" + title + "}"
    return title

def protect_title_in_entry(entry, mode):
    """Protect the title of an entry in a mode of `TITLE_MODES`."""
    if KEY_TITLE in entry:
        entry[KEY_TITLE] = protect_title(entry[KEY_TITLE], mode)
    return entry
