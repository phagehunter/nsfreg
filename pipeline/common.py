#!/usr/bin/env python3
"""Shared helpers for the NSF restricted-entities extraction pipeline."""
import json
import os
import re

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Where the raw downloads live. The official publications are large, are
# re-published under changing file names, and several are PDFs, so they are not
# committed; sources/README.md says what each parser expects and where to get
# it. Point NSFREG_SOURCES at the folder holding "Appendix A - U.S. Proscribed
# Party Lists" to run the parsers from anywhere.
SOURCE_ROOT = Path(os.environ.get("NSFREG_SOURCES", ROOT / "sources")).expanduser()
BASE_DIR = SOURCE_ROOT / "Appendix A - U.S. Proscribed Party Lists"

# Parsers always write into this repository.
DATA_DIR = ROOT / "data"

EXTRACTED = "2026-07-09"


def source(*parts):
    """Resolve one raw source file, failing with the path that was expected."""
    path = BASE_DIR.joinpath(*parts)
    if not path.exists():
        raise SystemExit(
            f"missing raw source:\n  {path}\n"
            f"Set NSFREG_SOURCES to the folder that holds "
            f'"Appendix A - U.S. Proscribed Party Lists", or place the file at the '
            f"path above. See sources/README.md for where each file comes from."
        )
    return path


def normalize_typography(s):
    """Normalize Federal Register typographic characters."""
    s = s.replace("’", "'").replace("‘", "'")
    s = s.replace("“", '"').replace("”", '"')
    s = s.replace("''", '"')  # FR double-apostrophe quotes
    s = s.replace("‘‘", '"').replace("’’", '"')
    s = s.replace("–", "-")  # en dash
    return s


def collapse_ws(s):
    return re.sub(r"\s+", " ", s).strip()


def dehyphenate(s):
    """Fix PDF line-wrap hyphenation after lines are joined with spaces.

    "Tech- nology" -> "Technology" (continuation starts lowercase: wrap artifact)
    "TP- Link"     -> "TP-Link"    (continuation starts uppercase: real hyphen)
    """
    s = re.sub(r"(\w)-\s+(?=[a-z])", r"\1", s)
    s = re.sub(r"(\w)-\s+(?=[A-Z0-9])", r"\1-", s)
    return s


def clean_text(s):
    return dehyphenate(collapse_ws(normalize_typography(s)))


def entity_record(name, aliases=None, country=None, address=None,
                  effective_date=None, federal_register=None, notes=None):
    return {
        "name": name,
        "aliases": aliases or [],
        "country": country,
        "address": address,
        "status": None,
        "effective_date": effective_date,
        "federal_register": federal_register,
        "notes": notes,
    }


def write_output(list_id, source_file, entities, filename):
    out = {
        "list_id": list_id,
        "source_file": os.path.basename(source_file),
        "extracted": EXTRACTED,
        "count": len(entities),
        "entities": entities,
    }
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"Wrote {len(entities)} entities -> {path}")
    return path


def truncate_note(s, limit=250):
    s = collapse_ws(s)
    if len(s) <= limit:
        return s
    cut = s.rfind(" ", 0, limit)
    if cut < limit - 40:
        cut = limit
    return s[:cut].rstrip(" ,;") + "..."
