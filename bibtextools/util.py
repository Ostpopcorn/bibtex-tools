import logging
import re
from collections import Counter

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.bibdatabase import BibDatabase

from .const import KEY_ID

def parse_abbr_string(abbr_str):
    """Return the abbreviations (`@string`) of the content of a bib file."""
    parser = BibTexParser(homogenize_fields=True, common_strings=True)
    abbr_database = bibtexparser.loads(abbr_str, parser=parser)
    return abbr_database.strings

def load_abbr(abbr_file, encoding="utf-8"):
    with open(abbr_file, encoding=encoding) as _abbr_file:
        return parse_abbr_string(_abbr_file.read())

def strip_comments(bib_str):
    """Remove `%` comments between the fields of an entry, e.g., a commented
    out field, which make bibtexparser silently skip the entry. Commented
    lines between entries are removed as well. Field values are not changed.
    """
    stripped = []
    depth = 0
    in_quotes = False
    idx = 0
    while idx < len(bib_str):
        char = bib_str[idx]
        if char == "%" and not in_quotes and bib_str[idx-1] != "\\":
            _line_start = bib_str.rfind("\n", 0, idx) + 1
            if depth == 1 or (depth == 0 and
                              not bib_str[_line_start:idx].strip()):
                idx = bib_str.find("\n", idx)
                if idx < 0:
                    break
                continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(depth-1, 0)
            if depth == 0:
                in_quotes = False
        elif char == '"' and depth == 1:
            in_quotes = not in_quotes
        stripped.append(char)
        idx += 1
    return "".join(stripped)

_RE_ENTRY_HEAD = re.compile(r'^[ \t]*@[ \t]*(\w+)[ \t]*(?P<open>[{(])\s*(?P<id>[^\s,{}]+)\s*,',
                            re.MULTILINE)
_RE_COMMENT_HEAD = re.compile(r'^[ \t]*@[ \t]*comment[ \t]*\{',
                              re.MULTILINE | re.IGNORECASE)

_RE_BRACE = re.compile(r'[{}]')

def _find_closing_brace(bib_str, idx):
    """Return the index after the brace that closes the one before `idx`."""
    depth = 1
    for _match in _RE_BRACE.finditer(bib_str, idx):
        depth += 1 if _match.group() == "{" else -1
        if depth == 0:
            return _match.end()
    return len(bib_str)

def get_entry_spans(bib_str):
    """Return the ID, start, and end index of all entries that start on a
    new line in a bib string. Unlike a full parser, this does not depend on
    the content of the entries being valid."""
    comment_spans = [(_match.start(), _find_closing_brace(bib_str, _match.end()))
                     for _match in _RE_COMMENT_HEAD.finditer(bib_str)]
    heads = []
    for _match in _RE_ENTRY_HEAD.finditer(bib_str):
        if _match.group(1).lower() in ("comment", "preamble", "string"):
            continue
        if any(_start < _match.start() < _end
               for _start, _end in comment_spans):
            continue
        heads.append(_match)
    spans = []
    for _idx, _match in enumerate(heads):
        _next = heads[_idx+1].start() if _idx+1 < len(heads) else len(bib_str)
        _end = len(bib_str[:_next].rstrip())
        if _match.group("open") == "{":
            _end = min(_find_closing_brace(bib_str, _match.end("open")), _end)
        spans.append((_match.group("id"), _match.start(), _end))
    return spans

def get_entry_ids(bib_str):
    """Return the IDs of all entries that start on a new line in a bib
    string. Unlike a full parser, this does not depend on the content of the
    entries being valid."""
    return [_id for _id, _start, _end in get_entry_spans(bib_str)]

def _read_abbr(abbr, encoding="utf-8"):
    if abbr is None or isinstance(abbr, dict):
        return abbr
    return load_abbr(abbr, encoding=encoding)

def parse_bib_string(bib_str, abbr=None, source="<string>",
                     return_skipped=False):
    """Parse the content of a bib file. The abbreviations `abbr`, e.g., from
    `load_abbr`, are expanded in addition to the common strings, without
    changing the strings of later calls. Entries that cannot be read are
    listed in a warning, and returned if `return_skipped` is set."""
    logger = logging.getLogger('load_bib_file')
    bib_str = strip_comments(bib_str)
    parser = BibTexParser(homogenize_fields=True, common_strings=True,
                          ignore_nonstandard_types=False)
    parser.alt_dict.pop("keywords")
    if abbr is not None:
        parser.bib_database.strings.update(abbr)
    bib_database = bibtexparser.loads(bib_str, parser=parser)
    skipped = (Counter(get_entry_ids(bib_str))
               - Counter([x[KEY_ID] for x in bib_database.entries]))
    if skipped:
        logger.warning("Could not read %d entries from %s. They are NOT "
                       "included in the result. Check them for syntax "
                       "errors, e.g., a missing comma between fields: %s",
                       sum(skipped.values()), source,
                       ", ".join(skipped.elements()))
    if return_skipped:
        return bib_database, list(skipped.elements())
    return bib_database

def load_bib_file(bib_file, abbr=None, encoding="utf-8"):
    abbr = _read_abbr(abbr, encoding=encoding)
    with open(bib_file, encoding=encoding) as _bib_file:
        bib_str = _bib_file.read()
    return parse_bib_string(bib_str, abbr=abbr, source=bib_file)


def get_bib_writer(order_entries_by=(KEY_ID,)):
    writer = BibTexWriter()
    writer.order_entries_by = order_entries_by
    writer.add_trailing_comma = True
    writer.indent = "\t"  # "  "
    return writer

def format_bib_entries(entries, order_entries_by=(KEY_ID,)):
    """Return the content of a bib file with the given entries."""
    clean_database = BibDatabase()
    clean_database.entries = entries
    return get_bib_writer(order_entries_by).write(clean_database)

def write_bib_database(entries, out_file, encoding="utf-8",
                       order_entries_by=(KEY_ID,)):
    with open(out_file, 'w', encoding=encoding) as _out_file:
        _out_file.write(format_bib_entries(entries, order_entries_by))

def getnames(names):
    """This function is a slight modification of the function from bibtexparser
    `bibtexparser.customization.getnames`.
    """
    tidynames = []
    for namestring in names:
        namestring = namestring.strip()
        if len(namestring) < 1:
            continue
        if ',' in namestring:
            namesplit = namestring.split(',', 1)
            last = namesplit[0].strip()
            firsts = [i.strip() for i in namesplit[1].split()]
        elif namestring[0] == "{" and namestring[-1] == "}":
            tidynames.append(namestring)
            continue
        else:
            #shielded_names = re.findall(r'[{].*?[}]', namestring)
            shielded_names = re.findall(r'(\s|^)([{].*?[}])', namestring)
            if shielded_names:
                last = shielded_names.pop()
                last = last[1]
                if namestring.endswith(last):
                    firsts = namestring[:-len(last)].split()
                else:
                    firsts = [last]
                    last = namestring[len(last):] #removeprefix in Python 3.9+
            else:
                namesplit = namestring.split()
                last = namesplit.pop()
                firsts = [i.replace('.', '. ').strip() for i in namesplit]
        if last in ['jnr', 'jr', 'junior']:
            last = firsts.pop()
        for item in firsts:
            if item in ['ben', 'van', 'der', 'de', 'la', 'le']:
                last = firsts.pop() + ' ' + last
        if not firsts:
            tidynames.append(last)
        else:
            tidynames.append(last + ", " + ' '.join(firsts))
    return tidynames
