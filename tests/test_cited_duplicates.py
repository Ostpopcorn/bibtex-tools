"""Duplicate entries together with a .bbl filter: every cited key stays."""
import json
import os
import sys

import bibtexparser
import pytest
from click.testing import CliRunner

from bibtextools import pipeline, web
from bibtextools.__main__ import main as argparse_main
from bibtextools.cli import main as click_main
from bibtextools.clean_bib_file import (get_duplicate_index_pairs,
                                        get_duplicate_index_pairs_of)
from bibtextools.const import KEY_ID, KEY_IDS
from bibtextools.filter_bib_file import (filter_cited_main, get_bbl_keys,
                                         resolve_cited_duplicates)
from bibtextools.util import load_bib_file

BIB_A = "cited_a.bib"
BIB_B = "cited_b.bib"
# Cites Smith2020 and lee2019study, whose duplicates in the other file are
# longer, Kim2021, whose crossref parent has a longer duplicate, and Same,
# which both files use for different works
ONE_BBL = "cited_one.bbl"
# Cites both Smith2020 and smith2020deep, the same work
BOTH_BBL = "cited_both.bbl"
BOTH_BIBTEX_BBL = "cited_both_bibtex.bbl"
EXPECTED_ONE = {"Smith2020", "lee2019study", "Kim2021", "Conf2021", "Same"}


def _sources(*bib_files):
    sources = []
    for _bib_file in bib_files:
        with open(_bib_file, encoding="utf-8") as _file:
            sources.append((_bib_file, _file.read()))
    return sources

def _run(bbl, duplicates, decisions=None, **kwargs):
    keys, backend = get_bbl_keys(bbl)
    options = pipeline.PipelineOptions(
        cited_keys=frozenset(keys), bbl_backend=backend,
        duplicates=duplicates, duplicate_decisions=decisions or {},
        sort_by_id=False, **kwargs)
    return pipeline.run_pipeline(_sources(BIB_A, BIB_B), options)

def _by_id(result):
    return {_out.entry[KEY_ID]: _out for _out in result.entries}

def _output_keys(entries):
    """The keys that the entries answer to, including their ids."""
    keys = set()
    for _entry in entries:
        keys.add(_entry[KEY_ID])
        keys.update(k.strip() for k in _entry.get(KEY_IDS, "").split(",")
                    if k.strip())
    return keys


def test_longer_duplicate_takes_over_the_cited_key():
    result = _run(ONE_BBL, pipeline.DUPLICATES_REMOVE_SHORTER)
    by_id = _by_id(result)
    assert set(by_id) == EXPECTED_ONE and len(result.entries) == 5
    # smith2020deep from the other file is longer and becomes Smith2020
    assert by_id["Smith2020"].origin == (1, 0) and by_id["Smith2020"].id_changed
    assert by_id["Smith2020"].entry["volume"] == "12"
    assert (result.removed[(0, 0)]
            == "duplicate of smith2020deep, which takes over its key")
    assert by_id["lee2019study"].origin == (0, 1)
    # the crossref parent of a cited entry keeps its key as well
    assert by_id["Conf2021"].origin == (1, 2)
    assert by_id["Kim2021"].entry["crossref"] == "Conf2021"
    assert any("take over the cited keys" in _msg
               for _level, _msg in result.messages)

def test_same_key_keeps_the_first_entry():
    result = _run(ONE_BBL, pipeline.DUPLICATES_REMOVE_SHORTER)
    assert _by_id(result)["Same"].origin == (0, 4)
    assert result.removed[(1, 3)].startswith("same key as an earlier entry")

def test_keep_duplicates_keeps_the_cited_entries():
    result = _run(ONE_BBL, pipeline.DUPLICATES_KEEP)
    by_id = _by_id(result)
    assert set(by_id) == EXPECTED_ONE
    assert by_id["Smith2020"].origin == (0, 0) and not by_id["Smith2020"].id_changed
    assert result.duplicate_pairs is None

@pytest.mark.parametrize("remove,kept", [((1, 0), (0, 0)), ((0, 0), (1, 0))])
def test_choose_which_duplicate_keeps_the_cited_key(remove, kept):
    result = _run(ONE_BBL, pipeline.DUPLICATES_CHOOSE,
                  decisions={((0, 0), (1, 0)): remove})
    assert _by_id(result)["Smith2020"].origin == kept
    # undecided pairs are kept, and the filter removes the uncited entry
    assert ((0, 1), (1, 1)) in result.unresolved_pairs
    assert _by_id(result)["lee2019study"].origin == (1, 1)

def test_both_keys_cited_biblatex_merges_with_ids():
    result = _run(BOTH_BBL, pipeline.DUPLICATES_REMOVE_SHORTER)
    by_id = _by_id(result)
    assert set(by_id) == {"smith2020deep", "Kim2021", "Conf2021"}
    assert by_id["smith2020deep"].entry[KEY_IDS] == "Smith2020"
    assert by_id["smith2020deep"].aliases == ("Smith2020",)
    assert "ids" in by_id["smith2020deep"].added
    assert any("Merged" in _msg for _level, _msg in result.messages)

def test_both_keys_cited_bibtex_keeps_both():
    result = _run(BOTH_BIBTEX_BBL, pipeline.DUPLICATES_REMOVE_SHORTER)
    by_id = _by_id(result)
    assert {"Smith2020", "smith2020deep"} <= set(by_id)
    assert KEY_IDS not in by_id["smith2020deep"].entry
    assert result.both_cited == [((0, 0), (1, 0))]
    assert any(_level == 30 and "BibTeX has no aliases" in _msg
               for _level, _msg in result.messages)

@pytest.mark.parametrize("bbl,output,merged", [
    (BOTH_BBL, None, True),
    (BOTH_BBL, pipeline.OUTPUT_BIBTEX, False),
    (BOTH_BIBTEX_BBL, pipeline.OUTPUT_BIBLATEX, True),
])
def test_output_decides_aliases(bbl, output, merged):
    """Only biblatex resolves the other keys in ids, so the output decides,
    or else the backend of the .bbl file."""
    result = _run(bbl, pipeline.DUPLICATES_REMOVE_SHORTER, output=output)
    by_id = _by_id(result)
    assert (KEY_IDS in by_id["smith2020deep"].entry) == merged
    assert bool(result.both_cited) != merged

def test_unknown_output():
    with pytest.raises(ValueError):
        pipeline.PipelineOptions(output="bibtex8").output_format()

def _decision_sets(bbl):
    pairs = _run(bbl, pipeline.DUPLICATES_CHOOSE).duplicate_pairs
    return [{}, {_pair: _pair[0] for _pair in pairs},
            {_pair: _pair[1] for _pair in pairs}]

@pytest.mark.parametrize("bbl", [ONE_BBL, BOTH_BBL, BOTH_BIBTEX_BBL])
@pytest.mark.parametrize("duplicates", [pipeline.DUPLICATES_KEEP,
                                        pipeline.DUPLICATES_REMOVE_SHORTER,
                                        pipeline.DUPLICATES_CHOOSE])
def test_every_cited_key_stays(bbl, duplicates):
    keys, _backend = get_bbl_keys(bbl)
    present = keys & set(_entry[KEY_ID] for _file in (BIB_A, BIB_B)
                         for _entry in load_bib_file(_file).entries)
    decision_sets = (_decision_sets(bbl)
                     if duplicates == pipeline.DUPLICATES_CHOOSE else [{}])
    for _decisions in decision_sets:
        result = _run(bbl, duplicates, decisions=_decisions)
        output = _output_keys(_out.entry for _out in result.entries)
        assert present <= output
        # and no entry has a key that is not needed
        assert set(_out.entry[KEY_ID] for _out in result.entries) <= present | {"Conf2021"}

def test_generate_keys_is_skipped_while_filtering():
    result = _run(ONE_BBL, pipeline.DUPLICATES_REMOVE_SHORTER,
                  generate_keys=True)
    assert set(_by_id(result)) == EXPECTED_ONE
    assert any("Generate keys is skipped" in _msg
               for _level, _msg in result.messages)


def _entry(key):
    return {KEY_ID: key, "ENTRYTYPE": "misc"}

@pytest.mark.parametrize("cited,aliases,expected", [
    ({"A"}, False, {2: ("A", None)}),
    ({"A", "B"}, True, {2: ("B", "A")}),
    # without aliases, A and B are both kept, and C takes over B
    ({"A", "B"}, False, {0: ("A", None), 2: ("B", None)}),
])
def test_keys_are_taken_over_along_chains(cited, aliases, expected):
    entries = [_entry("A"), _entry("B"), _entry("C")]
    result = resolve_cited_duplicates(entries, cited, pairs=[(0, 1), (1, 2)],
                                      resolve=lambda idx1, idx2: idx1,
                                      aliases=aliases)
    assert {_idx: (_entry[KEY_ID], _entry.get(KEY_IDS))
            for _idx, _entry in result.kept.items()} == expected
    assert [_entry[KEY_ID] for _entry in entries] == ["A", "B", "C"]

def test_three_copies_in_three_files():
    """The longest of three copies is kept, also if the cited one is the
    shortest and the other two are compared only with each other."""
    keys, backend = get_bbl_keys(ONE_BBL)
    options = pipeline.PipelineOptions(
        cited_keys=frozenset(keys), bbl_backend=backend,
        duplicates=pipeline.DUPLICATES_REMOVE_SHORTER, sort_by_id=False)
    result = pipeline.run_pipeline(_sources(BIB_A, BIB_B, "cited_c.bib"),
                                   options)
    assert ((1, 0), (2, 0)) in result.duplicate_pairs
    smith = _by_id(result)["Smith2020"]
    assert smith.origin == (2, 0) and smith.entry["url"] == "https://example.org/smith"
    assert set(_by_id(result)) == EXPECTED_ONE
    kept = filter_cited_main([BIB_A, BIB_B, "cited_c.bib"], ONE_BBL,
                             remove_duplicates=True)
    assert next(_entry for _entry in kept if _entry[KEY_ID] == "Smith2020")["url"]

def _copies(number):
    return [{KEY_ID: "Key{}".format(_idx), "ENTRYTYPE": "article",
             "title": "The Same Work", "author": "Author, Some",
             "journal": "Journal", "year": "2020"} for _idx in range(number)]

def test_copies_of_duplicates_are_compared():
    pairs, warnings = get_duplicate_index_pairs_of(_copies(4), [0])
    assert pairs == [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    assert warnings == []

def test_many_copies_are_not_searched_further():
    pairs, warnings = get_duplicate_index_pairs_of(_copies(7), [0])
    # only the pairs of the cited entry, since 7 copies are more than 5
    assert pairs == [(0, _idx) for _idx in range(1, 7)]
    assert len(warnings) == 1 and "7 entries seem to be the same work" in warnings[0][1]
    pairs, warnings = get_duplicate_index_pairs_of(_copies(7), [0],
                                                   max_duplicates=10)
    assert len(pairs) == 21 and warnings == []

def test_duplicate_search_among_entries():
    entries = load_bib_file(BIB_A).entries + load_bib_file(BIB_B).entries
    among = {0, 6}
    full = get_duplicate_index_pairs(entries)
    assert get_duplicate_index_pairs(entries, among=among) == [
        _pair for _pair in full if set(_pair) & among]
    assert (0, 5) in full


def test_filter_cited_main_with_duplicates(caplog):
    kept = filter_cited_main([BIB_A, BIB_B], ONE_BBL, remove_duplicates=True)
    by_id = {_entry[KEY_ID]: _entry for _entry in kept}
    assert set(by_id) == EXPECTED_ONE and by_id["Smith2020"]["volume"] == "12"
    # users see which entries took over a cited key
    assert any(_record.levelname == "WARNING"
               and "smith2020deep → Smith2020" in _record.getMessage()
               for _record in caplog.records)

def test_filter_cited_main_interactive(monkeypatch):
    # Hitting enter removes the shorter entry
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")
    kept = filter_cited_main([BIB_A, BIB_B], ONE_BBL, interactive=True)
    assert set(_entry[KEY_ID] for _entry in kept) == EXPECTED_ONE

def test_filter_cited_main_without_duplicate_removal():
    kept = filter_cited_main([BIB_A, BIB_B], BOTH_BBL)
    assert set(_entry[KEY_ID] for _entry in kept) == {"Smith2020",
                                                      "smith2020deep",
                                                      "Kim2021", "Conf2021"}

def _read_ids(bib_file):
    with open(bib_file, encoding="utf-8") as _file:
        return {_entry[KEY_ID]: _entry
                for _entry in bibtexparser.load(_file).get_entry_list()}

def test_argparse_filter_cited_with_duplicates(tmpdir):
    out_file = os.path.join(tmpdir, "filtered.bib")
    sys.argv = [sys.argv[0], "filter-cited", BIB_A, BIB_B, "--bbl", BOTH_BBL,
                "--remove-duplicates", "-o", out_file]
    argparse_main()
    entries = _read_ids(out_file)
    assert entries["smith2020deep"][KEY_IDS] == "Smith2020"

def test_click_filter_cited_with_duplicates(tmpdir):
    out_file = os.path.join(tmpdir, "filtered.bib")
    runner = CliRunner()
    result = runner.invoke(click_main, f'-o "{out_file}" filter-cited --bbl {ONE_BBL} '
                                       f'--remove-duplicates {BIB_A} {BIB_B}')
    assert result.exit_code == 0, result.output
    assert set(_read_ids(out_file)) == EXPECTED_ONE


def _web_run(bbl):
    sources = [{"name": _name, "text": _text}
               for _name, _text in _sources(BIB_A, BIB_B)]
    with open(bbl, encoding="utf-8") as _file:
        request = {"sources": sources, "bbl": _file.read(),
                   "options": {"duplicates": pipeline.DUPLICATES_REMOVE_SHORTER}}
    return json.loads(web.run(json.dumps(request)))

def test_web_shows_merged_and_kept_duplicates():
    response = _web_run(BOTH_BBL)
    out = next(_e for _e in response["entries"] if _e["id"] == "smith2020deep")
    assert out["aliases"] == ["Smith2020"] and "ids" in out["added"]
    assert {"0:0", "1:0"} <= set(response["cited"]["origins"])
    assert response["cited"]["both_cited"] == []
    response = _web_run(BOTH_BIBTEX_BBL)
    assert response["cited"]["both_cited"] == [["0:0", "1:0"]]
    assert any(_level == "warning" and "BibTeX has no aliases" in _msg
               for _level, _msg in response["messages"])
