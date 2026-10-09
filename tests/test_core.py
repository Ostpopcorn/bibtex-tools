import pytest

from bibtextools.core.duplicates import get_duplicate_index_pairs
from bibtextools.core.fields import (BIBTEX_FIELD_CLEANERS, clean_fields,
                                     month_to_macro, remove_fields)
from bibtextools.core.formats import to_biblatex, to_bibtex
from bibtextools.core.keys import generate_key, rename_duplicate_keys
from bibtextools.core.titles import (TITLE_ACRONYMS, TITLE_KEEP, TITLE_WHOLE,
                                     is_wrapped, protect_title,
                                     protect_title_in_entry)
from bibtextools.util import Macro, format_bib_entries, read_bib_string


@pytest.mark.parametrize("title,keep,acronyms,whole", [
    ("The IEEE Standard", "The IEEE Standard", "The {IEEE} Standard",
     "{The IEEE Standard}"),
    # no braces in braces, which the old whole-title mode added
    ("A Mathematical Theory", "A Mathematical Theory",
     "{A} Mathematical Theory", "{A Mathematical Theory}"),
    ("{A Title}", "{A Title}", "{A} Title", "{A Title}"),
    # one-letter words are protected too, also where styles keep them
    ("Thing: A thing", "Thing: A thing", "Thing: {A} thing",
     "{Thing: A thing}"),
    ("Type A Errors", "Type A Errors", "Type {A} Errors", "{Type A Errors}"),
    # acronyms with hyphens are one acronym
    ("A-BC: COVID-19 in 5G-NR", "A-BC: COVID-19 in 5G-NR",
     "{A-BC}: {COVID-19} in {5G-NR}", "{A-BC: COVID-19 in 5G-NR}"),
    ("Detection of R-peaks", "Detection of R-peaks",
     "Detection of {R}-peaks", "{Detection of R-peaks}"),
    # braces inside the title are kept
    (r'Caf{\'e} and {MIMO}', r'Caf{\'e} and {MIMO}', r'Caf{\'e} and {MIMO}',
     r'{Caf{\'e} and {MIMO}}'),
    # two groups of braces are not one around the whole title
    ("{A} and {B}", "{A} and {B}", "{A} and {B}", "{{A} and {B}}"),
    ("", "", "", ""),
])
def test_protect_title(title, keep, acronyms, whole):
    assert protect_title(title, TITLE_KEEP) == keep
    assert protect_title(title, TITLE_ACRONYMS) == acronyms
    assert protect_title(title, TITLE_WHOLE) == whole

def test_protect_title_twice_is_the_same():
    for _mode in (TITLE_ACRONYMS, TITLE_WHOLE):
        once = protect_title("Acro IN mmWave Title", _mode)
        assert protect_title(once, _mode) == once

def test_protect_title_unknown_mode():
    with pytest.raises(ValueError):
        protect_title("Title", "shield")

def test_is_wrapped():
    assert is_wrapped("{A Title}")
    assert is_wrapped("{{A} Title}")
    assert not is_wrapped("{A} Title")
    assert not is_wrapped("{A} and {B}")
    assert not is_wrapped(r"{A \} B")

def test_protect_title_in_entry_without_title():
    entry = {"ID": "Key", "ENTRYTYPE": "misc"}
    assert protect_title_in_entry(entry, TITLE_WHOLE) == {"ID": "Key",
                                                          "ENTRYTYPE": "misc"}

def test_clean_fields_only_given_fields():
    entry = {"pages": "1-2", "month": "jul", "author": "Paul Erdős"}
    assert clean_fields(dict(entry), ("pages",)) == dict(entry, pages="1--2")
    assert clean_fields(dict(entry), ()) == entry
    # the title is protected with `protect_title`, not cleaned here
    assert clean_fields({"title": "IEEE"}, ("title",)) == {"title": "IEEE"}

@pytest.mark.parametrize("month,macro", [
    ("November", "nov"), ("nov", "nov"), ("aug", "aug"), ("Aug.", "aug"),
    ("8", "aug"), ("08", "aug"), ("12", "dec"), ("Spring", "Spring"),
    ("13", "13")])
def test_month_to_macro(month, macro):
    assert month_to_macro(month) == macro
    # a month that is not known stays text
    assert isinstance(month_to_macro(month), Macro) == (month not in
                                                        ("Spring", "13"))

def test_clean_fields_for_bibtex():
    entry = {"month": "aug", "pages": "1-2"}
    assert clean_fields(dict(entry), ("month",)) == {"month": "8",
                                                     "pages": "1-2"}
    assert clean_fields(dict(entry), ("month", "pages"),
                        BIBTEX_FIELD_CLEANERS) == {"month": "aug",
                                                   "pages": "1--2"}

def test_month_is_written_without_braces():
    entry = {"ID": "Key", "ENTRYTYPE": "misc", "month": month_to_macro("8"),
             "note": "aug"}
    text = format_bib_entries([entry])
    assert "month = aug," in text and "note = {aug}," in text
    # the entry is not changed for the writer
    assert entry["month"] == "aug" and isinstance(entry["month"], Macro)

def test_remove_fields():
    entry = {"ID": "Key", "abstract": "Text", "note": "Note"}
    assert remove_fields(entry, ("abstract", "file")) == {"ID": "Key",
                                                          "note": "Note"}

@pytest.mark.parametrize("author", ["Claude E. Shannon", "Shannon, Claude E.",
                                    "Claude E. Shannon and Warren Weaver"])
def test_generate_key_without_cleaned_names(author):
    """The key has the last name, also if the names are not cleaned."""
    entry = {"ID": "Key", "author": author, "year": "1948",
             "title": "A Mathematical Theory of Communication"}
    assert generate_key(entry) == "Shannon1948mathematical"

def test_rename_duplicate_keys():
    entries = [{"ID": "A"}, {"ID": "A"}, {"ID": "B"}, {"ID": "A"}]
    entries, renamed = rename_duplicate_keys(entries)
    assert [k["ID"] for k in entries] == ["A", "A:b", "B", "A:c"]
    assert renamed == {"A": 3}

def test_read_keeps_undefined_strings():
    bib_str = ("@string{known = {Known Journal}}\n"
               "@article{a, journal = jacm, title = known # { and } # other}\n"
               "@article{b, journal = known, month = jan}\n")
    database, skipped, undefined = read_bib_string(bib_str)
    entries = database.get_entry_dict()
    assert entries["a"]["journal"] == "jacm"
    assert entries["a"]["title"] == "Known Journal and other"
    assert entries["b"]["journal"] == "Known Journal"
    assert undefined == ["jacm", "other"]
    assert skipped == []


@pytest.mark.parametrize("bibtex,biblatex", [
    ({"ENTRYTYPE": "article", "journal": "J", "address": "Here"},
     {"ENTRYTYPE": "article", "journaltitle": "J", "location": "Here"}),
    ({"ENTRYTYPE": "phdthesis", "school": "Uni"},
     {"ENTRYTYPE": "thesis", "type": "phdthesis", "institution": "Uni"}),
    ({"ENTRYTYPE": "mastersthesis", "school": "Uni"},
     {"ENTRYTYPE": "thesis", "type": "mathesis", "institution": "Uni"}),
    ({"ENTRYTYPE": "techreport", "institution": "Lab"},
     {"ENTRYTYPE": "report", "type": "techreport", "institution": "Lab"}),
    ({"ENTRYTYPE": "misc", "archiveprefix": "arXiv", "primaryclass": "cs.IT"},
     {"ENTRYTYPE": "misc", "eprinttype": "arXiv", "eprintclass": "cs.IT"}),
])
def test_convert_both_ways(bibtex, biblatex):
    assert to_biblatex(dict(bibtex)) == biblatex
    assert to_bibtex(dict(biblatex)) == bibtex

def test_to_biblatex_keeps_existing_fields():
    entry = {"ENTRYTYPE": "techreport", "type": "Memo",
             "journal": "A", "journaltitle": "B"}
    assert to_biblatex(entry) == {"ENTRYTYPE": "report", "type": "Memo",
                                  "journal": "A", "journaltitle": "B"}

@pytest.mark.parametrize("biblatex,bibtex", [
    ({"ENTRYTYPE": "online", "url": "u", "date": "2020-07-15"},
     {"ENTRYTYPE": "misc", "url": "u", "year": "2020", "month": "jul"}),
    ({"ENTRYTYPE": "article", "date": "2020"},
     {"ENTRYTYPE": "article", "year": "2020"}),
    # a different year keeps the date
    ({"ENTRYTYPE": "article", "year": "2019", "date": "2020"},
     {"ENTRYTYPE": "article", "year": "2019", "date": "2020"}),
    # a date range is not converted
    ({"ENTRYTYPE": "article", "date": "2020/2021"},
     {"ENTRYTYPE": "article", "date": "2020/2021"}),
    ({"ENTRYTYPE": "thesis", "type": "Habilitation", "institution": "Uni"},
     {"ENTRYTYPE": "phdthesis", "type": "Habilitation", "school": "Uni"}),
    ({"ENTRYTYPE": "collection", "editor": "E"},
     {"ENTRYTYPE": "book", "editor": "E"}),
])
def test_to_bibtex(biblatex, bibtex):
    assert to_bibtex(biblatex) == bibtex
    if "month" in bibtex:
        assert isinstance(biblatex["month"], Macro)


_PAPER = {"ID": "li2020federated", "ENTRYTYPE": "article",
          "author": "Li, Tian and Sahu, Anit Kumar and Zaheer, Manzil and "
                    "Sanjabi, Maziar and Talwalkar, Ameet and Smith, Virginia",
          "title": "Federated optimization in heterogeneous networks",
          "journal": "Proceedings of Machine learning and systems",
          "pages": "429--450", "volume": "2", "year": "2020"}

def _as_type(entry, entry_type, **fields):
    entry = dict(entry, ID=entry["ID"] + "b", ENTRYTYPE=entry_type, **fields)
    if entry_type != "article":
        entry["booktitle"] = entry.pop("journal")
    return entry

@pytest.mark.parametrize("other,duplicate", [
    # a conference paper, also exported as @article with the proceedings
    (_as_type(_PAPER, "inproceedings",
              journal="Proceedings of Machine Learning and Systems"), True),
    (_as_type(_PAPER, "conference"), True),
    # the journal version of a conference paper is another work
    (_as_type(_PAPER, "inproceedings", year="2019"), False),
    (_as_type(_PAPER, "inproceedings", pages="1--12"), False),
    (_as_type(_PAPER, "inproceedings",
              journal="IEEE Transactions on Communications"), False),
    # only papers are compared across types
    (_as_type(_PAPER, "book"), False),
])
def test_duplicate_papers_of_different_types(other, duplicate):
    pairs = get_duplicate_index_pairs([_PAPER, other])
    assert pairs == ([(0, 1)] if duplicate else [])
