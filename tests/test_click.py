import os.path
import sys

import pytest
from click.testing import CliRunner

import bibtexparser
from bibtexparser.bparser import BibTexParser

from bibtextools.cli import main


DUPLICATE_CONTENT = "duplicate_content.bib"
BIB_MAIN = "old.bib"
SECOND_BIB = "unicode.bib"
CLEAN_BIB_MAIN = "clean-old.bib"
BBL_FILE = "cited.bbl"

def test_main_modern(tmpdir, bib_file=BIB_MAIN):
    out_file = os.path.join(tmpdir, CLEAN_BIB_MAIN)
    runner = CliRunner()
    result = runner.invoke(main, f'-o "{out_file}" modernize {bib_file}')
    with open(out_file, encoding="utf-8") as _bib_file:
        parser = BibTexParser(homogenize_fields=True, common_strings=True)
        bib_database = bibtexparser.load(_bib_file, parser=parser)
    assert (len(bib_database.get_entry_list()) == 6) and (result.exit_code == 0)

def test_main_modern_arxiv_style(tmpdir):
    out_file = os.path.join(tmpdir, "modern.bib")
    runner = CliRunner()
    result = runner.invoke(main, f'-o "{out_file}" modernize --arxiv-style eprint arxiv.bib')
    with open(out_file, encoding="utf-8") as _bib_file:
        entries = bibtexparser.load(_bib_file).get_entry_list()
    preprint = next(_entry for _entry in entries if _entry["ID"] == "GoogleScholar")
    assert result.exit_code == 0, result.output
    assert preprint["ENTRYTYPE"] == "misc" and preprint["eprint"] == "2101.00001"

@pytest.mark.parametrize("options,num_entries",
                         [("", 9), ("--remove-duplicates", 7), ("-i", 7),
                          ("--remove-duplicates -i", 7)])
def test_main_clean_remove_duplicates(tmpdir, options, num_entries):
    out_file = os.path.join(tmpdir, "clean.bib")
    runner = CliRunner()
    result = runner.invoke(main, f'-o "{out_file}" clean {options} {DUPLICATE_CONTENT}',
                           input="\n\n")
    with open(out_file, encoding="utf-8") as _bib_file:
        parser = BibTexParser(homogenize_fields=True, common_strings=True)
        bib_database = bibtexparser.load(_bib_file, parser=parser)
    assert (len(bib_database.get_entry_list()) == num_entries) and (result.exit_code == 0)

def test_main_force_removed():
    runner = CliRunner()
    result = runner.invoke(main, f'clean --force {DUPLICATE_CONTENT}')
    assert result.exit_code == 2

def test_main_combine(tmpdir, bib_file=[BIB_MAIN, SECOND_BIB]):
    out_file = os.path.join(tmpdir, CLEAN_BIB_MAIN)
    runner = CliRunner()
    result = runner.invoke(main, f'-o "{out_file}" combine {bib_file[0]} {bib_file[1]}')
    with open(out_file, encoding="utf-8") as _bib_file:
        parser = BibTexParser(homogenize_fields=True, common_strings=True)
        bib_database = bibtexparser.load(_bib_file, parser=parser)
    assert len(bib_database.get_entry_list()) == 8

def test_main_filter_cited(tmpdir, bib_file=BIB_MAIN, bbl_file=BBL_FILE):
    out_file = os.path.join(tmpdir, "filter-cited-old.bib")
    runner = CliRunner()
    result = runner.invoke(main, f'-o "{out_file}" filter-cited {bib_file} --bbl {bbl_file}')
    with open(out_file, encoding="utf-8") as _bib_file:
        parser = BibTexParser(homogenize_fields=True, common_strings=True)
        bib_database = bibtexparser.load(_bib_file, parser=parser)
    entries = bib_database.get_entry_list()
    kept_ids = {entry["ID"] for entry in entries}
    assert kept_ids == {"Key123", "Conference2015"} and result.exit_code == 0
