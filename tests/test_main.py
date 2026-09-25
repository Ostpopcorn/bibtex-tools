import os.path
import sys

import pytest

import bibtexparser
from bibtexparser.bparser import BibTexParser

from bibtextools.__main__ import main


DUPLICATE_CONTENT = "duplicate_content.bib"
BIB_MAIN = "old.bib"
SECOND_BIB = "unicode.bib"
CLEAN_BIB_MAIN = "clean-old.bib"

def test_main_modern(tmpdir, bib_file=BIB_MAIN):
    out_file = os.path.join(tmpdir, CLEAN_BIB_MAIN)
    sys.argv = [sys.argv[0], 'modernize', bib_file, '-o', '{}'.format(out_file)]
    main()
    with open(out_file, encoding="utf-8") as _bib_file:
        parser = BibTexParser(homogenize_fields=True, common_strings=True)
        bib_database = bibtexparser.load(_bib_file, parser=parser)
    assert len(bib_database.get_entry_list()) == 6

@pytest.mark.parametrize("options,num_entries",
                         [([], 7), (["--remove-duplicates"], 7),
                          (["--no-remove-duplicates"], 9)])
def test_main_clean_remove_duplicates(tmpdir, options, num_entries):
    out_file = os.path.join(tmpdir, "clean.bib")
    sys.argv = [sys.argv[0], 'clean', *options, DUPLICATE_CONTENT, '-o', out_file]
    main()
    with open(out_file, encoding="utf-8") as _bib_file:
        parser = BibTexParser(homogenize_fields=True, common_strings=True)
        bib_database = bibtexparser.load(_bib_file, parser=parser)
    assert len(bib_database.get_entry_list()) == num_entries

def test_main_clean_interactive(tmpdir, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt="": "0")
    out_file = os.path.join(tmpdir, "clean.bib")
    sys.argv = [sys.argv[0], 'clean', '-i', DUPLICATE_CONTENT, '-o', out_file]
    main()
    with open(out_file, encoding="utf-8") as _bib_file:
        parser = BibTexParser(homogenize_fields=True, common_strings=True)
        bib_database = bibtexparser.load(_bib_file, parser=parser)
    assert len(bib_database.get_entry_list()) == 9

def test_main_force_removed():
    sys.argv = [sys.argv[0], 'clean', '--force', DUPLICATE_CONTENT]
    with pytest.raises(SystemExit):
        main()

def test_main_combine(tmpdir, bib_file=[BIB_MAIN, SECOND_BIB]):
    out_file = os.path.join(tmpdir, CLEAN_BIB_MAIN)
    sys.argv = [sys.argv[0], 'combine', *bib_file, '-o', '{}'.format(out_file)]
    main()
    with open(out_file, encoding="utf-8") as _bib_file:
        parser = BibTexParser(homogenize_fields=True, common_strings=True)
        bib_database = bibtexparser.load(_bib_file, parser=parser)
    assert len(bib_database.get_entry_list()) == 8
