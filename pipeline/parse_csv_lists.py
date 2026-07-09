#!/usr/bin/env python3
"""Parse four U.S. proscribed-party CSV sources into normalized JSON.

Sources (under "Appendix A - U.S. Proscribed Party Lists"):
  1. CBP Withhold Release Orders & Findings  -> data/cbp_wro.json
  2. BIS Denied Persons List                 -> data/bis_dpl.json
  3. State Dept Statutory Debarments         -> data/state_debarred_statutory.json
  4. State Dept Administrative Debarments    -> data/state_debarred_admin.json

Stdlib only. Python 3.9.
"""
import csv
import json
import os
import re
import sys

BASE = ("/Users/curtishoffmann/Desktop/Desktop/Datasets/nsf-prohibitions-july-2026/"
        "Appendix A - U.S. Proscribed Party Lists")
OUT_DIR = ("/Users/curtishoffmann/Desktop/Desktop/Datasets/nsf-prohibitions-july-2026/"
           "2026-07-09-nsf-restricted-entities-site/data")
EXTRACTED = "2026-07-09"

SOURCES = {
    "cbp_wro": os.path.join(
        BASE, "U.S. Customs and Border Protection",
        "Withhold Release Orders & Findings list",
        "withhold-release-orders-findings-fy26-2026-06-23.csv"),
    "bis_dpl": os.path.join(
        BASE, "U.S. Department of Commerce, Bureau of Industry and Security",
        "Denied Persons", "dpl_04142026.csv"),
    "state_stat": os.path.join(
        BASE, "U.S. Department of State", "Debarred Parties",
        "Statutory Debarments", "Stat Debarred Parties_20250825_revised.csv"),
    "state_admin": os.path.join(
        BASE, "U.S. Department of State", "Debarred Parties",
        "Administrative Debarments", "Admin Debarred Parties_06.01.23.csv"),
}

# ISO 3166-1 alpha-2 -> full country name (codes seen in the data plus common ones)
COUNTRY_CODES = {
    "AE": "United Arab Emirates", "AF": "Afghanistan", "AL": "Albania",
    "AR": "Argentina", "AT": "Austria", "AU": "Australia", "BE": "Belgium",
    "BG": "Bulgaria", "BR": "Brazil", "BY": "Belarus", "CA": "Canada",
    "CH": "Switzerland", "CL": "Chile", "CN": "China", "CO": "Colombia",
    "CU": "Cuba", "CY": "Cyprus", "CZ": "Czechia", "DE": "Germany",
    "DK": "Denmark", "DZ": "Algeria", "EG": "Egypt", "ES": "Spain",
    "FI": "Finland", "FR": "France", "GB": "United Kingdom", "GR": "Greece",
    "HK": "Hong Kong", "HU": "Hungary", "ID": "Indonesia", "IE": "Ireland",
    "IL": "Israel", "IN": "India", "IQ": "Iraq", "IR": "Iran",
    "IT": "Italy", "JO": "Jordan", "JP": "Japan", "KP": "North Korea",
    "KR": "South Korea", "KW": "Kuwait", "KZ": "Kazakhstan",
    "LB": "Lebanon", "LI": "Liechtenstein", "LK": "Sri Lanka",
    "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia", "LY": "Libya",
    "MO": "Macau", "MT": "Malta", "MX": "Mexico", "MY": "Malaysia",
    "NG": "Nigeria", "NL": "Netherlands", "NO": "Norway", "NZ": "New Zealand",
    "OM": "Oman", "PA": "Panama", "PE": "Peru", "PH": "Philippines",
    "PK": "Pakistan", "PL": "Poland", "PT": "Portugal", "QA": "Qatar",
    "RO": "Romania", "RS": "Serbia", "RU": "Russia", "SA": "Saudi Arabia",
    "SE": "Sweden", "SG": "Singapore", "SK": "Slovakia", "SY": "Syria",
    "TH": "Thailand", "TR": "Turkey", "TW": "Taiwan", "UA": "Ukraine",
    "US": "United States", "UZ": "Uzbekistan", "VE": "Venezuela",
    "VN": "Vietnam", "YE": "Yemen", "ZA": "South Africa",
}

# US state / territory abbreviations, used ONLY as a fallback when a code is
# not a valid ISO country code (e.g. "NM"), or when a 5-digit ZIP ends an
# address whose country slot is empty. Codes overlapping ISO (CA, AL, IN, DE
# ...) are never treated as states here.
US_STATE_CODES = {
    "AK", "AZ", "AR", "CT", "DC", "FL", "HI", "IA", "KS", "KY", "MA", "MI",
    "MN", "MS", "NC", "ND", "NE", "NH", "NJ", "NM", "NV", "NY", "OH", "OK",
    "OR", "RI", "TN", "TX", "UT", "VA", "VT", "WA", "WI", "WV", "WY",
}

ALIAS_SPLIT_RE = re.compile(r"\s*(?:,\s*)?\b(?:a/k/a|a\.\s?k\.\s?a\.?|aka)\b[.:]?\s*",
                            re.IGNORECASE)
PAREN_AKA_RE = re.compile(r"\s*\(\s*(?:a/k/a|a\.\s?k\.\s?a\.?|aka)\b[.:]?\s*(.+?)\)\s*",
                          re.IGNORECASE)


def read_csv(path):
    """Read a CSV as list of dicts; utf-8-sig first, cp1252 fallback."""
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    rows = list(csv.DictReader(text.splitlines()))
    return rows


def clean(s):
    """Collapse whitespace (incl. NBSP), strip; return None if empty."""
    if s is None:
        return None
    s = s.replace(" ", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def clean_name(s):
    s = clean(s) or ""
    s = s.strip(" \t\"'")
    s = s.rstrip(",;")
    return s.strip()


def norm_date(s):
    """M/D/YYYY -> YYYY-MM-DD; anything else returned cleaned as-is."""
    s = clean(s)
    if not s:
        return None
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return "%04d-%02d-%02d" % (y, mo, d)
    return s


def entity(name, aliases=None, country=None, address=None, status=None,
           effective_date=None, federal_register=None, notes=None):
    return {
        "name": name,
        "aliases": aliases or [],
        "country": country,
        "address": address,
        "status": status,
        "effective_date": effective_date,
        "federal_register": federal_register,
        "notes": notes,
    }


def write_output(list_id, source_path, entities):
    out = {
        "list_id": list_id,
        "source_file": os.path.basename(source_path),
        "extracted": EXTRACTED,
        "count": len(entities),
        "entities": entities,
    }
    fname = {
        "cbp-wro": "cbp_wro.json",
        "bis-dpl": "bis_dpl.json",
        "state-debarred-statutory": "state_debarred_statutory.json",
        "state-debarred-admin": "state_debarred_admin.json",
    }[list_id]
    path = os.path.join(OUT_DIR, fname)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("Wrote %s (%d entities)" % (path, len(entities)))
    return path


def split_akas(name):
    """Split inline a/k/a chains: 'X, a/k/a Y, a/k/a Z' -> ('X', ['Y', 'Z'])."""
    parts = [p.strip(" ,;") for p in ALIAS_SPLIT_RE.split(name) if p.strip(" ,;")]
    if len(parts) <= 1:
        return clean_name(name), []
    return clean_name(parts[0]), [clean_name(p) for p in parts[1:]]


# ---------------------------------------------------------------- 1. CBP WRO
def parse_cbp():
    rows = read_csv(SOURCES["cbp_wro"])
    entities = []
    for row in rows:
        raw_name = clean(row.get("Entity")) or ""
        if not raw_name:
            continue
        name, aliases = split_akas(raw_name)
        notes_parts = []
        wro_type = clean(row.get("WRO/Finding"))
        if wro_type:
            notes_parts.append(wro_type)
        industry = clean(row.get("Industry"))
        if industry:
            notes_parts.append("Industry: " + industry)
        merch = clean(row.get("Merchandise"))
        if merch:
            notes_parts.append("Merchandise: " + merch)
        remarks = clean(row.get("Remarks"))
        if remarks:
            notes_parts.append("Remarks: " + remarks)
        entities.append(entity(
            name=name,
            aliases=aliases,
            country=clean(row.get("Country")),
            status=clean(row.get("Status")),
            effective_date=norm_date(row.get("Effective Date")),
            notes="; ".join(notes_parts) or None,
        ))
    return write_output("cbp-wro", SOURCES["cbp_wro"], entities)


# ---------------------------------------------------------------- 2. BIS DPL
def dpl_country(addr_segs):
    """Derive country from address segments (format: ..., CC, postal)."""
    segs = [s.strip() for s in addr_segs]
    non_empty = [s for s in segs if s]
    # Preferred: second-to-last raw segment is the country code slot
    if len(segs) >= 2 and re.fullmatch(r"[A-Z]{2}", segs[-2]):
        if segs[-2] in COUNTRY_CODES:
            return COUNTRY_CODES[segs[-2]]
        if segs[-2] in US_STATE_CODES:
            return "United States"
    # A bare 5-digit ZIP at the end with no country code in the slot -> US
    # (checked before the generic scan so 'MONTGOMERY, AL, , 36112' is not
    #  misread as Albania)
    if non_empty and re.fullmatch(r"\d{5}(-\d{4})?", non_empty[-1]):
        return "United States"
    # Fall back to scanning from the end for any 2-letter code
    for c in reversed(non_empty):
        if re.fullmatch(r"[A-Z]{2}", c):
            if c in COUNTRY_CODES:
                return COUNTRY_CODES[c]
            if c in US_STATE_CODES:
                return "United States"
    return None


def parse_dpl():
    rows = read_csv(SOURCES["bis_dpl"])
    entities = []
    for row in rows:
        na = row.get("Name_and_Address") or ""
        segs = na.split(",")
        name = clean_name(segs[0])
        if not name:
            continue
        addr_segs = segs[1:]
        # Re-attach generational suffixes split off by the comma
        # ("JOEL PRADO, JR., INMATE ..." -> name "JOEL PRADO, JR.")
        if addr_segs and re.fullmatch(r"(?i)\s*(JR|SR|II|III|IV)\.?\s*",
                                      addr_segs[0]):
            name = name + ", " + clean_name(addr_segs[0])
            addr_segs = addr_segs[1:]
        # Parenthesized a/k/a first ("PEARL (A.K.A. NEI-CHIEN CHU) LI"),
        # then inline a/k/a chains ("FUYI SUN A/K/A FRANK SUN") -> aliases
        name, aliases = extract_paren_akas(name)
        name, more = split_akas(name)
        aliases.extend(more)
        country = dpl_country(addr_segs)
        # Address: remaining segments minus trailing empties, cleaned
        trimmed = [clean(s) for s in addr_segs]
        while trimmed and trimmed[-1] is None:
            trimmed.pop()
        address = ", ".join(s if s is not None else "" for s in trimmed)
        address = re.sub(r"(,\s*)+", ", ", address).strip(" ,") or None
        notes_parts = []
        denial = clean(row.get("Type of Denial"))
        if denial:
            notes_parts.append("Type of denial: " + denial)
        expires = norm_date(row.get("Expiration_Date"))
        if expires:
            notes_parts.append("Expires: " + expires)
        entities.append(entity(
            name=name,
            aliases=aliases,
            country=country,
            address=address,
            effective_date=norm_date(row.get("Effective_Date")),
            federal_register=clean(row.get("Appropriate Federal Register Citations")),
            notes="; ".join(notes_parts) or None,
        ))
    return write_output("bis-dpl", SOURCES["bis_dpl"], entities)


# ------------------------------------------------- 3/4. State Dept debarments
def extract_paren_akas(raw_name):
    """'Ahmed, Tariq (a.k.a. Tariq Amin; X)' -> ('Ahmed, Tariq', ['Tariq Amin', 'X'])."""
    aliases = []

    def grab(m):
        inner = m.group(1)
        for part in re.split(r"[;]", inner):
            part = clean_name(part)
            if part:
                aliases.append(part)
        return " "

    name = PAREN_AKA_RE.sub(grab, raw_name)
    return clean_name(name), aliases


def parse_state_statutory():
    rows = read_csv(SOURCES["state_stat"])
    entities = []
    for row in rows:
        raw = clean(row.get("Party Name")) or ""
        if not raw:
            continue
        name, aliases = extract_paren_akas(raw)
        fr = clean(row.get("Federal Register Notice"))
        corrected = clean(row.get("Corrected Notice"))
        corrected_date = norm_date(row.get("Corrected Notice Date"))
        if corrected:
            fr = (fr or "") + " (corrected by %s%s)" % (
                corrected, ", " + corrected_date if corrected_date else "")
            fr = fr.strip()
        notes_parts = []
        dob = clean(row.get("Date Of Birth"))
        if dob:
            notes_parts.append("Date of birth: " + dob)
        entities.append(entity(
            name=name,
            aliases=aliases,
            effective_date=norm_date(row.get("Notice Date")),
            federal_register=fr,
            notes="; ".join(notes_parts) or None,
        ))
    return write_output("state-debarred-statutory", SOURCES["state_stat"], entities)


def parse_state_admin():
    rows = read_csv(SOURCES["state_admin"])
    entities = []
    for row in rows:
        raw = clean(row.get("Name")) or ""
        if not raw:
            continue
        name, aliases = extract_paren_akas(raw)
        notes_parts = []
        if clean(row.get("Charging Letter")):
            notes_parts.append("Charging letter on file")
        if clean(row.get("Debarment Order")):
            notes_parts.append("Debarment order on file")
        # No reinstatement/status column in this CSV; status stays null.
        status = None
        for key in row:
            if key and re.search(r"reinstat|status", key, re.IGNORECASE):
                status = clean(row.get(key))
        entities.append(entity(
            name=name,
            aliases=aliases,
            status=status,
            effective_date=norm_date(row.get("Date")),
            federal_register=clean(row.get("Federal Register Notice")),
            notes="; ".join(notes_parts) or None,
        ))
    return write_output("state-debarred-admin", SOURCES["state_admin"], entities)


def main():
    for path in SOURCES.values():
        if not os.path.isfile(path):
            sys.exit("Missing source file: %s" % path)
    os.makedirs(OUT_DIR, exist_ok=True)
    outputs = [parse_cbp(), parse_dpl(), parse_state_statutory(), parse_state_admin()]
    # Quality check: print 3 samples per output
    for p in outputs:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        print("\n=== %s | count=%d ===" % (data["list_id"], data["count"]))
        for e in data["entities"][:3]:
            print(json.dumps(e, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
