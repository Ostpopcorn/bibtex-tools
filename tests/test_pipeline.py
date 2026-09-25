import pytest
from bibtexparser.bibdatabase import UndefinedString

from bibtextools import pipeline
from bibtextools.clean_bib_file import clean_bib_file_main, remove_duplicate_entries
from bibtextools.combine_bib_files import combine_bib_files_main
from bibtextools.const import DEFAULT_REMOVE, KEY_ID
from bibtextools.filter_bib_file import filter_cited_main, get_bbl_keys
from bibtextools.modernize_bib_file import CLEAN_FUNC, modernize_bib_main
from bibtextools.util import (format_bib_entries, get_entry_spans, load_abbr,
                              load_bib_file, parse_bib_string,
                              write_bib_database)

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


@pytest.mark.parametrize("remove_duplicates", (True, False))
def test_modernize_like_cli(remove_duplicates):
    kwargs = dict(remove_fields=DEFAULT_REMOVE, replace_ids=True, iso4=True,
                  shield_title=True)
    expected = modernize_bib_main(DUPLICATE_CONTENT,
                                  remove_duplicates=remove_duplicates, **kwargs)
    options = pipeline.PipelineOptions(
        clean_fields=tuple(CLEAN_FUNC), rename_duplicate_ids=True,
        duplicates=(pipeline.DUPLICATES_REMOVE_SHORTER if remove_duplicates
                    else pipeline.DUPLICATES_KEEP), **kwargs)
    result = pipeline.run_pipeline(_sources(DUPLICATE_CONTENT), options)
    assert result.text == format_bib_entries(expected)

def test_modernize_default_like_cli():
    expected = modernize_bib_main(BIB_MAIN, remove_fields=DEFAULT_REMOVE)
    options = pipeline.PipelineOptions(clean_fields=tuple(CLEAN_FUNC),
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
        replace_unicode=True, rename_duplicate_ids=True,
        duplicates=(pipeline.DUPLICATES_REMOVE_SHORTER if remove_duplicates
                    else pipeline.DUPLICATES_KEEP))
    result = pipeline.run_pipeline(_sources(DUPLICATE_CONTENT), options)
    assert result.text == format_bib_entries(expected)

def test_clean_abbreviations_like_cli():
    expected = clean_bib_file_main(DIRTY_BIB, abbr_file=ABBR,
                                   replace_unicode=True)
    options = pipeline.PipelineOptions(abbr=load_abbr(ABBR),
                                       replace_unicode=True,
                                       rename_duplicate_ids=True)
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
        rename_duplicate_ids=not allow_duplicates)
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
    assert list(result.removed) == [first[0]]
    assert len(result.entries) == 8

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

def test_entry_and_field_spans():
    with open(BIB_MAIN, encoding="utf-8") as _file:
        bib_str = _file.read()
    spans = get_entry_spans(bib_str)
    _id, start, end = spans[0]
    assert _id == "Key123" and bib_str[start:end].endswith("}")
    fields = pipeline.get_field_spans(bib_str, start, end)
    assert "author" in fields and "keywords" in fields
    _start, _end = fields["pages"]
    assert bib_str[_start:_end] == "pages = {22--29},"

def test_output_field_lines():
    text = "@article{Key,\n\tauthor = {A},\n\ttitle = {Line\n2},\n}\n"
    assert pipeline.get_output_field_lines(text) == {"author": (1, 1),
                                                     "title": (2, 3)}
