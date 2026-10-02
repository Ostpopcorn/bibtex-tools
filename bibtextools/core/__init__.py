"""The steps of bibtextools as independent functions, which the pipeline of
the web app and the commands share. Each function does one thing and takes
only its own settings:

- `fields`: clean the values of fields, e.g., pages and months, and remove
  fields
- `titles`: protect titles with braces
- `arxiv`: write arXiv preprints in one style and add their categories
- `journals`: abbreviate journal names with ISO 4
- `latex`: replace unicode characters with LaTeX
- `keys`: generate keys and rename duplicate keys
- `duplicates`: find duplicate entries
- `cited`: keep the entries that a .bbl file cites
- `formats`: convert between the fields and entry types of BibTeX and
  biblatex

The functions on an entry change it in place and return it, except
`journals.abbreviate_journalname`, which returns a copy.
"""
