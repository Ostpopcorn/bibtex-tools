import os
import subprocess
import sys

import pytest

import bibtexparser
from bibtexparser.bparser import BibTexParser

from bibtextools import modernize_bib_file
from bibtextools.const import KEY_ENTRYTYPE
from bibtextools.util import load_bib_file


BIB_MAIN = "old.bib"
ARXIV_API_ANSWER = "arxiv_api.xml"

def test_main_modern(bib_file=BIB_MAIN):
    clean_entries = modernize_bib_file.modernize_bib_main(bib_file)
    assert len(clean_entries) == 6

@pytest.mark.parametrize("remove_duplicates,num_entries", [(True, 7), (False, 9)])
def test_main_modern_remove_duplicates(remove_duplicates, num_entries):
    clean_entries = modernize_bib_file.modernize_bib_main(
        "duplicate_content.bib", remove_duplicates=remove_duplicates)
    assert len(clean_entries) == num_entries

def test_replace_id(bib_file=BIB_MAIN):
    clean_entries = modernize_bib_file.modernize_bib_main(bib_file, replace_ids=True)
    expected_keys = set(["Name2010title", "MultipleWordName2010title",
                         "Jorswieck2020copula", "Duck2018ecg",
                         "AuthorwithLastNames2015title", "Report2005"])
    cleaned_keys = set([k[modernize_bib_file.KEY_ID]
                        for k in clean_entries])
    assert cleaned_keys == expected_keys

@pytest.fixture
def arxiv_api(monkeypatch):
    """Answer requests to the arXiv API with a stored answer, since arXiv does
    not always answer the tests in time. Returns the requested URLs."""
    import feedparser
    parse = feedparser.parse
    urls = []
    def _parse(url, *args, **kwargs):
        urls.append(url)
        return parse(ARXIV_API_ANSWER)
    monkeypatch.setattr(feedparser, "parse", _parse)
    return urls

def test_arxiv_primaryclass(arxiv_api, bib_file=BIB_MAIN):
    clean_entries = modernize_bib_file.modernize_bib_main(bib_file, arxiv=True)
    _entry = [k for k in clean_entries
              if k[modernize_bib_file.KEY_ID] == "Besser2020CLpart1"][0]
    assert _entry[modernize_bib_file.KEY_CATEGORY] == "cs.IT"
    assert _entry[modernize_bib_file.KEY_ARCHIVE] == "arXiv"
    assert arxiv_api == ["http://export.arxiv.org/api/query?id_list=2009.09852"]

def test_arxiv_primaryclass_without_answer(monkeypatch):
    """Without an answer, e.g., if arXiv is not reachable, feedparser returns
    no entries, and the entry is kept as it is."""
    import feedparser
    monkeypatch.setattr(feedparser, "parse",
                        lambda url, *args, **kwargs: feedparser.FeedParserDict(
                            bozo=1, entries=[]))
    assert modernize_bib_file.get_arxiv_category("2009.09852") is None
    entry = modernize_bib_file.modernize_entry(
        {"ID": "Key", "ENTRYTYPE": "misc", "eprint": "2009.09852"}, arxiv=True)
    assert entry == {"ID": "Key", "ENTRYTYPE": "misc", "eprint": "2009.09852"}

def test_journal_abbreviation(bib_file=BIB_MAIN):
    from bibtextools.util import load_bib_file
    abbr_expectation = {"Journal Title": "J. Title",
                        "Title of the Journal": "J. Title",
                        "{IEEE} Communications Letters": "{IEEE} Commun. Lett.",
                       }
    dirty_entries = load_bib_file(bib_file).get_entry_dict()
    clean_entries = modernize_bib_file.modernize_bib_main(bib_file, iso4=True)
    _correct = []
    for _entry in clean_entries:
        if not any(_key in _entry for _key in modernize_bib_file.KEYS_JOURNAL):
            _correct.append(_entry == dirty_entries[_entry[modernize_bib_file.KEY_ID]])
        else:
            for _key in modernize_bib_file.KEYS_JOURNAL:
                if _key in _entry:
                    _correct.append(_entry[_key] == abbr_expectation[dirty_entries[_entry[modernize_bib_file.KEY_ID]]])
    print(_correct)
    assert all(_correct)

def test_author_getnames():
    old_names = ["Last, First", "{van Name}, First", "{One Single Name}",
                 "First {di Last Name}", "von Name, First", "CompanyName",
                 r'Ludger R{\"{u}}schendorf']
    expected = ["Last, First", "{van Name}, First", "{One Single Name}",
                "{di Last Name}, First", "von Name, First", "CompanyName",
                r'R{\"{u}}schendorf, Ludger']
    new_names = modernize_bib_file.getnames(old_names)
    print(old_names)
    print(new_names)
    assert new_names == expected

@pytest.mark.parametrize("title,expected",
                         [("MIMO", r"{MIMO}"), ("M2M", r"{M2M}"),
                          (r"Acro IN mmWave Title", r"Acro {IN} {mmWave} Title"),
                          (r"Math $\mu=\alpha$", r"Math {$\mu=\alpha$}"),
                          (r"Already {ACRO} in", r"Already {ACRO} in"),
                          (r"{Surrounding {ACRO}}", r"Surrounding {ACRO}"),
                          (r"5G should be SHIELded", r"{5G} should be {SHIELded}"),
                          (r"Regular title with Names", r'Regular title with Names'),
                         ])
def test_title_shielding_acronyms(title, expected):
    cleaned = modernize_bib_file.clean_title(title)
    assert cleaned == expected

@pytest.mark.parametrize("title,expected",
                         [("MIMO", r"{{MIMO}}"), ("M2M", r"{{M2M}}"),
                          (r"{MIMO}", r"{MIMO}"), (r"{M2M}", r"{M2M}"),
                          (r"Acro IN mmWave Title", r"{Acro {IN} {mmWave} Title}"),
                          (r"Math $\mu=\alpha$", r"{Math {$\mu=\alpha$}}"),
                          (r"Already {ACRO} in", r"{Already {ACRO} in}"),
                          (r"{Surrounding {ACRO}}", r"{Surrounding {ACRO}}"),
                          (r"{All in curly}", r"{All in curly}"),
                          (r"Regular title with Names", r'{Regular title with Names}'),
                         ])
def test_title_shielding(title, expected):
    cleaned = modernize_bib_file.clean_title(title, shield_title=True)
    assert cleaned == expected

@pytest.mark.parametrize("title,expected",
                         [
("Journal of Polymer Science Part A", "J. Polym. Sci. A"),
("Proceedings of the Institution of Mechanical Engineers, Part A", "Proc. Inst. Mech. Eng. A"),
("Bulletin of the Section of Logic", "Bull. Sect. Log."),
("The Lancet", "Lancet"),
("Baha'i Studies Review", "Baha'i Stud. Rev."),
("Journal of Shi'a Islamic Studies", "J. Shi'a Islam. Stud."),
("The Mariner's Mirror", "Mar. Mirror"),
("The Mechanics' Institute Review", "Mech. Inst. Rev."),
("Journal of Children's Orthopaedics", "J. Child. Orthop."),
("Annali dell'Istituto Superiore di Sanità", "Ann. Ist. Super. Sanità"),
("In Practice", "In Practice"),
("In the Library with the Lead Pipe", "In Libr. Lead Pipe"),
("Off our backs", "Off our backs"),
("Volume!", "Volume!"),
("Australasian Journal of Educational Technology", "Australas. J. Educ. Technol."),
("Real-World Economics Review", "Real-World Econ. Rev."),
("Real Analysis Exchange", "Real Anal. Exch."),
("Annals of Clinical & Laboratory Science", "Ann. Clin. Lab. Sci."),
("Journal of Early Christian Studies", "J. Early Christ. Stud."),
("Journal of Crustacean Biology", "J. Crustac. Biol."),
("Carniflora Australis", "Carniflora Aust."),
("Humana.Mente", "Humana.Mente"),
("Spunti e ricerche", "Spunti ric."),
("Journal of Chemical Physics A", "J. Chem. Phys. A"),
("Revista Médica de Chile", "Rev. Méd. Chile"),
("Romanian Journal of Physics", "Rom. J. Phys."),
("Journal de Théorie des Nombres de Bordeaux", "J. Théor. Nr. Bordx."),
("Labor History", "Labor Hist."),
("Archiv Orientální", "Arch. Orient."),
("Ślaski Kwartalnik Historyczny Sobótka", "Śl. Kwart. Hist. Sobótka"),
("Mitteilungen der Österreichischen Geographischen Gesellschaft", "Mitt. Österr. Geogr. Ges."),
("Filosofický časopis", "Filos. čas."),
("Cahiers québécois de démographie", "Cah. qué. démogr."),
("Análisis Filosófico", "Anál. Filos."),
("Inorganica Chimica Acta", "Inorg. Chim. Acta"),
("Comptes rendus de l'Académie des Sciences", "C. r. Acad. Sci."),
("Proceedings of the National Academy of Sciences of the United States of America", "Proc. Natl. Acad. Sci. U. S. A."),
("Scando-Slavica", "Scando-Slav."),
("Zeitschrift des Deutschen Palästina-Vereins", "Z. Dtsch. Paläst.-Ver."),
("International Journal of e-Collaboration", "Int. J. e-Collab."),
("Proceedings of A. Razmadze Mathematical Institute", "Proc. A. Razmadze Math. Inst."),
("Norsk Militært Tidsskrift", "Nor. Mil. Tidsskr."),
                          ])
def test_journal_abbreviation(title, expected):
    entry = {"journal": title, KEY_ENTRYTYPE: "article"}
    entry = modernize_bib_file.abbreviate_journalname(entry)
    abbr_title = entry['journal']
    assert abbr_title == expected

# Not used due to bug in pyiso4:
# https://github.com/pierre-24/pyiso4/issues/11
#@pytest.mark.parametrize("title,expected",
#                         [
#("J. Polym. Sci. A", "J. Polym. Sci. A"),
#("Proc. Inst. Mech. Eng. A", "Proc. Inst. Mech. Eng. A"),
#("Nor. Mil. Tidsskr.", "Nor. Mil. Tidsskr."),
#("IEEE Trans. on Wireless Communications", "IEEE Trans. Wirel. Commun."),
#                          ])
#def test_existing_journal_abbreviation(title, expected):
#    entry = {"journal": title, KEY_ENTRYTYPE: "article"}
#    entry = modernize_bib_file.abbreviate_journalname(entry)
#    abbr_title = entry['journal']
#    assert abbr_title == expected

def test_journal_abbreviation_non_utf8_default_encoding():
    """pyiso4 reads its data files with the default encoding, which is not
    UTF-8 on Windows (cp1252) or in the C locale (ASCII)."""
    env = dict(os.environ, PYTHONUTF8="0", PYTHONCOERCECLOCALE="0", LC_ALL="C")
    code = ("from bibtextools.modernize_bib_file import abbreviate_journalname\n"
            "entry = {'ENTRYTYPE': 'article', 'journal': 'Journal of Chemical Physics A'}\n"
            "print(abbreviate_journalname(entry)['journal'])")
    result = subprocess.run([sys.executable, "-c", code], env=env,
                            capture_output=True, text=True)
    assert result.stdout.strip() == "J. Chem. Phys. A", result.stderr

def test_abbreviator_is_loaded_once():
    assert modernize_bib_file.get_abbreviator() is modernize_bib_file.get_abbreviator()

def test_journal_abbreviation_keeps_name_on_error(caplog):
    # pyiso4 raises an IndexError for this name
    entry = {"ID": "Key", "ENTRYTYPE": "article",
             "journal": "Transactions on Different Work"}
    result = modernize_bib_file.abbreviate_journalname(entry)
    assert result["journal"] == "Transactions on Different Work"
    assert any("Could not abbreviate" in r.getMessage() for r in caplog.records)


ARXIV_BIB = "arxiv.bib"
# ID -> (arXiv ID, primary category) of the preprints in ARXIV_BIB
PREPRINTS = {"EprintStyle": ("2009.09852", "cs.IT"),
             "GoogleScholar": ("2101.00001", None),
             "WithCategory": ("2101.00002", "math.PR"),
             "Dblp": ("2101.00003", None),
             "Ads": ("2101.00004", "cs.LG"),
             "DataCite": ("2101.00005", None),
             "OldId": ("hep-th/9901001", None),
             "Biblatex": ("2101.00006", "eess.SP")}
NOT_PREPRINTS = ("Published", "Conference", "OtherArchive", "Website")
ARXIV_FIELDS = {"eprint", "archiveprefix", "primaryclass", "eprinttype",
                "eprintclass"}

def _arxiv_entries():
    entries = load_bib_file(ARXIV_BIB).get_entry_list()
    return {_entry["ID"]: _entry for _entry in entries}

def test_get_arxiv_preprint():
    found = {_key: modernize_bib_file.get_arxiv_preprint(_entry)
             for _key, _entry in _arxiv_entries().items()}
    assert found == {**PREPRINTS, **dict.fromkeys(NOT_PREPRINTS)}

@pytest.mark.parametrize("key", PREPRINTS)
def test_arxiv_journal_style(key):
    entry = modernize_bib_file.convert_arxiv_style(_arxiv_entries()[key],
                                                   "journal")
    assert entry[KEY_ENTRYTYPE] == "article"
    assert entry["journal"] == "arXiv preprint arXiv:" + PREPRINTS[key][0]
    assert not set(entry) & (ARXIV_FIELDS | {"publisher", "volume"})

@pytest.mark.parametrize("key", PREPRINTS)
def test_arxiv_eprint_style(key):
    entry = modernize_bib_file.convert_arxiv_style(_arxiv_entries()[key],
                                                   "eprint")
    arxiv_id, category = PREPRINTS[key]
    assert entry[KEY_ENTRYTYPE] == "misc"
    assert entry["eprint"] == arxiv_id and entry["archiveprefix"] == "arXiv"
    assert entry.get("primaryclass") == category
    assert not set(entry) & {"journal", "eprinttype", "eprintclass",
                             "publisher", "volume"}

@pytest.mark.parametrize("style", modernize_bib_file.ARXIV_STYLES)
def test_arxiv_style_keeps_other_entries(style):
    entries = _arxiv_entries()
    for _key in NOT_PREPRINTS:
        entry = dict(entries[_key])
        assert modernize_bib_file.convert_arxiv_style(entry, style) == entries[_key]

@pytest.mark.parametrize("style", modernize_bib_file.ARXIV_STYLES)
def test_arxiv_style_twice_is_the_same(style):
    for _entry in _arxiv_entries().values():
        once = modernize_bib_file.convert_arxiv_style(dict(_entry), style)
        assert modernize_bib_file.convert_arxiv_style(dict(once), style) == once

def test_arxiv_style_back_and_forth():
    entry = _arxiv_entries()["GoogleScholar"]
    converted = modernize_bib_file.convert_arxiv_style(dict(entry), "eprint")
    assert modernize_bib_file.convert_arxiv_style(converted, "journal") == entry

def test_arxiv_style_keeps_doi_and_url():
    entry = modernize_bib_file.convert_arxiv_style(
        _arxiv_entries()["DataCite"], "journal")
    assert entry["doi"] == "10.48550/ARXIV.2101.00005"
    assert entry["url"] == "https://arxiv.org/abs/2101.00005"

def test_arxiv_style_unknown():
    with pytest.raises(ValueError):
        modernize_bib_file.convert_arxiv_style({}, "other")

@pytest.mark.parametrize("style,categories",
                         [("eprint", {"GoogleScholar": "cs.IT",
                                      "Published": "cs.IT"}),
                          ("journal", {"GoogleScholar": None,
                                       "Published": "cs.IT"})])
def test_arxiv_style_with_category_lookup(style, categories):
    entries = _arxiv_entries()
    for _key, _category in categories.items():
        entry = modernize_bib_file.modernize_entry(
            entries[_key], arxiv=True, arxiv_style=style,
            arxiv_lookup=lambda eprint: "cs.IT")
        assert entry.get("primaryclass") == _category

def test_main_arxiv_style():
    entries = modernize_bib_file.modernize_bib_main(ARXIV_BIB,
                                                    arxiv_style="journal")
    journals = [_entry["journal"] for _entry in entries
                if _entry.get("journal", "").startswith("arXiv preprint")]
    assert len(journals) == len(PREPRINTS)

def test_iso4_keeps_arxiv_journal():
    entry = {"ID": "Key", "ENTRYTYPE": "article",
             "journal": "arXiv preprint arXiv:2101.00001"}
    result = modernize_bib_file.abbreviate_journalname(entry)
    assert result["journal"] == "arXiv preprint arXiv:2101.00001"

@pytest.mark.parametrize("eprint,expected",
                         [("arXiv:2009.09852", "2009.09852"),
                          ("arXiv: 2009.09852", "2009.09852"),
                          ("2009.09852", "2009.09852"),
                          ("arXiv:astro-ph/0601001", "astro-ph/0601001")])
def test_clean_eprint(eprint, expected):
    assert modernize_bib_file.clean_eprint(eprint) == expected
