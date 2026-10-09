"""Replace unicode characters with LaTeX, e.g., `é` with `{\\'e}`."""
import re

from bibtexparser.latexenc import unicode_to_latex_map

from ..const import (KEY_DOI, KEY_ENTRYTYPE, KEY_EPRINT, KEY_ID, KEY_IDS,
                     KEY_URL)
from ..util import Macro

#: Fields that are keys or are read verbatim, where LaTeX would break them
UNICODE_SKIP_FIELDS = (KEY_ID, KEY_ENTRYTYPE, KEY_IDS, KEY_URL, KEY_DOI,
                       KEY_EPRINT, "file", "pdf", "urlraw")

_RE_MATH = re.compile(r"(\$[^$]*\$)")
_RE_BARE_SPECIAL = re.compile(r"(?<!\\)([&%#])")

def unicode_to_latex(text):
    """Convert the non-ASCII characters of a text to LaTeX, e.g., `é` to
    `{\\'e}`, and escape a bare `&`, `%`, or `#` outside of math. Existing
    LaTeX and braces, e.g., `{IEEE}` or `{\\"o}`, are kept."""
    parts = _RE_MATH.split(text)
    for _idx, _part in enumerate(parts):
        _part = "".join(unicode_to_latex_map.get(c, c) if ord(c) > 127 else c
                        for c in _part)
        if _idx % 2 == 0:
            _part = _RE_BARE_SPECIAL.sub(r"\\\1", _part)
        parts[_idx] = _part
    return "".join(parts)

def replace_unicode_in_entry(entry):
    """Convert the unicode characters of all fields of an entry to LaTeX,
    except the fields in `UNICODE_SKIP_FIELDS` and the names of strings,
    e.g., the month `nov`."""
    for _field in entry:
        if (_field not in UNICODE_SKIP_FIELDS
                and not isinstance(entry[_field], Macro)):
            entry[_field] = unicode_to_latex(entry[_field])
    return entry
