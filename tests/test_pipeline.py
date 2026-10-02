import logging

import pytest
from bibtexparser.bibdatabase import UndefinedString

from bibtextools import pipeline
from bibtextools.clean_bib_file import clean_bib_file_main, remove_duplicate_entries
from bibtextools.combine_bib_files import combine_bib_files_main
from bibtextools.const import DEFAULT_REMOVE, KEY_ID
from bibtextools.filter_bib_file import filter_cited_main, get_bbl_keys
from bibtextools.core.fields import FIELD_CLEANERS
from bibtextools.core.titles import TITLE_ACRONYMS, TITLE_WHOLE
from bibtextools.modernize_bib_file import modernize_bib_main
from bibtextools.util import (format_bib_entries, load_abbr, load_bib_file,
                              parse_bib_string, write_bib_database)

BIB_MAIN = "old.bib"
DUPLICATE_CONTENT = "duplicate_content.bib"
ABBR = "abbr.bib"
DIRTY_BIB = "dirty.bib"


def _sources(*bib_files):
    sources = []
    for _bib_file in bib_files:
        with open(_bib_file, encoding="utf-8") as _file:
            sources.append((_bib_file, _file.read()))
    return sources


def test_unicode_keeps_shielded_titles():
    source = ("@article{erdos1960,\n  author = {Paul Erdős and Alfréd Rényi},\n"
              "  title = {On the Evolution of {IEEE} Random Graphs},\n}\n")
    options = pipeline.PipelineOptions(clean_fields=tuple(FIELD_CLEANERS),
                                       titles=TITLE_WHOLE, replace_unicode=True)
    entry = pipeline.run_pipeline([("a.bib", source)], options).entries[0].entry
    assert entry["title"] == "{On the Evolution of {IEEE} Random Graphs}"
    assert entry["author"] == "Erd{\\H o}s, Paul and R{\\'e}nyi, Alfr{\\'e}d"


@pytest.mark.parametrize("remove_duplicates", (True, False))
def test_modernize_like_cli(remove_duplicates):
    expected = modernize_bib_main(DUPLICATE_CONTENT, remove_fields=DEFAULT_REMOVE,
                                  replace_ids=True, iso4=True, shield_title=True,
                                  remove_duplicates=remove_duplicates)
    options = pipeline.PipelineOptions(
        remove_fields=DEFAULT_REMOVE, generate_keys=True, iso4=True,
        titles=TITLE_WHOLE, clean_fields=tuple(FIELD_CLEANERS),
        rename_duplicate_keys=True,
        duplicates=(pipeline.DUPLICATES_REMOVE_SHORTER if remove_duplicates
                    else pipeline.DUPLICATES_KEEP))
    result = pipeline.run_pipeline(_sources(DUPLICATE_CONTENT), options)
    assert result.text == format_bib_entries(expected)

def test_modernize_default_like_cli():
    expected = modernize_bib_main(BIB_MAIN, remove_fields=DEFAULT_REMOVE)
    options = pipeline.PipelineOptions(clean_fields=tuple(FIELD_CLEANERS),
                                       titles=TITLE_ACRONYMS,
                                       remove_fields=DEFAULT_REMOVE)
    result = pipeline.run_pipeline(_sources(BIB_MAIN), options)
    assert result.text == format_bib_entries(expected)

@pytest.mark.parametrize("remove_duplicates", (True, False))
def test_clean_like_cli(remove_duplicates):
    expected = clean_bib_file_main(DUPLICATE_CONTENT, abbr_file=ABBR,
                                   remove_fields=DEFAULT_REMOVE,
                                   replace_unicode=True,
                                   remove_duplicates=remove_duplicates)
    options = pipeline.PipelineOptions(
        abbr=load_abbr(ABBR), remove_fields=DEFAULT_REMOVE,
        replace_unicode=True, rename_duplicate_keys=True,
        duplicates=(pipeline.DUPLICATES_REMOVE_SHORTER if remove_duplicates
                    else pipeline.DUPLICATES_KEEP))
    result = pipeline.run_pipeline(_sources(DUPLICATE_CONTENT), options)
    assert result.text == format_bib_entries(expected)

def test_clean_abbreviations_like_cli():
    expected = clean_bib_file_main(DIRTY_BIB, abbr_file=ABBR,
                                   replace_unicode=True)
    options = pipeline.PipelineOptions(abbr=load_abbr(ABBR),
                                       replace_unicode=True,
                                       rename_duplicate_keys=True)
    result = pipeline.run_pipeline(_sources(DIRTY_BIB), options)
    assert result.text == format_bib_entries(expected)
    assert "Super Long Text" in result.text

@pytest.mark.parametrize("allow_duplicates", (True, False))
def test_combine_like_cli(allow_duplicates):
    bib_files = ["duplicates.bib", "unicode.bib"]
    expected = combine_bib_files_main(bib_files, remove_duplicates=True,
                                      allow_duplicates=allow_duplicates)
    options = pipeline.PipelineOptions(
        duplicates=pipeline.DUPLICATES_REMOVE_SHORTER,
        rename_duplicate_keys=not allow_duplicates)
    result = pipeline.run_pipeline(_sources(*bib_files), options)
    assert result.text == format_bib_entries(expected)

def test_filter_cited_like_cli():
    expected = filter_cited_main("crossref.bib", "crossref.bbl")
    cited_keys, _backend = get_bbl_keys("crossref.bbl")
    options = pipeline.PipelineOptions(cited_keys=frozenset(cited_keys))
    result = pipeline.run_pipeline(_sources("crossref.bib"), options)
    assert result.text == format_bib_entries(expected)
    assert set(result.removed.values()) == {"not cited"}

def test_filter_cited_missing_keys():
    cited_keys, _backend = get_bbl_keys("cited.bbl")
    options = pipeline.PipelineOptions(cited_keys=frozenset(cited_keys))
    result = pipeline.run_pipeline(_sources(BIB_MAIN), options)
    assert result.missing_keys == {"NotInBib"}
    assert any("NotInBib" in _msg for _level, _msg in result.messages)

def test_origins_and_changes():
    options = pipeline.PipelineOptions(clean_fields=("month",),
                                       remove_fields=("abstract",),
                                       sort_by_id=False)
    result = pipeline.run_pipeline(_sources(BIB_MAIN), options)
    first = result.entries[0]
    assert first.origin == (0, 0) and first.entry[KEY_ID] == "Key123"
    assert first.changed == {"month"} and first.removed == {"abstract"}
    assert not first.added and not first.id_changed
    assert result.originals[(0, 0)]["month"] == "aug"

def test_added_fields_with_arxiv_lookup():
    options = pipeline.PipelineOptions(arxiv=True,
                                       arxiv_lookup=lambda eprint: "cs.IT")
    result = pipeline.run_pipeline(_sources(BIB_MAIN), options)
    added = [_out for _out in result.entries if _out.added]
    assert added and all(_out.added == {"archiveprefix", "primaryclass"}
                         for _out in added)

def test_arxiv_style_changes():
    options = pipeline.PipelineOptions(arxiv_style="journal")
    result = pipeline.run_pipeline(_sources("arxiv.bib"), options)
    by_id = {_out.entry[KEY_ID]: _out for _out in result.entries}
    converted = by_id["EprintStyle"]
    assert converted.type_changed and converted.added == {"journal"}
    assert converted.removed == {"eprint", "archiveprefix", "primaryclass"}
    # already in the style
    assert not by_id["GoogleScholar"].type_changed
    assert not by_id["GoogleScholar"].changed
    assert not by_id["Published"].type_changed

def test_entry_lines():
    options = pipeline.PipelineOptions(sort_by_id=True)
    result = pipeline.run_pipeline(_sources(BIB_MAIN, "unicode.bib"), options)
    lines = result.text.split("\n")
    for _out in result.entries:
        assert lines[_out.line-1] == _out.text.split("\n")[0]
    assert [_out.origin[0] for _out in result.entries].count(1) == 2

def test_output_like_write(tmpdir):
    entries = load_bib_file(BIB_MAIN).get_entry_list()
    out_file = tmpdir.join("out.bib")
    write_bib_database(entries, str(out_file))
    result = pipeline.run_pipeline(_sources(BIB_MAIN))
    assert out_file.read_text("utf-8") == result.text

def test_choose_duplicates():
    sources = _sources(DUPLICATE_CONTENT)
    options = pipeline.PipelineOptions(duplicates=pipeline.DUPLICATES_CHOOSE)
    runner = pipeline.Pipeline()
    result = runner.run(sources, options)
    assert len(result.duplicate_pairs) == 2
    assert result.unresolved_pairs == result.duplicate_pairs
    assert len(result.entries) == 9 and not result.removed
    first, second = result.duplicate_pairs
    options.duplicate_decisions = {first: first[0], second: None}
    result = runner.run(sources, options)
    assert result.unresolved_pairs == []
    assert result.decided_pairs == [first, second]
    assert list(result.removed) == [first[0]]
    assert len(result.entries) == 8

def test_decided_pairs_without_pairs_that_no_longer_matter():
    """Of three copies of a work, after removing one copy, its pair with the
    third copy no longer matters."""
    entry = ("@article{{{},\n  author = {{Claude E. Shannon}},\n"
             "  title = {{A Mathematical Theory of Communication}},\n"
             "  journal = {{Bell System Technical Journal}},\n"
             "  year = {{1948}},\n}}\n")
    sources = [("a.bib", "".join(entry.format(k) for k in "ABC"))]
    options = pipeline.PipelineOptions(duplicates=pipeline.DUPLICATES_CHOOSE)
    result = pipeline.run_pipeline(sources, options)
    pair_ab, pair_ac, pair_bc = result.duplicate_pairs
    assert result.unresolved_pairs == [pair_ab, pair_ac, pair_bc]
    assert result.decided_pairs == []
    options.duplicate_decisions = {pair_ab: pair_ab[0]}
    result = pipeline.run_pipeline(sources, options)
    assert result.decided_pairs == [pair_ab]
    assert result.unresolved_pairs == [pair_bc]

BIB_ONE = """@article{Key1,
  author = {Claude E. Shannon},
  title = {A Mathematical Theory of IEEE Communication},
  journal = {Bell System Technical Journal},
  pages = {379-423},
  month = jul,
  year = {1948},
  abstract = {Some text},
  note = {Erdős},
}
"""

@pytest.mark.parametrize("options,changed", [
    (dict(clean_fields=("pages",)), {"pages"}),
    (dict(clean_fields=("month",)), {"month"}),
    (dict(clean_fields=("author",)), {"author"}),
    (dict(titles=TITLE_ACRONYMS), {"title"}),
    (dict(titles=TITLE_WHOLE), {"title"}),
    (dict(iso4=True), {"journal"}),
    (dict(replace_unicode=True), {"note"}),
    (dict(remove_fields=("abstract",)), {"-abstract"}),
    (dict(generate_keys=True), {"ID"}),
    (dict(), set()),
])
def test_each_setting_alone(options, changed):
    """Each setting changes only its own fields, without other settings."""
    result = pipeline.run_pipeline([("a.bib", BIB_ONE)],
                                   pipeline.PipelineOptions(**options))
    out = result.entries[0]
    assert not out.added
    assert (out.changed | set("-" + k for k in out.removed)
            | ({"ID"} if out.id_changed else set())) == changed

BIB_THESIS = """@phdthesis{Key1,
  author = {Claude E. Shannon},
  title = {An Algebra for Theoretical Genetics},
  school = {MIT},
  year = {1940},
}
"""

@pytest.mark.parametrize("output,entry_type,field", [
    (None, "thesis", "institution"),
    (pipeline.OUTPUT_BIBLATEX, "thesis", "institution"),
    (pipeline.OUTPUT_BIBTEX, "phdthesis", "school"),
])
def test_convert_fields_for_output(output, entry_type, field):
    options = pipeline.PipelineOptions(convert_fields=True, output=output)
    entry = pipeline.run_pipeline([("a.bib", BIB_THESIS)], options).entries[0].entry
    assert entry["ENTRYTYPE"] == entry_type and entry[field] == "MIT"

def test_convert_fields_before_removing_fields():
    options = pipeline.PipelineOptions(convert_fields=True,
                                       remove_fields=("institution",))
    entry = pipeline.run_pipeline([("a.bib", BIB_THESIS)], options).entries[0].entry
    assert "institution" not in entry and "school" not in entry

def test_undefined_abbreviations_are_kept():
    with open(DIRTY_BIB, encoding="utf-8") as _file:
        sources = [(DIRTY_BIB, _file.read())]
    result = pipeline.run_pipeline(sources)
    assert result.undefined_strings == {0: ["my_abbr"]}
    assert any(_level == logging.WARNING and "my_abbr" in _msg
               for _level, _msg in result.messages)
    entry = next(k.entry for k in result.entries if k.entry["ID"] == "Cesar2013")
    assert entry["journal"] == "my_abbr"
    # with the abbreviations, nothing is undefined
    result = pipeline.run_pipeline(sources, pipeline.PipelineOptions(
        abbr=load_abbr(ABBR)))
    assert result.undefined_strings == {}

def test_cache_is_reused():
    sources = _sources(BIB_MAIN)
    runner = pipeline.Pipeline()
    runner.run(sources, pipeline.PipelineOptions())
    loaded = runner._loaded
    runner.run(sources, pipeline.PipelineOptions(replace_unicode=True))
    assert runner._loaded is loaded
    runner.run(sources, pipeline.PipelineOptions(abbr={"a": "b"}))
    assert runner._loaded is not loaded

def test_abbreviations_are_not_kept():
    with open(DIRTY_BIB, encoding="utf-8") as _file:
        bib_str = _file.read()
    with_abbr = parse_bib_string(bib_str, abbr=load_abbr(ABBR))
    assert with_abbr.get_entry_dict()["Cesar2013"]["journal"] == "Super Long Text"
    with pytest.raises(UndefinedString):
        parse_bib_string(bib_str)

def test_remove_duplicates_with_resolver():
    bib_database = load_bib_file(DUPLICATE_CONTENT)
    pairs = []
    def resolver(entry1, entry2):
        pairs.append((entry1[KEY_ID], entry2[KEY_ID]))
        return entry2
    results = remove_duplicate_entries(bib_database, resolver=resolver)
    ids = set(x[KEY_ID] for x in results)
    assert len(pairs) == 2 and len(results) == 7
    assert not ids & set(_id2 for _id1, _id2 in pairs)
