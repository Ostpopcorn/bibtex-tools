"""Clean the values of fields, e.g., pages and months, and remove fields."""
import re

from ..const import KEY_AUTHOR, KEY_EPRINT, KEY_MONTH, KEY_PAGES
from ..util import Macro, getnames

_MONTHS = {"jan": "1", "january": "1", "1": "1",
           "feb": "2", "february": "2", "2": "2",
           "mar": "3", "march": "3", "3": "3",
           "apr": "4", "april": "4", "4": "4",
           "may": "5", "5": "5",
           "jun": "6", "june": "6", "6": "6",
           "jul": "7", "july": "7", "7": "7",
           "aug": "8", "august": "8", "8": "8",
           "sep": "9", "september": "9", "9": "9",
           "oct": "10", "october": "10", "10": "10",
           "nov": "11", "november": "11", "11": "11",
           "dec": "12", "december": "12", "12": "12"}

#: The months that BibTeX styles define, e.g., as "July" or "Jul."
MONTH_MACROS = ("jan", "feb", "mar", "apr", "may", "jun",
                "jul", "aug", "sep", "oct", "nov", "dec")

def clean_month(month):
    """Write a month as its number, e.g., `jul` as `7`, which biblatex
    reads."""
    return _MONTHS.get(str(month).lower().strip("."), month)

def month_to_macro(month):
    """Write a month as the name that BibTeX styles define, without braces,
    e.g., `{August}`, `{aug}`, or `8` as `aug`. The style prints it in its own
    way, while `{aug}` would be printed as it is."""
    _number = _MONTHS.get(str(month).lower().strip(".").lstrip("0"))
    return Macro(MONTH_MACROS[int(_number) - 1]) if _number else month

def clean_pages(pages):
    """Write a range of pages with `--`, e.g., `17-61` as `17--61`."""
    _split = pages.split("-")
    if "" in _split:
        _split.remove("") # remove empty entries in case '--' was already used
    return "--".join(_split)

def clean_eprint(eprint):
    """Remove the prefix "arXiv:" from an eprint."""
    return re.sub(r"^\s*arxiv\s*:\s*", "", eprint, flags=re.IGNORECASE)

def clean_author(author):
    """Write the names as "Last, First", e.g., `Paul Erdős` as
    `Erdős, Paul`."""
    _names = getnames([i.strip() for i in author.replace('\n', ' ').split(" and ")])
    return " and ".join(_names)

#: Field -> function that cleans its value
FIELD_CLEANERS = {KEY_PAGES: clean_pages,
                  KEY_MONTH: clean_month,
                  KEY_EPRINT: clean_eprint,
                  KEY_AUTHOR: clean_author}
#: The same for BibTeX, which reads the months as names instead of numbers
BIBTEX_FIELD_CLEANERS = dict(FIELD_CLEANERS, **{KEY_MONTH: month_to_macro})

def clean_fields(entry, fields, cleaners=FIELD_CLEANERS):
    """Clean the values of the given fields of an entry with `cleaners`,
    e.g., `fields=("pages", "month")`. Other fields are kept."""
    for _key, _clean in cleaners.items():
        if _key in fields and _key in entry:
            entry[_key] = _clean(entry[_key])
    return entry

def remove_fields(entry, fields):
    """Remove the given fields from an entry, e.g., `fields=("abstract",)`."""
    for _field in fields:
        entry.pop(_field, None)
    return entry
