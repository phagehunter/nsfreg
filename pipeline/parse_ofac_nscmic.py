#!/usr/bin/env python3
"""Parse the OFAC Non-SDN Chinese Military-Industrial Complex Companies
(NS-CMIC) List PDF (December 16, 2021).

Layout: 3-column portrait pages (columns at x0 ~ 50/222/390), page header
and footer bands. Extracted with pdfminer (pypdf inserts spurious
intra-word spaces for this PDF's fonts). Each entry is:

  NAME (a.k.a. ALT1; f.k.a. ALT2; ...), address...; Equity Ticker ...;
  Issuer Name ...; ISIN ...; Target Type ...; Effective Date (CMIC) ...;
  Purchase/Sales For Divestment Date (CMIC) ...; Listing Date (CMIC) ...;
  Unified Social Credit Code (USCC) ... [CMIC-EO13959].

OFAC lists every alias as its own full entry (cross-referenced via
a.k.a.), so entries are deduplicated into one record per company keyed on
USCC (or alias-set). Canonical display name comes from the mixed-case
"Issuer Name" field when it matches a listed variant; otherwise the
longest ALL-CAPS variant is title-cased with acronyms preserved.
"""
import os
import re
from datetime import datetime

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTTextLine

from common import BASE_DIR, collapse_ws, entity_record, write_output

SOURCE = os.path.join(
    BASE_DIR,
    "U.S. Department of Treasury, Office of Foreign Assets Control",
    "Non-SDN Chinese Military-Industrial Complex Companies",
    "nscmiclist.pdf",
)

COL_BOUNDS = (150.0, 310.0)  # x0 < 150 -> col 0; < 310 -> col 1; else col 2

ENTRY_END = re.compile(r"\[CMIC-[A-Z0-9]+\](?:\s*\(Linked To:[^)]*\))?\s*\.")
FIELD_KEYS = (
    "Equity Ticker", "Issuer Name", "ISIN", "Target Type", "Effective Date",
    "Purchase/Sales For Divestment Date", "Listing Date",
    "Unified Social Credit Code", "Executive Order", "Additional Sanctions",
    "Website", "Email", "Phone",
)

ACRONYMS = {
    "AECC", "AVIC", "CASC", "CASIC", "CETC", "CCCC", "CEC", "CGN", "CGNPC",
    "CNNC", "CNOOC", "COMEC", "COSCO", "CRRC", "CSGC", "CSIC", "CSSC",
    "CSCEC", "UAV", "CH", "DJI", "SZ", "SMIC", "ZTE", "CCT", "GD", "IT",
    "JONHON", "PLA", "USA", "LLC", "PLC", "AG", "BVI",
}
SPECIAL_CASE = {"IFLYTEK": "iFLYTEK", "LTD": "Ltd", "CO": "Co", "CORP": "Corp",
                "MFG": "Mfg", "INTL": "Intl", "GRP": "Grp"}
SMALL_WORDS = {"of", "and", "the", "for", "to", "in", "on", "at", "by"}


def smart_title(name):
    """Title-case an ALL-CAPS company name, preserving obvious acronyms."""
    out = []
    for i, tok in enumerate(name.split()):
        core = tok.strip("(),.&;\"'")
        if core in SPECIAL_CASE:
            out.append(tok.replace(core, SPECIAL_CASE[core]))
            continue
        if core in ACRONYMS or (core.isalpha() and core.isupper()
                                and not re.search(r"[AEIOUY]", core)):
            out.append(tok)  # keep acronym as-is
            continue
        if not core:
            out.append(tok)
            continue

        def cap_seg(seg):
            if not seg or not seg[0].isalpha():
                return seg[:1] + cap_seg(seg[1:]) if seg else seg
            return seg[0].upper() + seg[1:].lower()

        low = core.lower()
        if low in SMALL_WORDS and i != 0:
            new = low
        else:
            # capitalize each hyphen-separated segment; lowercase after
            # apostrophes ("XI'AN" -> "Xi'an")
            new = "-".join(cap_seg(s) for s in core.split("-"))
            new = re.sub(r"'(\w+)", lambda m: "'" + m.group(1).lower(), new)
        out.append(tok.replace(core, new))
    return " ".join(out)


def get_text():
    """Rebuild document text in column reading order."""
    chunks = []
    for i, page in enumerate(extract_pages(SOURCE)):
        cols = ([], [], [])
        top_cut = 685.0 if i == 0 else 745.0
        for el in page:
            if not isinstance(el, LTTextContainer):
                continue
            for ln in el:
                if not isinstance(ln, LTTextLine):
                    continue
                t = collapse_ws(ln.get_text())
                if not t or ln.y0 > top_cut or ln.y0 < 40.0:
                    continue
                c = 0 if ln.x0 < COL_BOUNDS[0] else 1 if ln.x0 < COL_BOUNDS[1] else 2
                cols[c].append((-ln.y0, t))
        for col in cols:
            col.sort()
            chunks.extend(t for _, t in col)
    text = " ".join(chunks)
    # fix hyphenation artifacts from line wraps ("HIGH- TECHNOLOGY")
    text = re.sub(r"(\w)-\s+(?=[A-Z0-9])", r"\1-", text)
    # repair program tags broken across line/column wraps
    text = re.sub(r"\[\s*CMIC\s*-\s*EO\s*(\d+)\s*\]\s*\.", r"[CMIC-EO\1].", text)
    return text


CHINESE_GLOSS = re.compile(r"\s*\(Chinese\s+(?:Simplified|Traditional):\s*([^)]*)\)")


def strip_gloss(s):
    """Remove '(Chinese Simplified: ...)' glosses; return (clean, [chinese])."""
    chinese = [collapse_ws(m) for m in CHINESE_GLOSS.findall(s)]
    return collapse_ws(CHINESE_GLOSS.sub("", s)), [c for c in chinese if c]


def split_name_aka(head):
    """Split 'NAME (a.k.a. X; f.k.a. Y)' -> (name, [aliases]). Handles
    nested parens inside alias names."""
    m = re.search(r"\((?=\s*(?:a\.k\.a\.|f\.k\.a\.))", head)
    if not m:
        return collapse_ws(head.rstrip(", ")), [], set()
    name = collapse_ws(head[:m.start()])
    depth = 0
    end = None
    for j in range(m.start(), len(head)):
        if head[j] == "(":
            depth += 1
        elif head[j] == ")":
            depth -= 1
            if depth == 0:
                end = j
                break
    inner = head[m.start() + 1:end] if end else head[m.start() + 1:]
    aliases = []
    fka = set()
    for part in inner.split(";"):
        part = collapse_ws(part)
        is_fka = part.startswith("f.k.a.")
        part = re.sub(r"^(a\.k\.a\.|f\.k\.a\.)\s*", "", part)
        part = part.strip().strip('"').strip()
        if part:
            aliases.append(part)
            if is_fka:
                fka.add(part.upper())
    return name, aliases, fka


def parse_entry(entry):
    entry = collapse_ws(entry)
    tag_m = ENTRY_END.search(entry)
    tag, linked_to = None, None
    if tag_m:
        tag = re.search(r"\[CMIC-[A-Z0-9]+\]", tag_m.group(0)).group(0)
        lm = re.search(r"\(Linked To:\s*([^)]*)\)", tag_m.group(0))
        if lm:
            linked_to = collapse_ws(lm.group(1))
    body = entry[:tag_m.start()].rstrip(" ,;") if tag_m else entry

    # find where the metadata fields begin
    segs = [collapse_ws(s) for s in body.split(";")]
    head_parts, addr_parts, fields = [], [], []
    stage = 0  # 0 = name/aka, 1 = address, 2 = fields
    for seg in segs:
        if any(seg.startswith(k) for k in FIELD_KEYS):
            stage = 2
        if stage == 2:
            fields.append(seg)
            continue
        if stage == 0:
            # name/aka section persists until the aka paren closes
            head_parts.append(seg)
            joined = ";".join(head_parts)
            if joined.count("(") == joined.count(")"):
                stage = 1
            continue
        addr_parts.append(seg)

    head = ";".join(head_parts)
    # peel the address off the head: it follows the closing paren of the
    # aka clause (or the first comma before a mixed-case token)
    name_aka, address_head = head, ""
    m = re.search(r"\)\s*,\s*", head)
    if m and re.search(r"\((?:a\.k\.a\.|f\.k\.a\.)", head):
        name_aka, address_head = head[:m.start() + 1], head[m.end():]
    else:
        # no aka clause: name is the leading ALL-CAPS run; the address
        # starts at the first comma followed by mixed-case text or an
        # address-like token (PO Box, No. 1, digits, ...)
        m2 = re.search(r",\s+(?=[A-Z][a-z]|[0-9]|P\.?O\.?\s*[Bb]ox)", head)
        if m2:
            name_aka, address_head = head[:m2.start()], head[m2.end():]
    name, aliases, fka = split_name_aka(name_aka)
    name, chinese = strip_gloss(name.strip().strip('"').strip())
    cleaned = []
    for a in aliases:
        a2, zh = strip_gloss(a)
        if a2:
            cleaned.append(a2)
        chinese.extend(zh)
    aliases = cleaned + chinese
    address = collapse_ws("; ".join(p for p in [address_head] + addr_parts if p)) or None

    meta = {}
    for f in fields:
        for k in FIELD_KEYS:
            if f.startswith(k):
                meta[k] = collapse_ws(f[len(k):]).lstrip("(CMIC) ").strip()
                break
    # re-extract with paren labels intact
    for f in fields:
        if f.startswith("Effective Date"):
            meta["Effective Date"] = collapse_ws(re.sub(r"^Effective Date\s*(\(CMIC\))?", "", f))
        elif f.startswith("Listing Date"):
            meta["Listing Date"] = collapse_ws(re.sub(r"^Listing Date\s*(\(CMIC\))?", "", f))
        elif f.startswith("Unified Social Credit Code"):
            meta["USCC"] = collapse_ws(re.sub(r"^Unified Social Credit Code\s*(\(USCC\))?", "", f))
        elif f.startswith("Issuer Name"):
            meta["Issuer Name"] = collapse_ws(f[len("Issuer Name"):])
        elif f.startswith("Target Type"):
            meta["Target Type"] = collapse_ws(f[len("Target Type"):])

    return {
        "name": name, "aliases": aliases, "fka": fka, "address": address,
        "meta": meta, "tag": tag, "linked_to": linked_to,
    }


def to_iso(d):
    try:
        return datetime.strptime(d, "%d %b %Y").date().isoformat()
    except (ValueError, TypeError):
        return None


def main():
    text = get_text()
    start = text.find("AERO ENGINE CORP OF CHINA")
    m_reg = re.search(r"country in which the equity ticker is\s*registered\.", text)
    if m_reg and m_reg.end() < start:
        start = m_reg.end()
    text = text[start:]

    raw_entries = []
    pos = 0
    for m in ENTRY_END.finditer(text):
        raw_entries.append(text[pos:m.end()])
        pos = m.end()
    trailing = collapse_ws(text[pos:])
    if trailing:
        print(f"  WARN: trailing text after last entry: {trailing[:120]!r}")

    parsed = [parse_entry(e) for e in raw_entries]

    # ---- deduplicate: one record per company ----
    # Every alias appears as its own full entry cross-referencing the
    # others, so all entries of one company carry the IDENTICAL variant
    # set. Grouping on the full set (rather than any shared variant)
    # avoids over-merging distinct companies that share a short alias
    # (e.g. "CEC", "CHINA TELECOM", Huawei cross-references).
    groups = {}
    order = []
    for p in parsed:
        key = frozenset(re.sub(r"\W", "", v.upper())
                        for v in [p["name"]] + p["aliases"])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(p)

    # variants shared by more than one group (e.g. OFAC cross-references
    # "HUAWEI INVESTMENT & HOLDING CO LTD" on the Huawei Technologies
    # entry) must not become a group's display name
    norm_group_count = {}
    for gkey in order:
        for norm in gkey:
            norm_group_count[norm] = norm_group_count.get(norm, 0) + 1

    def norm(v):
        return re.sub(r"\W", "", v.upper())

    entities = []
    for key in order:
        grp = groups[key]
        variants = []
        for p in grp:
            for v in [p["name"]] + p["aliases"]:
                if v.upper() not in {x.upper() for x in variants}:
                    variants.append(v)
        meta = {}
        for p in grp:
            meta.update({k: v for k, v in p["meta"].items() if v})
        # canonical display name: never a f.k.a. name; prefer the
        # mixed-case Issuer Name when it matches a current variant and is
        # not a badly truncated form; otherwise smart-title-case the
        # longest current ALL-CAPS variant.
        fka_all = set()
        for p in grp:
            fka_all |= p["fka"]
        current = [v for v in variants
                   if v.upper() not in fka_all] or variants
        unique = [v for v in current if norm_group_count.get(norm(v), 1) == 1]
        current = unique or current
        full = [v for v in current if len(v) > 4]
        longest = max(full or current, key=len)
        issuer = meta.get("Issuer Name", "")
        canon = None
        if issuer and len(issuer) >= 0.8 * len(longest):
            iu = issuer.upper().replace(" ", "")
            for v in current:
                if v.upper().replace(" ", "")[:12] == iu[:12]:
                    canon = issuer
                    break
        if not canon:
            canon = smart_title(longest)
        if canon.isupper():
            canon = smart_title(canon)
        aliases = [v for v in variants if v.upper() != canon.upper()]
        address = next((p["address"] for p in grp if p["address"]), None)
        country = None
        if address:
            first_addr = address.split(";")[0]
            tail = first_addr.rstrip(".").rsplit(",", 1)[-1].strip()
            if tail and not any(ch.isdigit() for ch in tail):
                country = tail
            if country == "British" and "Virgin Islands" in address:
                country = "British Virgin Islands"
        note_bits = []
        if meta.get("Target Type"):
            note_bits.append("Target Type: " + meta["Target Type"])
        if meta.get("Listing Date"):
            note_bits.append("Listing Date (CMIC): " + meta["Listing Date"])
        if meta.get("USCC"):
            note_bits.append("USCC: " + meta["USCC"])
        tag = next((p["tag"] for p in grp if p["tag"]), None)
        if tag:
            note_bits.append("Program: " + tag.strip("[]"))
        linked = next((p["linked_to"] for p in grp if p["linked_to"]), None)
        if linked:
            note_bits.append("Linked To: " + linked)
        entities.append(entity_record(
            name=canon,
            aliases=aliases,
            country=country,
            address=address,
            effective_date=to_iso(meta.get("Effective Date")),
            notes="; ".join(note_bits) or None,
        ))

    write_output("ofac-nscmic", SOURCE, entities, "ofac_nscmic.json")
    print(f"Raw alias-expanded entries: {len(parsed)}; deduplicated companies: {len(entities)}")
    print("\nSamples:")
    for e in entities[:4] + entities[-4:]:
        print("  *", e["name"], "| aliases:", e["aliases"][:3],
              "| country:", e["country"], "| eff:", e["effective_date"])


if __name__ == "__main__":
    main()
