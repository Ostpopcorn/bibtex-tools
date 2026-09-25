import pytest

import bibtexparser
from bibtexparser.bparser import BibTexParser

from bibtextools.util import (load_bib_file, load_abbr, get_entry_spans,
                              get_field_spans)


ABBR = "abbr.bib"
DIRTY_BIB = "dirty.bib"

def test_replace_abbr_from_file():
    bib_data = load_bib_file(DIRTY_BIB, abbr=ABBR)
    entry = bib_data.get_entry_dict()["Cesar2013"]
    assert entry['journal'] == "Super Long Text"

def test_load_abbr_from_file():
    abbr = load_abbr(ABBR)
    assert abbr["my_abbr"] == "Super Long Text"

COMMENTS_BIB = "comments.bib"

def test_load_entries_with_comments():
    entries = load_bib_file(COMMENTS_BIB).get_entry_dict()
    assert set(entries) == {"FullLineComment", "TrailingComment",
                            "PercentInValues", "ParenEntry"}
    assert "note" not in entries["FullLineComment"]
    assert entries["FullLineComment"]["journal"] == "Journal Name"
    assert entries["TrailingComment"]["journal"] == "Journal Name"

def test_load_keeps_percent_in_values():
    entry = load_bib_file(COMMENTS_BIB).get_entry_dict()["PercentInValues"]
    assert entry["title"] == r'50\% of "Everything"'
    assert entry["note"] == "Improves by 20% on average"
    assert entry["url"] == "https://example.com/some%20file.pdf"

def test_load_warns_about_unreadable_entries(caplog):
    load_bib_file(COMMENTS_BIB)
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert ("MissingComma" in warnings[0] and "InComment" not in warnings[0]
            and "CommentedOut" not in warnings[0])

def test_load_no_warning_for_valid_file(caplog):
    load_bib_file("duplicates.bib")
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


def _fields(bib_str):
    (_id, start, end), = get_entry_spans(bib_str)
    return {k: bib_str[v[0]:v[1]] for k, v in
            get_field_spans(bib_str, start, end).items()}

def test_entry_and_field_spans():
    with open("old.bib", encoding="utf-8") as _file:
        bib_str = _file.read()
    _id, start, end = get_entry_spans(bib_str)[0]
    assert _id == "Key123" and bib_str[start:end].endswith("}")
    fields = get_field_spans(bib_str, start, end)
    assert "author" in fields and "keywords" in fields
    _start, _end, _vstart, _vend = fields["pages"]
    assert bib_str[_start:_end] == "pages = {22--29}"
    assert bib_str[_vstart:_vend] == "{22--29}"

def test_field_spans_on_one_line():
    fields = _fields("@misc{Key, title={A}, author={B, C}, year=2020, month=jan}")
    assert fields == {"title": "title={A}", "author": "author={B, C}",
                      "year": "year=2020", "month": "month=jan"}

def test_field_spans_skip_comments():
    fields = _fields("@article{Key,\n  title = {A}, % a = comment\n"
                     "  % note = {Commented out},\n  year = {2020},\n}")
    assert fields == {"title": "title = {A}", "year": "year = {2020}"}

def test_field_spans_values():
    fields = _fields('@article(Key,\n  journal = "IEEE " # jnl,\n'
                     '  Link = {http://a.org/?b=c},\n'
                     '  title = "{Quoted} x = y",\n'
                     '  abstract = {Line\nx = 5}\n)')
    assert fields == {"journal": 'journal = "IEEE " # jnl',
                      "url": "Link = {http://a.org/?b=c}",
                      "title": 'title = "{Quoted} x = y"',
                      "abstract": "abstract = {Line\nx = 5}"}
