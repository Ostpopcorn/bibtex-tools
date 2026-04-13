import logging
import re

from .const import KEY_ID
from .util import load_bib_file


def get_bbl_keys(bbl_file, encoding="utf-8"):
    """Extract citation keys from a .bbl file, auto-detecting the backend."""
    with open(bbl_file, encoding=encoding) as _bbl_file:
        content = _bbl_file.read()
    biblatex_keys = set(re.findall(r"\\entry\{([^}]+)\}", content))
    bibtex_keys = set(re.findall(r"\\bibitem(?:\[.*?\])?\{([^}]+)\}", content))
    if biblatex_keys and not bibtex_keys:
        return biblatex_keys, "biblatex"
    if bibtex_keys and not biblatex_keys:
        return bibtex_keys, "bibtex"
    return biblatex_keys | bibtex_keys, "unknown"


def filter_cited_main(bib_file, bbl_file, verbose=logging.WARN, encoding="utf-8"):
    logging.basicConfig(format="%(asctime)s - [%(levelname)8s]: %(message)s")
    logger = logging.getLogger("filter_cited")
    logger.setLevel(verbose)
    logger.info("Filtering entries of %s using citations from %s", bib_file, bbl_file)
    bib_database = load_bib_file(bib_file, abbr=None, encoding=encoding)
    entries = bib_database.get_entry_list()
    cited_keys, backend = get_bbl_keys(bbl_file, encoding=encoding)
    logger.info("Detected bbl backend: %s", backend)
    logger.info("Found %d cited keys in bbl file", len(cited_keys))
    bib_ids = set(entry.get(KEY_ID) for entry in entries)
    kept = [entry for entry in entries if entry.get(KEY_ID) in cited_keys]
    unused = bib_ids - cited_keys
    missing = cited_keys - bib_ids
    logger.info("Keeping %d of %d entries", len(kept), len(entries))
    if unused:
        logger.info("Dropping %d uncited entries: %s",
                    len(unused), ", ".join(sorted(unused)))
    if missing:
        logger.warning("%d cited keys are not present in the bib file: %s",
                       len(missing), ", ".join(sorted(missing)))
    return kept
