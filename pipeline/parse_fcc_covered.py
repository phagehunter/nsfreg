#!/usr/bin/env python3
"""Parse the FCC Covered List (Secure Networks Act Section 2) saved HTML page
into data/fcc_covered.json.

Source: browser-saved "Webpage, Complete" copy of
https://www.fcc.gov/supplychain/coveredlist
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
    "U.S. Federal Communications Commission/"
    "Equipment and Services Covered by Section 2 of The Secure Networks Act/"
    "List of Equipment and Services Covered By Section 2 of The Secure Networks Act _ "
    "Federal Communications Commission.html"
)
OUT = (
    "/Users/curtishoffmann/Desktop/Desktop/Datasets/nsf-prohibitions-july-2026/"
    "2026-07-09-nsf-restricted-entities-site/data/fcc_covered.json"
)


class TableParser(HTMLParser):
    """Extract rows from the first <table>; each cell keeps plain text plus the
    list of <strong> spans (entity names)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_table = False
        self.table_done = False
        self.in_cell = False
        self.in_strong = False
        self.rows = []
        self.row = None
        self.cell_text = []
        self.cell_strongs = []
        self.strong_text = []

    def handle_starttag(self, tag, attrs):
        if self.table_done:
            return
        if tag == "table":
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.row = []
        elif self.in_table and tag in ("td", "th"):
            self.in_cell = True
            self.cell_text = []
            self.cell_strongs = []
        elif self.in_cell and tag == "strong":
            self.in_strong = True
            self.strong_text = []
        elif self.in_cell and tag in ("br", "p"):
            self.cell_text.append(" ")

    def handle_endtag(self, tag):
        if self.table_done:
            return
        if tag == "table" and self.in_table:
            self.in_table = False
            self.table_done = True
        elif tag == "strong" and self.in_strong:
            self.in_strong = False
            s = clean("".join(self.strong_text))
            if s:
                self.cell_strongs.append(s)
        elif tag in ("td", "th") and self.in_cell:
            self.in_cell = False
            if self.row is not None:
                self.row.append(
                    {"text": clean("".join(self.cell_text)),
                     "strongs": self.cell_strongs}
                )
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.in_cell:
            self.cell_text.append(data)
            if self.in_strong:
                self.strong_text.append(data)


def clean(s):
    s = html.unescape(s)
    s = s.replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip()


DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+(\d{1,2}),\s*(\d{4})"
)
MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"])}


def iso_date(text):
    """First date in the cell as YYYY-MM-DD, or None."""
    m = DATE_RE.search(text)
    if not m:
        return None
    return "%04d-%02d-%02d" % (int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))


CHINA_MARKERS = (
    "Huawei", "ZTE", "Hytera", "Hikvision", "Dahua", "China Mobile",
    "China Telecom", "China Unicom", "Pacific Networks", "ComNet",
)


def derive_country(name):
    """Only assign a country when the company is recognizably attributable."""
    if "Kaspersky" in name:
        return "Russia"
    if any(m in name for m in CHINA_MARKERS):
        return "China"
    return None


def truncate(s, n=250):
    if len(s) <= n:
        return s
    return s[: n - 1].rsplit(" ", 1)[0] + "…"


def main():
    with open(SOURCE, encoding="utf-8", errors="replace") as f:
        raw = f.read()
    p = TableParser()
    p.feed(raw)

    entities = []
    for row in p.rows:
        if len(row) < 2 or not row[0]["text"]:
            continue
        desc_cell, date_cell = row[0], row[1]
        desc = desc_cell["text"]
        if desc.startswith("Covered Equipment or Services"):
            continue  # header row
        eff = iso_date(date_cell["text"])
        all_dates = DATE_RE.findall(date_cell["text"])
        names = desc_cell["strongs"]
        base_note = truncate(desc)
        if len(all_dates) > 1:
            last = "%s %s, %s" % all_dates[-1]
            base_note = truncate(desc, 200) + " [Entry updated %d time(s), most recently %s]" % (
                len(all_dates) - 1, last)
        if names:
            for name in names:
                # strip punctuation glued to the strong tag, keep "Inc./Corp." style
                name = name.rstrip(",;: ").strip()
                if re.search(r"\b(Inc|Corp)$", name):
                    name += "."
                entities.append({
                    "name": name,
                    "aliases": [],
                    "country": derive_country(name),
                    "address": None,
                    "status": None,
                    "effective_date": eff,
                    "federal_register": None,
                    "notes": base_note,
                })
        else:
            # Category rows (no named company): foreign-produced UAS, routers.
            short = desc.split(",")[0].split("—")[0].strip()
            short = re.sub(r"[\^†#*]+", "", short)
            short = re.sub(r"\s+", " ", short).strip()
            entities.append({
                "name": short,
                "aliases": [],
                "country": None,
                "address": None,
                "status": None,
                "effective_date": eff,
                "federal_register": None,
                "notes": "Category listing (not a named company). " + base_note,
            })

    out = {
        "list_id": "fcc-covered",
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
    for e in entities:
        print(" - %-55s %s  %s" % (e["name"], e["effective_date"], e["country"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
