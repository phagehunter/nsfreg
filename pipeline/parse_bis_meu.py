#!/usr/bin/env python3
"""Parse the BIS 'Military End-User' (MEU) List (Supplement No. 7 to Part 744)
from the .docx export.

Structure (verified by inspection): one 91-row, 3-column table:
    Country | Entity | Federal Register citation
- Country cell is filled only when the country changes; carry it forward.
- "[Reserved]" rows (Burma, Cambodia, Nicaragua, Venezuela) hold no entities.
- Group headers: "The following N subordinate institutions of X:" followed by
  alternating "Subordinate institution:" marker rows and member rows; members
  are separate entities (kept as separate records, parent noted in notes).
- FR citation is often empty on subordinate rows; carry forward the last
  non-empty citation within the country (matches the printed table layout).
- Entity cells may contain "a.k.a., the following N aliases:" plus em-dash
  alias lines, then the address on a later line.
"""
import json
import re
from pathlib import Path

import docx

SRC = Path(
    "../../nsf-prohibitions-july-2026/"
    "Appendix A - U.S. Proscribed Party Lists/"
    "U.S. Department of Commerce, Bureau of Industry and Security/"
    "Military End-User Entities/"
    "Supplement No. 7 to Part 744—'Military End-User' (MEU) List.docx"
)
OUT = Path(
    "../../nsf-prohibitions-july-2026/"
    "2026-07-09-nsf-restricted-entities-site/data/bis_meu.json"
)

DASHES = ("—", "–")
AKA_SPLIT_RE = re.compile(r",?\s+(?:a\.?k\.?a\.?|f\.?k\.?a\.?),?\s")
NAME_SUFFIX_TOKENS = (
    "Ltd", "LTD", "Limited", "Inc", "LLC", "L.L.C", "Co.", "Co ", "Co,",
    "Corp", "Company", "S.A", "GmbH", "B.V", "N.V", "Pte", "Pvt", "Sdn",
    "Bhd", "JSC", "PJSC", "OJSC", "CJSC", "OOO", "AO", "PLC",
)
SMALL_WORDS = {"of", "and", "the", "for"}
NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
}


def title_case_country(header):
    base = header.split(",")[0].strip()
    words = base.split()
    out = []
    for i, w in enumerate(words):
        lw = w.lower()
        if i > 0 and lw in SMALL_WORDS:
            out.append(lw)
        else:
            out.append(lw[:1].upper() + lw[1:])
    return " ".join(out)


# org-type comma segment that is part of the name, not the address
ORG_SEGMENT_RE = re.compile(r"^(Institute|Institution|Ministry|Academy|"
                            r"Bureau|Corporation|Research Center)\b")
ADDRESS_START_RE = re.compile(r"^(No\.|P\.?O\.?\s?Box|Room|Rm\b|Building|"
                              r"Bldg|Floor|Flat|Unit\b|Suite|\d)")
# a corporate suffix with the address glued on without a comma,
# e.g. "Beijing Ander Tech. Co., Ltd. No. C22, Yu An Rd."
GLUED_ADDR_RE = re.compile(r"^(.*\b(?:Ltd|Limited|Inc|Corp|Co)\.?,?)\s+"
                           r"((?:No\.\s?\S+|Floor\s+\S+|Room\s+\S+|\d+\S*).*)$")


def split_name(first_line):
    m = AKA_SPLIT_RE.search(first_line)
    if m:
        return first_line[: m.start()].strip().rstrip(",;"), ""
    i = 0
    while True:
        idx = first_line.find(",", i)
        if idx == -1:
            name, rest = first_line.strip().rstrip("."), ""
            break
        after = first_line[idx + 1:].lstrip()
        if any(after.startswith(tok) for tok in NAME_SUFFIX_TOKENS):
            i = idx + 1
            continue
        name, rest = first_line[:idx].strip(), after.strip()
        break
    # absorb org-type segments into the name ("Laboratory of Toxicant
    # Analysis, Institute of Pharmacology and Toxicology, <addr>")
    absorbed = 0
    while rest and absorbed < 2:
        seg, _, tail = rest.partition(",")
        seg = seg.strip()
        if seg and ORG_SEGMENT_RE.match(seg) and not ADDRESS_START_RE.match(seg):
            name = name + ", " + seg
            rest = tail.strip()
            absorbed += 1
        else:
            break
    # split a glued-on address off the name
    g = GLUED_ADDR_RE.match(name)
    if g:
        name = g.group(1).rstrip(",").strip()
        rest = (g.group(2).strip() + (", " + rest if rest else "")).strip()
    # trailing street-number fragment that belongs to the address
    t = re.match(r"^(.*\S)\s+(No\.\s?[A-Z]?\d+)$", name)
    if t and rest:
        name, rest = t.group(1).rstrip(","), t.group(2) + ", " + rest
    return name, rest


def clean_alias(line):
    a = line.lstrip("".join(DASHES)).strip()
    a = re.sub(r",?\s*(?:and\s+)?to include the following.*$", "", a,
               flags=re.IGNORECASE)
    a = re.sub(r";?\s*and$", "", a).strip()
    a = a.rstrip(";,").strip()
    if a.endswith(".") and not re.search(r"\b(?:Ltd|Inc|Corp|Co|Jr|Sr)\.$", a):
        a = a[:-1]
    return a.rstrip(";,").strip()


def parse_entity_cell(text, country, fr, parent):
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    first = lines[0]
    name, addr_first = split_name(first)
    aliases = []
    addr_parts = []
    if addr_first:
        addr_parts.append(addr_first)
    for ln in lines[1:]:
        if ln.startswith(DASHES):
            a = clean_alias(ln)
            if a:
                aliases.append(a)
        else:
            addr_parts.append(ln)
    address = " ".join(addr_parts).strip() or None
    federal_register = None
    if fr:
        federal_register = fr.strip().split(". ")[0].strip().rstrip(".") or None
    notes = f"Subordinate institution of {parent}" if parent else None
    return {
        "name": name,
        "aliases": aliases,
        "country": country,
        "address": address,
        "status": None,
        "effective_date": None,
        "federal_register": federal_register,
        "notes": notes,
    }


def main():
    doc = docx.Document(str(SRC))
    table = doc.tables[0]

    entities = []
    country = None
    last_fr = None
    parent = None          # current subordinate-group parent org
    parent_remaining = 0   # members still expected in the group

    for i, row in enumerate(table.rows):
        cells = [c.text.strip() for c in row.cells]
        c_country, c_entity, c_fr = (cells + ["", "", ""])[:3]
        if i == 0:  # header row
            continue
        if c_country:
            country = title_case_country(c_country)
            last_fr = None
            parent, parent_remaining = None, 0
        if not c_entity or c_entity == "[Reserved]":
            continue
        if c_fr and c_fr != "[Reserved]":
            last_fr = re.sub(r"\s+", " ", c_fr).strip()

        first_line = c_entity.split("\n", 1)[0].strip()
        # group header row
        m = re.match(r"^The following (\w+) subordinate institutions? of "
                     r"(.+?):$", first_line)
        if m:
            parent = m.group(2).strip()
            parent_remaining = NUM_WORDS.get(m.group(1).lower(), 0)
            continue
        # marker row (several misspelled "instituion" in source)
        if re.match(r"^Subordinate institu\w*:?$", first_line):
            continue

        cur_parent = None
        if parent and parent_remaining > 0:
            cur_parent = parent
            parent_remaining -= 1
            if parent_remaining == 0:
                parent = None
        entities.append(parse_entity_cell(c_entity, country, last_fr,
                                          cur_parent))

    out = {
        "list_id": "bis-meu",
        "source_file": SRC.name,
        "extracted": "2026-07-09",
        "count": len(entities),
        "entities": entities,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding="utf-8")

    # ---- report ----
    countries = sorted({e["country"] for e in entities})
    with_alias = sum(1 for e in entities if e["aliases"])
    print(f"entities: {len(entities)}")
    print(f"countries: {len(countries)} -> {countries}")
    print(f"with >=1 alias: {with_alias}")
    subs = [e for e in entities if e["notes"]]
    print(f"subordinate-institution records: {len(subs)}")
    print("--- samples ---")
    for e in entities[:3] + [x for x in entities if x["aliases"]][:2]:
        print(json.dumps(e, ensure_ascii=False)[:300])


if __name__ == "__main__":
    main()
