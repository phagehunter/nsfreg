#!/usr/bin/env python3
"""Parse the DHS UFLPA Entity List from a live-fetched copy of
https://www.dhs.gov/uflpa-entity-list (fetched 2026-07-09; copy stored at
data/source-uflpa-2026-07-09.html).

The page carries three tables, one per UFLPA statutory category:
  table 0 -> Sec. 2(d)(2)(B)(i)   (mine/produce/manufacture in Xinjiang)
  table 1 -> Sec. 2(d)(2)(B)(ii)  (labor transfer / recruitment)
  table 2 -> Sec. 2(d)(2)(B)(v)   (sourcing via government labor schemes)

Entities repeated across categories are merged into one record with all
categories in notes. Alias parentheticals ("also known as", "formerly known
as", "and N aliases:", "including N aliases:") are split out.

Usage: python3 pipeline/parse_dhs_uflpa_live.py [path-to-html]
"""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = ROOT / "data" / "source-uflpa-2026-07-09.html"
OUT = ROOT / "data" / "dhs_uflpa.json"

CATEGORIES = [
    "UFLPA Sec. 2(d)(2)(B)(i): mines, produces, or manufactures goods in Xinjiang with forced labor",
    "UFLPA Sec. 2(d)(2)(B)(ii): works with the XUAR government to recruit or transfer forced labor",
    "UFLPA Sec. 2(d)(2)(B)(v): sources material from Xinjiang via government labor schemes",
]

ALIAS_LEAD = re.compile(
    r"\((?:and\s+\w+\s+alias(?:es)?:|including\s+\w+\s+alias(?:es)?:|also\s+known\s+as|formerly\s+known\s+as|a/?k/?a\.?|f/?k/?a\.?)\s*",
    re.I,
)


def strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def split_name(raw):
    """Return (name, aliases, extra_note)."""
    aliases, notes = [], []
    name = raw
    # pull every parenthetical that is an alias clause
    while True:
        m = ALIAS_LEAD.search(name)
        if not m:
            break
        depth, i = 1, m.end()
        while i < len(name) and depth:
            if name[i] == "(":
                depth += 1
            elif name[i] == ")":
                depth -= 1
            i += 1
        inner = name[m.end():i - 1]
        for part in re.split(r";|,\s+and\s+", inner):
            part = part.strip(" .;")
            part = re.sub(r"^and\s+", "", part, flags=re.I)
            if part:
                aliases.append(part)
        name = (name[:m.start()] + " " + name[i:]).strip()
    # subsidiaries / affiliates phrasing stays out of the name
    m = re.search(r"\b(and its .*)$", name, re.I)
    if m:
        notes.append(m.group(1).strip(" ."))
        name = name[:m.start()].strip(" ,;")
    name = re.sub(r"\s+", " ", name).strip(" ,;.")
    return name, aliases, "; ".join(notes)


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
    raw = src.read_text(encoding="utf-8", errors="replace")
    tables = re.findall(r"<table.*?</table>", raw, re.S)
    assert len(tables) == 3, f"expected 3 tables, found {len(tables)}"

    merged = {}
    order = []
    for ti, table in enumerate(tables):
        for row in re.findall(r"<tr.*?</tr>", table, re.S):
            cells = [strip_tags(c) for c in re.findall(r"<t[dh][^>]*>.*?</t[dh]>", row, re.S)]
            if len(cells) < 2 or cells[0].lower() in ("name of entity", "entity name"):
                continue
            raw_name, eff = cells[0], cells[1]
            name, aliases, extra = split_name(raw_name)
            if not name:
                continue
            key = name.lower()
            if key not in merged:
                merged[key] = {
                    "name": name,
                    "aliases": [],
                    "country": "China",
                    "address": None,
                    "status": None,
                    "effective_date": eff or None,
                    "federal_register": None,
                    "notes": "",
                    "_cats": [],
                    "_extras": [],
                }
                order.append(key)
            rec = merged[key]
            for a in aliases:
                if a not in rec["aliases"]:
                    rec["aliases"].append(a)
            if extra and extra not in rec["_extras"]:
                rec["_extras"].append(extra)
            if CATEGORIES[ti] not in rec["_cats"]:
                rec["_cats"].append(CATEGORIES[ti])

    entities = []
    for key in order:
        rec = merged.pop(key)
        bits = rec.pop("_cats") + rec.pop("_extras")
        rec["notes"] = "; ".join(bits) if bits else None
        entities.append(rec)

    blob = {
        "list_id": "dhs-uflpa",
        "source_file": "dhs.gov/uflpa-entity-list (live fetch 2026-07-09)",
        "extracted": "2026-07-09",
        "count": len(entities),
        "entities": entities,
    }
    OUT.write_text(json.dumps(blob, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {OUT}: {len(entities)} unique entities")
    multi = [e for e in entities if e["notes"] and e["notes"].count("UFLPA Sec.") > 1]
    print(f"  in >1 category: {len(multi)}")
    withal = [e for e in entities if e["aliases"]]
    print(f"  with aliases: {len(withal)}")
    for e in entities[:5]:
        print("  -", e["name"], "| aliases:", e["aliases"][:3])


if __name__ == "__main__":
    main()
