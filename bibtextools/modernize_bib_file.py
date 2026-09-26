import functools
import logging
import re

from bibtexparser.customization import string_to_latex#, getnames
from pyiso4 import ltwa
from pyiso4.ltwa import Abbreviate

from .util import load_bib_file, write_bib_database, getnames
from .const import (KEY_ARCHIVE, KEY_AUTHOR, KEY_CATEGORY, KEY_EPRINT, KEY_ID,
                    KEY_MONTH, KEY_PAGES, KEY_TITLE, KEY_YEAR, KEYS_JOURNAL,
                    KEY_ENTRYTYPE, KEY_BOOKTITLE, KEY_DOI, KEY_EPRINTCLASS,
                    KEY_EPRINTTYPE, KEY_HOWPUBLISHED, KEY_JOURNAL,
                    KEY_PUBLISHER, KEY_URL, KEY_VOLUME)
from .clean_bib_file import has_duplicates, replace_duplicate_ids, remove_duplicate_entries


def clean_month(month, **kwargs):
    _month_str = str(month).lower()
    _month_str = _month_str.strip(".")
    MONTH_DICT = {"jan": "1",
                  "january": "1",
                  "1": "1",
                  "feb": "2",
                  "february": "2",
                  "2": "2",
                  "mar": "3",
                  "march": "3",
                  "3": "3",
                  "apr": "4",
                  "april": "4",
                  "4": "4",
                  "may": "5",
                  "5": "5",
                  "jun": "6",
                  "june": "6",
                  "6": "6",
                  "jul": "7",
                  "july": "7",
                  "7": "7",
                  "aug": "8",
                  "august": "8",
                  "8": "8",
                  "sep": "9",
                  "september": "9",
                  "9": "9",
                  "oct": "10",
                  "october": "10",
                  "10": "10",
                  "nov": "11",
                  "november": "11",
                  "11": "11",
                  "dec": "12",
                  "december": "12",
                  "12": "12",
                 }
    return MONTH_DICT.get(_month_str, month)

def clean_pages(pages, **kwargs):
    _split = pages.split("-")
    if "" in _split:
        _split.remove("") # remove empty entries in case '--' was already used
    return "--".join(_split)

def clean_eprint(eprint, **kwargs):
    """Remove the prefix "arXiv:" from an eprint."""
    return re.sub(r"^\s*arxiv\s*:\s*", "", eprint, flags=re.IGNORECASE)


def __surrounded_by_curly(title):
    return title.startswith(r"{") and title.endswith(r"}")

def clean_title(title, shield_title=False, **kwargs):
    _shielded = re.sub(r'([0-9A-Z]+\b)|([a-zA-Z]+[A-Z0-9]+[a-zA-Z\b]*)|(\$[\w\\+-=]*\$)', r'{\g<0>}', title)
    _shielded = re.sub(r'\{{2}((?:\{??[^\{]*?))\}{2}', r'{\g<1>}', _shielded)
    _re_inner_acro = r'\{((?:\{??[^\{]*?))\}'
    __without_inner = re.sub(_re_inner_acro, r"\g<1>", _shielded)
    __remove_curly_w_acros = __surrounded_by_curly(__without_inner)
    __remove_curly_wo_acros = (len(re.findall(_re_inner_acro, _shielded)) == 1) and __surrounded_by_curly(title)
    if __remove_curly_w_acros or __remove_curly_wo_acros:
        _shielded = _shielded[1:-1]
    if shield_title:
        _shielded = r'{' + _shielded + r'}'
    return _shielded

def clean_author(author, **kwargs):
    _names = getnames([i.strip() for i in author.replace('\n', ' ').split(" and ")])
    return " and ".join(_names)

CLEAN_FUNC = {KEY_PAGES: clean_pages,
              KEY_MONTH: clean_month,
              KEY_EPRINT: clean_eprint,
              KEY_TITLE: clean_title,
              KEY_AUTHOR: clean_author}


def _remove_unwanted_characters(string):
    return re.sub(r'[{}]|(\\.)', '', string)

def replace_bib_id(entry):
    author = entry.get(KEY_AUTHOR)
    year = entry.get(KEY_YEAR)
    title = entry.get(KEY_TITLE)
    if (author is None) or (year is None) or (title is None):
        return entry.get(KEY_ID)
    first_author = author.split(" and ")[0]
    last_name = first_author.split(",")[0]
    #last_name = last_name.replace(" ", "")
    #first_word = re.findall(r"[\w']+", title)[0]  # this gives "a" as first word
    first_word = re.findall(r"[\w]{3,}", title)
    first_word = next((k.lower() for k in first_word if (k.lower() not in ["the"])), "")
    new_id = "{}{}{}".format(last_name, year, first_word)
    new_id = string_to_latex(new_id)
    new_id = _remove_unwanted_characters(new_id)
    new_id = new_id.replace(" ", "")
    return new_id

#: Styles of arXiv preprints: as @misc with the ID in the eprint field, like
#: arXiv exports them, or as @article with the ID in the journal field, like
#: Google Scholar exports them
ARXIV_EPRINT = "eprint"
ARXIV_JOURNAL = "journal"
ARXIV_STYLES = (ARXIV_EPRINT, ARXIV_JOURNAL)
ARXIV_JOURNAL_FORMAT = "arXiv preprint arXiv:{}"

# IDs of arXiv preprints, e.g., 2009.09852, 2009.09852v2, and hep-th/9901001
_ARXIV_ID = r"(?:\d{4}\.\d{4,5}|[a-z]+(?:-[a-z]+)*(?:\.[a-z]{2})?/\d{7})(?:v\d+)?"
# arXiv as the venue of a preprint, e.g., "arXiv preprint arXiv:2009.09852",
# "arXiv e-prints", "arXiv:2009.09852 [cs.IT]", and "CoRR" (DBLP)
_ARXIV_VENUE = re.compile(
    r"(?:arxiv|corr)(?:\s+(?:preprint|e-?prints?))*"
    r"(?:\s*[:,]?\s*(?:arxiv\s*:\s*|abs/)?(?P<id>{}))?"
    r"(?:\s*\[(?P<category>[^\]]+)\])?\.?".format(_ARXIV_ID), re.IGNORECASE)
# Fields that can name arXiv as the venue of a preprint
_ARXIV_VENUE_FIELDS = (*KEYS_JOURNAL, KEY_HOWPUBLISHED, KEY_PUBLISHER)
# Other ways to find the ID: field -> pattern with the ID as group
_ARXIV_ID_FIELDS = (
    (KEY_VOLUME, re.compile(r"abs/({})".format(_ARXIV_ID), re.IGNORECASE)),
    (KEY_DOI, re.compile(r"10\.48550/arxiv\.({})".format(_ARXIV_ID),
                         re.IGNORECASE)),
    (KEY_URL, re.compile(r"https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/({})"
                         r"(?:\.pdf)?/?".format(_ARXIV_ID), re.IGNORECASE)),
)
# Entry types of preprints. Others, e.g., theses, are kept as they are.
_PREPRINT_TYPES = ("article", "misc", "unpublished", "online", "electronic",
                   "preprint", "www")

def _match_arxiv_venue(value):
    """Match a venue, e.g., a journal, if it is arXiv."""
    return _ARXIV_VENUE.fullmatch(" ".join(re.sub(r"[{}]", "", value).split()))

def get_arxiv_preprint(entry):
    """Return the ID and the primary category (or None) if the entry is an
    arXiv preprint, i.e., it is not published elsewhere, and None otherwise.
    Preprints have an arXiv eprint, e.g., as arXiv exports them, or arXiv as
    their journal, e.g., as Google Scholar and DBLP export them."""
    if entry.get(KEY_ENTRYTYPE, "").lower() not in _PREPRINT_TYPES:
        return None
    venue_id = category = None
    arxiv_venue = False
    for _key in _ARXIV_VENUE_FIELDS:
        _value = entry.get(_key)
        if _value is None:
            continue
        _match = _match_arxiv_venue(_value)
        if _match:
            arxiv_venue = True
            venue_id = venue_id or _match["id"]
            category = category or _match["category"]
        elif _key in KEYS_JOURNAL:
            return None  # published in a journal
    eprint_id = None
    eprint = entry.get(KEY_EPRINT)
    archive = entry.get(KEY_ARCHIVE, entry.get(KEY_EPRINTTYPE, ""))
    if eprint is not None and archive.strip().lower() in ("", "arxiv"):
        _match = re.fullmatch(r"(?:arxiv\s*:\s*)?({})".format(_ARXIV_ID),
                              eprint.strip(), re.IGNORECASE)
        eprint_id = _match and _match[1]
    if not arxiv_venue and not eprint_id:
        return None
    arxiv_id = eprint_id or venue_id
    for _key, _pattern in _ARXIV_ID_FIELDS:
        if arxiv_id:
            break
        _match = _pattern.fullmatch(entry.get(_key, "").strip())
        arxiv_id = _match and _match[1]
    if not arxiv_id:
        return None
    category = entry.get(KEY_CATEGORY, entry.get(KEY_EPRINTCLASS, category))
    return arxiv_id, category

def convert_arxiv_style(entry, style):
    """Write an arXiv preprint in a style of `ARXIV_STYLES`, e.g., as
    @article with "arXiv preprint arXiv:2009.09852" as journal. The entry is
    changed in place. Other entries, e.g., published ones with an eprint, are
    not changed."""
    if style not in ARXIV_STYLES:
        raise ValueError("Unknown style of arXiv preprints: {}".format(style))
    preprint = get_arxiv_preprint(entry)
    if preprint is None:
        return entry
    arxiv_id, category = preprint
    for _key in _ARXIV_VENUE_FIELDS:
        if _key in entry and _match_arxiv_venue(entry[_key]):
            del entry[_key]
    if re.fullmatch(r"abs/.*", entry.get(KEY_VOLUME, "").strip()):
        del entry[KEY_VOLUME]
    for _key in (KEY_EPRINT, KEY_ARCHIVE, KEY_EPRINTTYPE, KEY_CATEGORY,
                 KEY_EPRINTCLASS):
        entry.pop(_key, None)
    if style == ARXIV_EPRINT:
        entry[KEY_ENTRYTYPE] = "misc"
        entry[KEY_EPRINT] = arxiv_id
        entry[KEY_ARCHIVE] = "arXiv"
        if category:
            entry[KEY_CATEGORY] = category
    else:
        entry[KEY_ENTRYTYPE] = "article"
        entry[KEY_JOURNAL] = ARXIV_JOURNAL_FORMAT.format(arxiv_id)
    return entry

def get_arxiv_category(eprint):
    import feedparser  # only needed here, not available in the web app
    base_url = 'http://export.arxiv.org/api/query?'
    search_query = {'id_list': eprint,}
    query = "&".join(["{}={}".format(k, v) for k, v in search_query.items()])
    feed = feedparser.parse(base_url + query)
    entries = feed['entries']
    if len(entries) != 1:
        return None
    #a_id = entries[0]["id"].split('/abs/')[-1]
    try:
        primary_class = entries[0]['arxiv_primary_category']['term']
    except KeyError:
        return None
    if primary_class == "":
        return None
    else:
        return primary_class

def _open_utf8(file, mode="r", *args, **kwargs):
    if "b" not in mode:
        kwargs.setdefault("encoding", "utf-8")
    return open(file, mode, *args, **kwargs)

@functools.lru_cache(maxsize=None)
def get_abbreviator():
    """Load the ISO4 abbreviation list (LTWA) once, since this takes about a
    second. pyiso4 opens its UTF-8 data files with the default encoding,
    which fails on Windows (cp1252), so its open() is made to use UTF-8."""
    ltwa.open = _open_utf8
    try:
        return Abbreviate.create()
    finally:
        del ltwa.open

def abbreviate_name(name):
    """Abbreviate a journal or conference name according to ISO4. Names that
    pyiso4 fails on are kept, e.g., "Transactions on Different Work"."""
    try:
        return get_abbreviator()(name)
    except Exception:
        logging.getLogger('modernize_bib_file').warning(
            "Could not abbreviate %r, so it is kept", name)
        return name

def abbreviate_journalname(entry):
    entry = entry.copy()
    if entry[KEY_ENTRYTYPE] == "inproceedings":
        conf = entry.get(KEY_BOOKTITLE, False)
        if conf:
            entry[KEY_BOOKTITLE] = abbreviate_name(conf)
    for _key in KEYS_JOURNAL:
        journal = entry.get(_key, False)
        if not journal or _match_arxiv_venue(journal):
            continue
        entry[_key] = abbreviate_name(journal)
    return entry

def modernize_entry(entry, remove_fields=(), replace_ids=False, arxiv=False,
                    iso4=False, clean_fields=None, arxiv_lookup=None,
                    arxiv_style=None, **kwargs):
    """Modernize a single entry, which is changed in place. Only the fields
    in `clean_fields` are cleaned with `CLEAN_FUNC` (default: all of them).
    arXiv preprints are written in `arxiv_style`, one of `ARXIV_STYLES`
    (default: as they are). `arxiv_lookup` returns the primary category of
    an arXiv eprint (default: `get_arxiv_category`, which downloads it)."""
    logger = logging.getLogger('modernize_bib_file')
    if arxiv_lookup is None:
        arxiv_lookup = get_arxiv_category
    for _key, _clean_func in CLEAN_FUNC.items():
        if clean_fields is not None and _key not in clean_fields:
            continue
        _value = entry.get(_key)
        if _value is not None:
            logger.debug("Cleaning field: %s", _key)
            entry[_key] = _clean_func(_value, **kwargs)
    if arxiv_style is not None:
        logger.debug("Writing arXiv preprints in the %s style", arxiv_style)
        convert_arxiv_style(entry, arxiv_style)
    if arxiv:
        eprint = entry.get(KEY_EPRINT)
        primary_class = entry.get(KEY_CATEGORY)
        if (eprint is not None) and (primary_class is None):
            logging.debug("Retrieving arXiv primary category")
            _primary_class = arxiv_lookup(eprint)
            if _primary_class is not None:
                entry[KEY_ARCHIVE] = "arXiv"
                entry[KEY_CATEGORY] = _primary_class
                logging.debug("Primary category successfully changed to: %s", _primary_class)
    for _field in remove_fields:
        logger.debug("Removing field: %s", _field)
        entry.pop(_field, None)
    if replace_ids:
        logger.debug("Replacing bib ID")
        entry[KEY_ID] = replace_bib_id(entry)
    if iso4:
        entry = abbreviate_journalname(entry)
    return entry

def modernize_bib_main(bib_file, remove_fields=None, replace_ids=False,
                       remove_duplicates=False, interactive=False,
                       arxiv=False, iso4=False, arxiv_style=None,
                       verbose=logging.WARN, encoding='utf-8', **kwargs):
    logging.basicConfig(format="%(asctime)s - [%(levelname)8s]: %(message)s")
    logger = logging.getLogger('modernize_bib_file')
    logger.setLevel(verbose)
    logger.info("Modernizing bib file: %s", bib_file)

    if remove_fields is None:
        remove_fields = []
    logger.info("Fields to remove: {}".format(remove_fields))

    bib_database = load_bib_file(bib_file, encoding=encoding).get_entry_list()
    logger.debug("Successfully loaded bib file")
    if remove_duplicates or interactive:
        bib_database = remove_duplicate_entries(bib_database,
                                                interactive=interactive,
                                                verbose=verbose)
        logger.debug("Successfully removed duplicates")
    #if has_duplicates(bib_database):
    #    logger.warning("The loaded bib-file has duplicates (same ID for multiple entries). Consider running this script with the --replace_ids option to get automatically rename them.")

    _clean_entries = []
    for entry in bib_database:
        logger.info("Working on entry: %s", entry.get(KEY_ID))
        entry = modernize_entry(entry, remove_fields=remove_fields,
                                replace_ids=replace_ids, arxiv=arxiv,
                                iso4=iso4, arxiv_style=arxiv_style, **kwargs)
        _clean_entries.append(entry)
    if replace_ids:
        _clean_entries = replace_duplicate_ids(_clean_entries)
    return _clean_entries
