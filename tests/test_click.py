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

def test_main_modern(tmpdir, bib_file=BIB_MAIN):
    out_file = os.path.join(tmpdir, CLEAN_BIB_MAIN)
    runner = CliRunner()
    result = runner.invoke(main, f'-o "{out_file}" modernize {bib_file}')
    with open(out_file, encoding="utf-8") as _bib_file:
        parser = BibTexParser(homogenize_fields=True, common_strings=True)
        bib_database = bibtexparser.load(_bib_file, parser=parser)
    assert (len(bib_database.get_entry_list()) == 6) and (result.exit_code == 0)

@pytest.mark.parametrize("options,num_entries",
                         [("", 7), ("--remove-duplicates", 7),
                          ("--no-remove-duplicates", 9), ("-i", 9)])
def test_main_clean_remove_duplicates(tmpdir, options, num_entries):
    out_file = os.path.join(tmpdir, "clean.bib")
    runner = CliRunner()
    result = runner.invoke(main, f'-o "{out_file}" clean {options} {DUPLICATE_CONTENT}',
                           input="0\n0\n")
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
