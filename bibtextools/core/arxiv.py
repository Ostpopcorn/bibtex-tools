"""Write arXiv preprints in one style and add their categories."""
import re

from ..const import (KEY_ARCHIVE, KEY_CATEGORY, KEY_DOI, KEY_ENTRYTYPE,
                     KEY_EPRINT, KEY_EPRINTCLASS, KEY_EPRINTTYPE,
                     KEY_HOWPUBLISHED, KEY_JOURNAL, KEY_PUBLISHER, KEY_URL,
                     KEY_VOLUME, KEYS_JOURNAL)

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

def match_arxiv_venue(value):
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
        _match = match_arxiv_venue(_value)
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
        if _key in entry and match_arxiv_venue(entry[_key]):
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

def add_arxiv_category(entry, lookup=get_arxiv_category):
    """Add the primary category of the arXiv eprint of an entry, e.g.,
    cs.IT, if it has none. `lookup(eprint)` returns the category, or None
    if it is not known. By default, it is downloaded from arXiv."""
    eprint = entry.get(KEY_EPRINT)
    if eprint is not None and entry.get(KEY_CATEGORY) is None:
        category = lookup(eprint)
        if category is not None:
            entry[KEY_ARCHIVE] = "arXiv"
            entry[KEY_CATEGORY] = category
    return entry
