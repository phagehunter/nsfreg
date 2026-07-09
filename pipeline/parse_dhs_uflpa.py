#!/usr/bin/env python3
"""Parse the DHS UFLPA Entity List saved HTML page into data/dhs_uflpa.json.

Source: browser-saved "Webpage, Complete" copy of
https://www.dhs.gov/uflpa-entity-list

NOTE (2026-07-09): the saved main HTML file in Appendix A is 0 bytes — the
browser save captured only supporting resources (CSS/JS/images) and empty
tracker stubs, not the page document itself. This script therefore refuses to
run against that file and exits non-zero with a diagnostic. Re-save the page
(or drop a valid copy at SOURCE) and re-run; the parsing logic below targets
the DHS page structure: UFLPA category section headings (h2/h3/h4) followed
by tables or bullet lists of entity names.

Uses stdlib only (html.parser) — BeautifulSoup is not installed.
"""
import html
import json
import os
import re
import sys
from html.parser import HTMLParser

SOURCE = (
    "/Users/curtishoffmann/Desktop/Desktop/Datasets/nsf-prohibitions-july-2026/"
    "Appendix A - U.S. Proscribed Party Lists/"
    "U.S. Department of Homeland Security/UFLPA Entity List/"
    "UFLPA Entity List _ Homeland Security.html"
)
OUT = (
    "/Users/curtishoffmann/Desktop/Desktop/Datasets/nsf-prohibitions-july-2026/"
    "2026-07-09-nsf-restricted-entities-site/data/dhs_uflpa.json"
)

# Phrases that identify the four UFLPA list-category section headings
CATEGORY_MARKERS = (
    "mine, produce, or manufacture",
    "working with the government of Xinjiang",
    "labor transfer",
    "exported products",
    "source material",
    "poverty alleviation",
    "pairing assistance",
)


def clean(s):
    s = html.unescape(s)
    s = s.replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip()


class ContentParser(HTMLParser):
    """Walk the document collecting (heading, items) sections.

    Headings are h2-h5 text; items are the text of <li> elements and of the
    first cell of table rows encountered under the current heading.
    """

    HEADINGS = ("h2", "h3", "h4", "h5")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sections = []  # list of [heading_text, [item_text, ...]]
        self._head_tag = None
        self._buf = None
        self._item_depth = 0  # inside li or td
        self._cell_index = None
        self._in_tr = False

    def _current(self):
        if not self.sections:
            self.sections.append(["", []])
        return self.sections[-1]

    def handle_starttag(self, tag, attrs):
        if tag in self.HEADINGS:
            self._head_tag = tag
            self._buf = []
        elif tag == "tr":
            self._in_tr = True
            self._cell_index = -1
        elif tag == "td" and self._in_tr:
            self._cell_index += 1
            if self._cell_index == 0:
                self._item_depth += 1
                self._buf = []
        elif tag == "li":
            self._item_depth += 1
            self._buf = []

    def handle_endtag(self, tag):
        if tag in self.HEADINGS and self._head_tag == tag:
            text = clean("".join(self._buf or []))
            self._head_tag = None
            self._buf = None
            if text:
                self.sections.append([text, []])
        elif tag == "tr":
            self._in_tr = False
        elif tag in ("li", "td") and self._item_depth > 0:
            if tag == "td" and (not self._in_tr or self._cell_index != 0):
                return
            self._item_depth -= 1
            text = clean("".join(self._buf or []))
            self._buf = None
            if text:
                self._current()[1].append(text)

    def handle_data(self, data):
        if self._buf is not None:
            self._buf.append(data)


ALIAS_RE = re.compile(
    r"\s*[;(,]?\s*(?:\ba/k/a\b|\baka\b|\balso known as\b|\bformerly known as\b|"
    r"\bf/k/a\b|\bfka\b)[.:]?\s*",
    re.IGNORECASE,
)
SUBSIDIARY_RE = re.compile(
    r"\s*[,;(]?\s*including\s+(?:its\s+|their\s+)?.*?subsidiar.*$",
    re.IGNORECASE,
)


def split_entity(raw):
    """Return (name, aliases, extra_note) from one raw list/table item."""
    extra = None
    m = SUBSIDIARY_RE.search(raw)
    if m:
        extra = clean(m.group(0).lstrip(",;( ").rstrip(")"))
        raw = raw[: m.start()]
    parts = ALIAS_RE.split(raw)
    name = clean(parts[0]).rstrip(";,")
    aliases = []
    for p in parts[1:]:
        for piece in re.split(r"\s*[;]\s*|\s+and\s+", p):
            piece = clean(piece).strip("()").rstrip(";,.")
            if piece:
                aliases.append(piece)
    if not name:  # alias split ate everything — keep verbatim
        return clean(raw), [], extra
    return name, aliases, extra


def looks_like_entity(text):
    """Filter out navigation/boilerplate list items."""
    if len(text) < 4 or len(text) > 300:
        return False
    bad = ("Skip to", "How Do I", "Sign up", "Subscribe", "Privacy",
           "FOIA", "Accessibility", "Site Links", "dhs.gov", "http")
    return not any(b.lower() in text.lower() for b in bad)


def main():
    size = os.path.getsize(SOURCE) if os.path.exists(SOURCE) else -1
    if size <= 0:
        sys.stderr.write(
            "ERROR: UFLPA source HTML is missing or empty (%d bytes):\n  %s\n"
            "The 'Webpage, Complete' save failed to capture the document body\n"
            "(only CSS/JS/tracker stubs were saved). No output written.\n"
            "Re-save https://www.dhs.gov/uflpa-entity-list and re-run.\n" % (size, SOURCE)
        )
        return 1

    with open(SOURCE, encoding="utf-8", errors="replace") as f:
        raw = f.read()
    p = ContentParser()
    p.feed(raw)

    # Keep only sections whose heading matches a UFLPA category marker;
    # fall back to any section with >=3 plausible entity items.
    merged = {}
    order = []
    for heading, items in p.sections:
        is_cat = any(m.lower() in heading.lower() for m in CATEGORY_MARKERS)
        good = [it for it in items if looks_like_entity(it)]
        if not (is_cat or len(good) >= 3):
            continue
        if not is_cat and not any(
            k in heading.lower() for k in ("entit", "list", "xinjiang", "uflpa")
        ):
            continue
        for it in good:
            name, aliases, extra = split_entity(it)
            note_bits = ["UFLPA category: " + heading] if heading else []
            if extra:
                note_bits.append(extra)
            key = name.lower()
            if key in merged:
                e = merged[key]
                for a in aliases:
                    if a not in e["aliases"]:
                        e["aliases"].append(a)
                for nb in note_bits:
                    if nb not in (e["notes"] or ""):
                        e["notes"] = ((e["notes"] + " | ") if e["notes"] else "") + nb
            else:
                merged[key] = {
                    "name": name,
                    "aliases": aliases,
                    "country": "China",
                    "address": None,
                    "status": None,
                    "effective_date": None,
                    "federal_register": None,
                    "notes": " | ".join(note_bits) or None,
                }
                order.append(key)

    entities = [merged[k] for k in order]
    if not entities:
        sys.stderr.write("ERROR: no entities extracted — page structure not "
                         "recognized. No output written.\n")
        return 1

    out = {
        "list_id": "dhs-uflpa",
        "source_file": os.path.basename(SOURCE),
        "extracted": "2026-07-09",
        "count": len(entities),
        "entities": entities,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("Wrote %d entities -> %s" % (len(entities), OUT))
    for e in entities[:5]:
        print(" sample:", e["name"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
