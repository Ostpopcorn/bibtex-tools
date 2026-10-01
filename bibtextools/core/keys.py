"""Generate keys from the entries and rename duplicate keys."""
import re

from bibtexparser.customization import string_to_latex

from ..const import KEY_AUTHOR, KEY_ID, KEY_TITLE, KEY_YEAR
from ..util import getnames


def _remove_unwanted_characters(string):
    return re.sub(r'[{}]|(\\.)', '', string)

def generate_key(entry):
    """Return a key of the last name of the first author, the year, and the
    first word of the title, e.g., `Shannon1948mathematical`. Entries
    without an author, year, or title keep their key."""
    author = entry.get(KEY_AUTHOR)
    year = entry.get(KEY_YEAR)
    title = entry.get(KEY_TITLE)
    if (author is None) or (year is None) or (title is None):
        return entry.get(KEY_ID)
    first_author = author.replace("\n", " ").split(" and ")[0]
    # The last name also if the names are written as "First Last"
    last_name = (getnames([first_author]) or [first_author])[0].split(",")[0]
    first_word = re.findall(r"[\w]{3,}", title)
    first_word = next((k.lower() for k in first_word if (k.lower() not in ["the"])), "")
    new_id = "{}{}{}".format(last_name, year, first_word)
    new_id = string_to_latex(new_id)
    new_id = _remove_unwanted_characters(new_id)
    new_id = new_id.replace(" ", "")
    return new_id

def generate_key_in_entry(entry):
    """Replace the key of an entry with `generate_key`."""
    entry[KEY_ID] = generate_key(entry)
    return entry

def get_duplicate_keys(entries):
    """Return the keys that more than one entry has."""
    list_ids = [x[KEY_ID] for x in entries]
    return set([x for x in list_ids if list_ids.count(x) > 1])

def rename_duplicate_keys(entries):
    """Rename entries with the same key to `key:b`, `key:c`, and so on. The
    first entry keeps its key, since BibTeX and biber also use the first
    entry of a key. The entries are changed in place. Returns them and the
    renamed keys with their number of entries."""
    duplicates = {k: 0 for k in get_duplicate_keys(entries)}
    used_ids = set([x[KEY_ID] for x in entries])
    for entry in entries:
        _id = entry[KEY_ID]
        if _id in duplicates:
            duplicates[_id] += 1
            if duplicates[_id] == 1:
                continue
            _letter = ord('`') + duplicates[_id]
            while "{}:{}".format(_id, chr(_letter)) in used_ids:
                _letter += 1
            _id = "{}:{}".format(_id, chr(_letter))
            used_ids.add(_id)
            entry[KEY_ID] = _id
    return entries, duplicates
