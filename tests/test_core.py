import pytest

from bibtextools.core.fields import clean_fields, remove_fields
from bibtextools.core.formats import to_biblatex, to_bibtex
from bibtextools.core.keys import generate_key, rename_duplicate_keys
from bibtextools.core.titles import (TITLE_ACRONYMS, TITLE_KEEP, TITLE_WHOLE,
                                     is_wrapped, protect_title,
                                     protect_title_in_entry)
from bibtextools.util import read_bib_string


@pytest.mark.parametrize("title,keep,acronyms,whole", [
    ("The IEEE Standard", "The IEEE Standard", "The {IEEE} Standard",
     "{The IEEE Standard}"),
    # no braces in braces, which the old whole-title mode added
    ("A Mathematical Theory", "A Mathematical Theory",
     "{A} Mathematical Theory", "{A Mathematical Theory}"),
    ("{A Title}", "{A Title}", "{A} Title", "{A Title}"),
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
     {"ENTRYTYPE": "misc", "url": "u", "year": "2020", "month": "July"}),
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
