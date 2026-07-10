#!/usr/bin/env python3
"""Shared helpers for the NSF restricted-entities extraction pipeline."""
import json
import os
import re

BASE_DIR = ("../../"
            "nsf-prohibitions-july-2026/Appendix A - U.S. Proscribed Party Lists")
DATA_DIR = ("../../"
            "nsf-prohibitions-july-2026/2026-07-09-nsf-restricted-entities-site/data")

EXTRACTED = "2026-07-09"


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
