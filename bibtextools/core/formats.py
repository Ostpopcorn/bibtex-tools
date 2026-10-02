"""Convert entries between the fields and entry types of BibTeX and
biblatex, e.g., `journal` and `journaltitle`. biber reads the BibTeX names as
well, but BibTeX does not read the biblatex names."""
import re

from ..const import KEY_DATE, KEY_ENTRYTYPE, KEY_MONTH, KEY_YEAR

#: BibTeX field -> biblatex field
BIBTEX_TO_BIBLATEX_FIELDS = {"journal": "journaltitle",
                             "address": "location",
                             "school": "institution",
                             "annote": "annotation",
                             "archiveprefix": "eprinttype",
                             "primaryclass": "eprintclass"}
#: biblatex field -> BibTeX field. `institution` is only `school` for theses.
BIBLATEX_TO_BIBTEX_FIELDS = {v: k for k, v in BIBTEX_TO_BIBLATEX_FIELDS.items()
                             if v != "institution"}

#: BibTeX entry type -> biblatex entry type and its `type` field
BIBTEX_TO_BIBLATEX_TYPES = {"conference": ("inproceedings", None),
                            "electronic": ("online", None),
                            "www": ("online", None),
                            "phdthesis": ("thesis", "phdthesis"),
                            "mastersthesis": ("thesis", "mathesis"),
                            "techreport": ("report", "techreport")}
#: biblatex entry type -> BibTeX entry type, for the types that BibTeX does
#: not have. Theses and reports also depend on their `type` field.
BIBLATEX_TO_BIBTEX_TYPES = {"online": "misc",
                            "electronic": "misc",
                            "www": "misc",
                            "dataset": "misc",
                            "software": "misc",
                            "collection": "book",
                            "mvbook": "book",
                            "mvcollection": "book",
                            "reference": "book",
                            "inreference": "incollection",
                            "report": "techreport"}
_THESIS_TYPES = {"phdthesis": "phdthesis", "mathesis": "mastersthesis"}

_MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November",
                "December"]
_RE_DATE = re.compile(r"\s*(\d{4})(?:-(\d{1,2}))?(?:-\d{1,2})?\s*")

KEY_TYPE = "type"
KEY_INSTITUTION = "institution"
KEY_SCHOOL = "school"


def _rename_fields(entry, names):
    """Rename the fields of an entry, unless the new name is already used."""
    for _old, _new in names.items():
        if _old in entry and _new not in entry:
            entry[_new] = entry.pop(_old)
    return entry

def to_biblatex(entry):
    """Use the fields and entry types of biblatex, e.g., `journaltitle`
    instead of `journal`, and `@thesis` with `type = {phdthesis}` instead of
    `@phdthesis`."""
    entry_type = entry[KEY_ENTRYTYPE].lower()
    if entry_type in BIBTEX_TO_BIBLATEX_TYPES:
        entry[KEY_ENTRYTYPE], _type = BIBTEX_TO_BIBLATEX_TYPES[entry_type]
        if _type is not None and KEY_TYPE not in entry:
            entry[KEY_TYPE] = _type
    return _rename_fields(entry, BIBTEX_TO_BIBLATEX_FIELDS)

def to_bibtex(entry):
    """Use the fields and entry types of BibTeX, e.g., `journal` instead of
    `journaltitle`, `@misc` instead of `@online`, and `year` and `month`
    instead of `date`."""
    entry_type = entry[KEY_ENTRYTYPE].lower()
    if entry_type == "thesis":
        _type = entry.get(KEY_TYPE, "").strip().lower()
        entry[KEY_ENTRYTYPE] = _THESIS_TYPES.get(_type, "phdthesis")
        if _type in _THESIS_TYPES:
            del entry[KEY_TYPE]
    elif entry_type in BIBLATEX_TO_BIBTEX_TYPES:
        entry[KEY_ENTRYTYPE] = BIBLATEX_TO_BIBTEX_TYPES[entry_type]
        if (entry_type == "report"
                and entry.get(KEY_TYPE, "").strip().lower() == "techreport"):
            del entry[KEY_TYPE]
    if entry[KEY_ENTRYTYPE] in ("phdthesis", "mastersthesis"):
        _rename_fields(entry, {KEY_INSTITUTION: KEY_SCHOOL})
    _match = _RE_DATE.fullmatch(entry.get(KEY_DATE, ""))
    if _match:
        year, month = _match.groups()
        entry.setdefault(KEY_YEAR, year)
        if month and 1 <= int(month) <= 12 and KEY_MONTH not in entry:
            entry[KEY_MONTH] = _MONTH_NAMES[int(month) - 1]
        if entry[KEY_YEAR] == year:
            del entry[KEY_DATE]
    return _rename_fields(entry, BIBLATEX_TO_BIBTEX_FIELDS)
