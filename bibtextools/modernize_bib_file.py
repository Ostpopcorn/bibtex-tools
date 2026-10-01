"""The `modernize` command, which cleans the fields, writes arXiv preprints
in one style, and abbreviates journal names. The steps are in `core`."""
import logging

from .util import load_bib_file, write_bib_database, getnames
from .const import (KEY_ARCHIVE, KEY_AUTHOR, KEY_CATEGORY, KEY_EPRINT, KEY_ID,
                    KEY_MONTH, KEY_PAGES, KEY_TITLE, KEY_YEAR, KEYS_JOURNAL,
                    KEY_ENTRYTYPE, KEY_BOOKTITLE)
# The steps moved to `core`, and their names are kept here for older code
from .clean_bib_file import has_duplicates, replace_duplicate_ids, remove_duplicate_entries
from .core.arxiv import (ARXIV_EPRINT, ARXIV_JOURNAL, ARXIV_JOURNAL_FORMAT,
                         ARXIV_STYLES, add_arxiv_category, convert_arxiv_style,
                         get_arxiv_category, get_arxiv_preprint,
                         match_arxiv_venue as _match_arxiv_venue)
from .core.fields import (FIELD_CLEANERS, clean_author, clean_eprint,
                          clean_fields as _clean_fields, clean_month,
                          clean_pages, remove_fields as _remove_fields)
from .core.journals import (abbreviate_journalname, abbreviate_name,
                            get_abbreviator)
from .core.keys import generate_key as replace_bib_id, generate_key_in_entry
from .core.titles import (TITLE_ACRONYMS, TITLE_WHOLE, protect_title,
                          protect_title_in_entry)


def clean_title(title, shield_title=False, **kwargs):
    """Put braces around the acronyms of a title, or around the whole title
    with `shield_title`."""
    return protect_title(title, TITLE_WHOLE if shield_title else TITLE_ACRONYMS)

#: Fields that `modernize` cleans: the title gets braces around its acronyms
CLEAN_FUNC = {**FIELD_CLEANERS, KEY_TITLE: clean_title}

def modernize_entry(entry, remove_fields=(), replace_ids=False, arxiv=False,
                    iso4=False, clean_fields=None, arxiv_lookup=None,
                    arxiv_style=None, shield_title=False):
    """Modernize a single entry, which is changed in place. Only the fields
    in `clean_fields` are cleaned with `CLEAN_FUNC` (default: all of them),
    and the title gets braces around its acronyms, or around the whole title
    with `shield_title`. arXiv preprints are written in `arxiv_style`, one
    of `ARXIV_STYLES` (default: as they are). `arxiv_lookup` returns the
    primary category of an arXiv eprint (default: `get_arxiv_category`,
    which downloads it)."""
    logger = logging.getLogger('modernize_bib_file')
    if clean_fields is None:
        clean_fields = tuple(CLEAN_FUNC)
    logger.debug("Cleaning fields: %s", ", ".join(clean_fields))
    _clean_fields(entry, clean_fields)
    if KEY_TITLE in clean_fields:
        protect_title_in_entry(entry, TITLE_WHOLE if shield_title
                               else TITLE_ACRONYMS)
    if arxiv_style is not None:
        logger.debug("Writing arXiv preprints in the %s style", arxiv_style)
        convert_arxiv_style(entry, arxiv_style)
    if arxiv:
        logger.debug("Retrieving arXiv primary category")
        add_arxiv_category(entry, arxiv_lookup or get_arxiv_category)
    logger.debug("Removing fields: %s", ", ".join(remove_fields))
    _remove_fields(entry, remove_fields)
    if replace_ids:
        logger.debug("Replacing bib ID")
        generate_key_in_entry(entry)
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
