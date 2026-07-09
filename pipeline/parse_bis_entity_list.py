#!/usr/bin/env python3
"""Parse the eCFR text export of the BIS Entity List (Supplement No. 4 to Part 744).

Source format notes (verified by inspection):
- UTF-8 with BOM, CRLF line endings.
- The .txt file actually contains Supplements 4-8; the Entity List table is
  everything before the line starting "Supplement No. 5 to Part 744".
- Pseudo-table: a line starting with a TAB opens a new table *cell*; lines
  without a leading TAB are continuations of the current cell (alias lines
  starting with an em-dash, wrapped address lines, etc.).
- A row is: [name+address cell] [license requirement cell]
  [license review policy cell(s)] [Federal Register citation cell].
- Country headers are single all-uppercase tab cells (e.g. "AFGHANISTAN").
- Tab-only cells are row separators/padding.
- A few entries have extra cells AFTER the FR citation cell
  ("Subordinate institution", "Affiliated entities:", "The following
  addresses apply ..."); these belong to the entry just completed.
- Five footnote cells ("1 For this entity ...") and the amendment-history
  cell ("[63 FR 64325 ...]") trail the table and must be skipped.
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

SRC = Path(
    "/Users/curtishoffmann/Desktop/Desktop/Datasets/nsf-prohibitions-july-2026/"
    "Appendix A - U.S. Proscribed Party Lists/"
    "U.S. Department of Commerce, Bureau of Industry and Security/"
    "Entity List/Supplement No. 4 to Part 744—Entity List.txt"
)
OUT = Path(
    "/Users/curtishoffmann/Desktop/Desktop/Datasets/nsf-prohibitions-july-2026/"
    "2026-07-09-nsf-restricted-entities-site/data/bis_entity_list.json"
)

EM_DASH = "—"
DASHES = ("—", "–")  # em dash, en dash

FR_RE = re.compile(r"^\d{1,3} FR \d{3,}")
FOOTNOTE_RE = re.compile(r"^\d{1,2} (For this entity|Cybersecurity)")
AKA_SPLIT_RE = re.compile(r",?\s+(?:a\.?k\.?a\.?|f\.?k\.?a\.?),?\s")

# tokens that may follow a comma while still being part of the entity name
NAME_SUFFIX_TOKENS = (
    "Ltd", "LTD", "Ltda", "Limited", "Inc", "INC", "Incorporated", "LLC",
    "L.L.C", "LLP", "L.P", "LP", "Co.", "Co ", "Co,", "Corp", "Company",
    "S.A", "S.L", "S.R.L", "s.r.o", "S.p.A", "SpA", "SA", "SL", "GmbH",
    "A.G", "AG", "B.V", "BV", "N.V", "NV", "Pte", "Pvt", "PVT", "Sdn",
    "Bhd", "JSC", "PJSC", "OJSC", "CJSC", "OOO", "AO", "PAO", "ZAO",
    "FZE", "FZC", "FZCO", "L.L.C.", "PLC", "plc", "Jr", "Sr", "II", "III",
    "d.o.o", "a.s", "A.S", "A.Ş", "Lda", "C.A", "K.K", "S.A.S", "SAS",
    "S.A.R.L", "SARL", "SRL", "M.M.C", "MMC", "LLC.",
)

SMALL_WORDS = {"of", "and", "the", "for", "de", "la"}


def load_cells(lines):
    """Group physical lines into table cells. Returns list of cell dicts."""
    cells = []
    cur = None
    for raw in lines:
        line = raw.rstrip("\r")
        if line.startswith("\t"):
            if cur is not None:
                cells.append(cur)
            cur = {"lines": [line[1:].strip()] if line[1:].strip() else []}
        else:
            text = line.strip()
            if not text:
                continue  # blank spacing line inside a cell
            if cur is None:
                continue  # preamble paragraph before the table
            cur["lines"].append(text)
    if cur is not None:
        cells.append(cur)
    for c in cells:
        c["text"] = "\n".join(c["lines"]).strip()
    return cells


def is_country_header(text):
    if not text or "\n" in text:
        return False
    if len(text) > 50 or len(text) < 4:
        return False
    if any(ch.isdigit() for ch in text):
        return False
    if text != text.upper() or not any(ch.isalpha() for ch in text):
        return False
    return True


def title_case_country(header):
    """'CHINA, PEOPLE'S REPUBLIC OF' -> 'China'; 'CRIMEA REGION OF UKRAINE'
    -> 'Crimea Region of Ukraine'."""
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


def looks_like_license(text):
    t = text.lower()
    return ("subject to the ear" in t or t.startswith("for ")
            or t.startswith("all items") or t.startswith("see §"))


def is_continuation_cell(text):
    first = text.split("\n", 1)[0]
    return (first.startswith("Subordinate institu")
            or first.startswith("Affiliated entities")
            or first.startswith("The following addresses apply")
            or first.startswith("Addresses for")
            or first.startswith(DASHES))


def clean_alias(line):
    a = line.lstrip("".join(DASHES)).strip()
    # cut embedded "to include ..." / "and the following ..." tails
    for pat in (r";?\s*and the following [a-z]+ (?:aliases|subordinate|affiliated).*$",
                r",?\s*(?:and\s+)?to include the following.*$"):
        a = re.sub(pat, "", a, flags=re.IGNORECASE)
    a = a.strip()
    a = re.sub(r";?\s*and$", "", a)
    a = a.rstrip(";,").strip()
    if a.endswith(".") and not re.search(
            r"(?:Ltd|Inc|Corp|Co|S\.A|B\.V|N\.V|L\.L\.C|LLC|Jr|Sr|a\.s|\b[A-Z])\.$", a):
        a = a[:-1]
    a = a.rstrip(";,").strip()
    return a


# comma-separated segments that look like an organizational sub-unit rather
# than the start of an address (used only to resolve parent/sub-unit names
# that would otherwise collapse into duplicates, e.g.
# "Academy of Military Medical Sciences, Institute of Basic Medicine, <addr>")
ORG_SEGMENT_RE = re.compile(
    r"(Institute|Institution|Plant|Bureau|Design|Concern|Company|Corporation|"
    r"\bJSC\b|\bAO\b|\bOAO\b|\bPAO\b|\bNPO\b|\bGNPP\b|\bTMKB\b|Center|Centre|"
    r"Factory|Academy|University|Works|Association|Enterprise|Laborator)")
ADDRESS_START_RE = re.compile(
    r"^(No\.|P\.?O\.?\s?Box|Room|Rm\b|Building|Bldg|Floor|Flat|Unit\b|House\b|"
    r"Suite|Office\b|Plot|Km\b|Street|Ulitsa|ul\.|\d)")


def split_name(first_line, extend_names=None):
    """Split the first line of a name cell into (name, address_fragment).

    If extend_names is given (a set of first-pass names that are duplicated),
    absorb following comma-segments that look like org sub-units.
    """
    m = AKA_SPLIT_RE.search(first_line)
    if m:
        return first_line[: m.start()].strip().rstrip(",;"), ""
    # walk comma positions; skip commas followed by a corporate suffix token
    i = 0
    name = None
    rest = ""
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
    # parent/sub-unit disambiguation (second pass only)
    if extend_names is not None and name in extend_names:
        absorbed = 0
        while rest and absorbed < 2:
            seg, _, tail = rest.partition(",")
            seg = seg.strip()
            if (seg and not ADDRESS_START_RE.match(seg)
                    and ORG_SEGMENT_RE.search(seg)):
                name = name + ", " + seg
                rest = tail.strip()
                absorbed += 1
            else:
                break
    return name, rest


def strip_footnote_digits(name):
    """Strip a trailing footnote marker only when it is clearly an artifact:
    a single digit 1-5 (or the adjacent pair '45') preceded by a letter and
    not part of a numbered unit/plant/institute name."""
    m = re.search(r"^(.*[A-Za-z).])\s(45|[1-5])$", name)
    if m:
        head = m.group(1)
        if not re.search(r"(No\.|Unit|Factory|Institute|Base|Bureau|Academy|"
                         r"Team|Group|Number|District|Type|Zavod|Plant)$",
                         head, re.I):
            return head.strip()
    return name


def parse_entity(row, country, extend_names=None):
    name_lines = row["name_lines"]
    aliases = []
    addr_parts = []
    first = name_lines[0]
    # group entries like "The following Department of Atomic Energy entities:"
    grp = re.match(r"^The following (.+?) entities:$", first)
    if grp:
        name, addr_first = grp.group(1), ""
    else:
        name, addr_first = split_name(first, extend_names)
    # "A. Leib Ltd.; HA'Assif 19, ..." - semicolon separates name from address
    if "; " in name:
        name, _, semi_rest = name.partition("; ")
        addr_first = (semi_rest + (", " + addr_first if addr_first else "")).strip()
        name = name.strip()
    name = strip_footnote_digits(name)
    if addr_first:
        addr_parts.append(addr_first)
    for ln in name_lines[1:]:
        if ln.startswith(DASHES):
            a = clean_alias(ln)
            if a and a.lower() not in ("and", "the following"):
                aliases.append(a)
        else:
            # skip structural marker lines
            if ln in ("Subordinate institution", "Subordinate institution:",
                      "Subordinate instituion:", "Affiliated entities:"):
                continue
            if ln.endswith((" aliases:", " alias:", "aliases:", "alias:")):
                continue  # sub-entry "X, a.k.a., the following..." intro
            addr_parts.append(ln)
    address = " ".join(addr_parts).strip() or None

    fr = row.get("fr")
    federal_register = None
    if fr:
        federal_register = fr.split(". ")[0].strip().rstrip(".") or None

    lic = row.get("license")
    notes = None
    if lic:
        lic = re.sub(r"\s+", " ", lic).strip()
        notes = lic if len(lic) <= 200 else lic[:197].rstrip() + "..."

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
    text = SRC.read_text(encoding="utf-8-sig")
    lines = text.split("\n")
    # keep only Supplement No. 4 (stop at Supplement No. 5 header)
    end = len(lines)
    for i, ln in enumerate(lines):
        if ln.startswith("Supplement No. 5 to Part 744"):
            end = i
            break
    cells = load_cells(lines[:end])

    rows = []  # (row_dict, country) in table order
    country = None
    row = None  # dict: name_lines, license, policy, fr

    def flush():
        nonlocal row
        if row and row.get("name_lines"):
            rows.append((row, country))
        row = None

    for cell in cells:
        t = cell["text"]
        if not t:
            continue  # tab-only padding cell
        if is_country_header(t):
            flush()
            country = title_case_country(t)
            continue
        if country is None:
            continue  # table header cells before first country
        if FOOTNOTE_RE.match(t) or t.startswith("["):
            flush()
            continue
        if row is None:
            row = {"name_lines": list(cell["lines"]), "license": None,
                   "policy": [], "fr": None}
            continue
        if row.get("fr"):
            if is_continuation_cell(t):
                row["name_lines"].extend(cell["lines"])
            else:
                flush()
                row = {"name_lines": list(cell["lines"]), "license": None,
                       "policy": [], "fr": None}
            continue
        if row["license"] is None:
            if looks_like_license(t):
                row["license"] = t
            else:
                row["name_lines"].extend(cell["lines"])  # address overflow
            continue
        if FR_RE.match(t):
            row["fr"] = t
        else:
            row["policy"].append(t)
    flush()

    # pass 1: first-comma names, to find parent orgs listed with sub-units
    from collections import Counter
    prelim = Counter()
    for r, ctry in rows:
        e = parse_entity(r, ctry)
        prelim[(e["name"], ctry)] += 1
    extend_names = {n for (n, c), v in prelim.items() if v > 1}
    # pass 2: final parse, absorbing org sub-unit segments for duplicates
    entities = [parse_entity(r, ctry, extend_names) for r, ctry in rows]

    out = {
        "list_id": "bis-entity-list",
        "source_file": SRC.name,
        "extracted": "2026-07-09",
        "count": len(entities),
        "entities": entities,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding="utf-8")

    # ---- report / quality checks ----
    countries = sorted({e["country"] for e in entities})
    with_alias = sum(1 for e in entities if e["aliases"])
    print(f"entities: {len(entities)}")
    print(f"countries: {len(countries)}")
    print(f"with >=1 alias: {with_alias}")
    for probe in ("Huawei Technologies Co., Ltd.",
                  "Beijing University of Aeronautics and Astronautics (BUAA)",
                  "Semiconductor Manufacturing International Corporation (SMIC)"):
        hits = [e for e in entities if e["name"] == probe]
        print(f"probe {probe!r}: {len(hits)}")
    # suspicious names (possible footnote digits / parse slips)
    weird = [e["name"] for e in entities if re.search(r"\s\d{1,2}$", e["name"])]
    print(f"names ending in 1-2 digits: {len(weird)}")
    for w in weird[:15]:
        print("   ?", w)
    import random
    random.seed(4)
    print("--- samples ---")
    for e in random.sample(entities, 6):
        print(json.dumps(e, ensure_ascii=False)[:300])


if __name__ == "__main__":
    main()
