import json

from bibtextools import web
from bibtextools.const import DEFAULT_REMOVE


def _source(bib_file):
    with open(bib_file, encoding="utf-8") as _file:
        return {"name": bib_file, "text": _file.read()}

def _read(name):
    with open(name, encoding="utf-8") as _file:
        return _file.read()

def _run(request):
    return json.loads(web.run(json.dumps(request)))


def test_defaults():
    defaults = json.loads(web.defaults())
    assert defaults["remove_fields"] == DEFAULT_REMOVE
    assert "month" in defaults["clean_fields"]

def test_run_marks_changes_in_both_files():
    response = _run({"sources": [_source("old.bib")],
                     "options": {"clean_fields": ["month"],
                                 "remove_fields": ["abstract"]}})
    out = next(e for e in response["entries"] if e["id"] == "Key123")
    assert out["changed"] == ["month"] and out["removed"] == ["abstract"]
    assert out["fields"]["month"][0] == out["fields"]["month"][1]
    lines = response["text"].split("\n")
    assert lines[out["line"]-1] == "@article{Key123,"
    original = response["sources"][0]["entries"][0]
    assert original["origin"] == out["origin"] and original["lines"] == [0, 14]
    source_lines = _read("old.bib").split("\n")
    first, last = original["fields"]["month"]
    assert source_lines[first] == source_lines[last] == "month = {aug},"

def test_run_filter_and_abbreviations():
    response = _run({"sources": [_source("dirty.bib"), _source("old.bib")],
                     "abbr": _read("abbr.bib"), "bbl": _read("cited.bbl"),
                     "options": {}})
    assert response["cited"] == {"count": 3, "backend": "biblatex", "kept": 2,
                                 "missing": ["NotInBib"]}
    assert set(response["removed"].values()) == {"not cited"}
    response = _run({"sources": [_source("dirty.bib")],
                     "abbr": _read("abbr.bib"), "options": {}})
    # expanded abbreviations are changes
    assert response["entries"][0]["changed"] == ["journal"]

def test_run_undefined_abbreviation():
    response = _run({"sources": [_source("dirty.bib")], "options": {}})
    assert "my_abbr" in response["error"]

def test_run_choose_duplicates():
    request = {"sources": [_source("duplicate_content.bib")],
               "options": {"duplicates": "choose"}}
    response = _run(request)
    pairs = response["duplicate_pairs"]
    assert len(pairs) == 2 and response["unresolved_pairs"] == pairs
    assert set(response["pair_entries"]) == set(sum(pairs, []))
    request["options"]["decisions"] = [[pairs[0], pairs[0][1]],
                                       [pairs[1], None]]
    response = _run(request)
    assert list(response["removed"]) == [pairs[0][1]]
    assert response["unresolved_pairs"] == []

def test_run_arxiv_categories():
    request = {"sources": [_source("old.bib")],
               "options": {"arxiv": True}}
    response = _run(request)
    assert response["eprints"] == ["2009.09852"]
    request["arxiv_categories"] = {"2009.09852": "cs.IT"}
    response = _run(request)
    out = next(e for e in response["entries"] if e["id"] == "Besser2020CLpart1")
    assert out["added"] == ["archiveprefix", "primaryclass"]

def _run_text(text, options=None):
    return _run({"sources": [{"name": "test.bib", "text": text}],
                 "options": options or {}})

def test_run_highlights_fields_on_one_line():
    response = _run_text("@misc{Key, title={A}, year=2020, month=jan}\n",
                         {"clean_fields": ["month"]})
    out = response["entries"][0]
    original = response["sources"][0]["entries"][0]
    assert out["changed"] == ["month"] and original["fields"]["month"] == [0, 0]

def test_run_highlights_without_comments():
    response = _run_text("@article{Key,\n  title = {A},\n"
                         "  % note = {Commented out},\n  year = {2020},\n}\n",
                         {"remove_fields": ["title"]})
    original = response["sources"][0]["entries"][0]
    assert response["entries"][0]["removed"] == ["title"]
    assert original["fields"] == {"title": [1, 1], "year": [3, 3]}

def test_run_changed_is_what_is_shown():
    text = ("@article{Key,\n  title = \"A  title\",\n  month = nov,\n"
            "  Link = {http://a.org},\n  year = 2020,\n}\n")
    out = _run_text(text)["entries"][0]
    # quotes, spaces, and bare numbers are not changes, but abbreviations
    # that are expanded and renamed fields are
    assert out["changed"] == ["month", "url"]
    assert out["fields"]["month"] == [1, 1]

def test_run_arxiv_style():
    request = {"sources": [_source("arxiv.bib")],
               "options": {"arxiv_style": "eprint", "arxiv": True}}
    response = _run(request)
    out = next(e for e in response["entries"] if e["id"] == "GoogleScholar")
    assert out["type_changed"] and out["removed"] == ["journal"]
    assert out["added"] == ["archiveprefix", "eprint"]
    # the converted preprints need their categories as well
    assert "2101.00001" in response["eprints"]
    request["options"]["arxiv_style"] = "journal"
    response = _run(request)
    assert "2101.00001" not in response["eprints"]
    assert "2009.09852" in response["eprints"]  # the published article
