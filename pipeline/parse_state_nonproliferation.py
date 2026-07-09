#!/usr/bin/env python3
"""Parse the State Department Master Sanctions List (May 14, 2025) —
nonproliferation sanctions imposed under 12 statutes/authorities
(CBW Act, CAATSA 231, E.O. 12938, E.O. 13382, Export-Import Bank Act,
Iran and Syria Nonproliferation Act, Iran-Iraq Arms Nonpro Act, Iran
Nonproliferation Act, INKSNA, Missile Sanctions Laws, Nuclear
Proliferation Prevention Act, Transfer of Lethal Military Equipment).

Layout: 97 landscape pages of 6-column tables (Sanction Name | Entity |
Location of Entity | Date Imposed | Status/Date of Expiration | Federal
Register Notice). Column x-positions differ between tables, so column
boundaries are re-derived from each header band (which repeats on every
page). Cells wrap over multiple lines and are sometimes vertically
centered, and pdfminer occasionally merges horizontally adjacent cells
into one text line — so lines are split back into cells at column
boundaries using character coordinates.

Row segmentation: within a table segment the statute (column 1) is
repeated verbatim for every row, so each occurrence of the segment's
first column-1 line marks a new row. Lines appearing above the first
row marker of a page are continuations of the previous page's last row.

Parties appearing multiple times (same or different statute) are merged
into one record; every action (statute, date imposed, status, FR notice)
is recorded in notes.
"""
import os
import re
from datetime import datetime

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTAnno, LTChar, LTTextContainer, LTTextLine

from common import (BASE_DIR, collapse_ws, dehyphenate, entity_record,
                    write_output)

SOURCE = os.path.join(
    BASE_DIR,
    "U.S. Department of State",
    "Nonproliferation Sanctions",
    "May-2025-Updated-Master-Sanctions.pdf",
)

DATE_RE = re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}")

COUNTRY_MAP = {
    "people's republic of china": "China",
    "china": "China",
    "russia": "Russia",
    "russian federation": "Russia",
    "north korea": "North Korea",
    "dprk": "North Korea",
    "south korea": "South Korea",
    "iran": "Iran",
    "syria": "Syria",
    "burma": "Burma",
    "myanmar": "Burma",
    "united arab emirates": "United Arab Emirates",
    "uae": "United Arab Emirates",
    "czech republic": "Czech Republic",
}


def get_lines(page):
    """Return [(y0, x0, [(x0, ch), ...])] for every text line on a page."""
    out = []
    for el in page:
        if not isinstance(el, LTTextContainer):
            continue
        for ln in el:
            if not isinstance(ln, LTTextLine):
                continue
            chars = []
            for ch in ln:
                if isinstance(ch, LTChar):
                    chars.append((ch.x0, ch.get_text()))
                elif isinstance(ch, LTAnno):
                    chars.append((None, ch.get_text()))
            text = collapse_ws("".join(c for _, c in chars))
            if text:
                out.append((ln.y0, ln.x0, chars, text))
    out.sort(key=lambda l: (-l[0], l[1]))
    return out


def keyword_positions(chars, text, keyword):
    """x0 positions where `keyword` starts within a line's text."""
    # map text indices to char x positions
    xs = []
    clean = []
    for x, c in chars:
        for cc in c:
            if cc.isspace():
                continue
            clean.append((x, cc))
    squished = "".join(c for _, c in clean)
    kw = keyword.replace(" ", "")
    pos = []
    i = squished.find(kw)
    while i != -1:
        pos.append(clean[i][0])
        i = squished.find(kw, i + 1)
    return [p for p in pos if p is not None]


def detect_header(lines, start_idx):
    """If lines[start_idx] starts a header band, return (col_xs, band_idx_set)."""
    y0, x0, chars, text = lines[start_idx]
    # header label may wrap: "Sanction Name" or "Sanction" / "Name"
    if not (text.startswith("Sanction Name") or text.split()[0] == "Sanction"):
        return None
    band = [start_idx]
    for j in range(len(lines)):
        if j != start_idx and abs(lines[j][0] - y0) <= 18 and lines[j][0] <= y0 + 9:
            band.append(j)
    cand = {"Entity": [], "Location": [], "Date": [], "Status": [], "Federal": []}
    for j in band:
        _, _, ch, tx = lines[j]
        for kw in cand:
            cand[kw].extend(keyword_positions(ch, tx, kw))
    if not cand["Federal"] or not cand["Location"]:
        return None
    sanction_x = x0
    entity_x = min(cand["Entity"]) if cand["Entity"] else None
    location_x = min(cand["Location"])
    status_x = min(cand["Status"]) if cand["Status"] else None
    fr_x = min(cand["Federal"])
    date_x = None
    for d in sorted(cand["Date"]):
        if d > location_x + 20 and (status_x is None or d < status_x - 5):
            date_x = d
            break
    if None in (entity_x, location_x, date_x, status_x, fr_x):
        return None
    cols = [sanction_x, entity_x, location_x, date_x, status_x, fr_x]
    return cols, set(band)


def split_cells(line, cols):
    """Split a line's characters into the 6 columns."""
    y0, x0, chars, text = line
    bounds = [c - 3.0 for c in cols]
    cells = [""] * len(cols)
    cur = 0
    for x, c in chars:
        if x is not None:
            col = 0
            while col + 1 < len(bounds) and x >= bounds[col + 1]:
                col += 1
            cur = col
        cells[cur] += c
    return [collapse_ws(c) for c in cells]


def norm_name(n):
    return re.sub(r"[^a-z0-9]", "", n.lower())


ALIAS_PREFIX = re.compile(
    r"^\s*(?:and\s+)?(?:aka:?|AKA:?|a\.k\.a\.:?|F\.?K\.?A\.?:?|f\.k\.a\.:?)\s*")


def split_parties(text):
    """Split an Entity cell into [(name, [aliases]), ...].

    E.O. 13382 rows list several parties in one cell, each followed by a
    bracketed alias block: "Name1 [aka A; B] Name2 [aka C]". Parties
    without an alias block cannot be told apart from a wrapped name, so
    they stay part of the preceding/only name (documented caveat).
    """
    parties = []
    pos = 0
    while True:
        i = text.find("[", pos)
        if i == -1:
            tail = collapse_ws(text[pos:]).strip(" ;,")
            if tail and len(tail) > 2:
                parties.append((tail, []))
            break
        name = collapse_ws(text[pos:i]).strip(" ;,")
        if name.endswith(" and"):
            name = name[:-4].rstrip(" ,;")
        j = text.find("]", i)
        block = text[i + 1:j if j != -1 else len(text)]
        aliases = []
        for part in block.split(";"):
            part = collapse_ws(ALIAS_PREFIX.sub("", part)).strip(" ,")
            if part:
                aliases.append(part)
        if name:
            parties.append((name, aliases))
        elif parties:
            parties[-1] = (parties[-1][0], parties[-1][1] + aliases)
        pos = (j + 1) if j != -1 else len(text)
    return parties or [(collapse_ws(text), [])]


ROW_GAP = 17.5  # baselines further apart than this start a new row


def main():
    rows = []  # each: {"cells": [six lists of strings], "page": n}
    warn = []
    state = {"marker": None, "table_changed": True, "rows": rows, "warn": warn}

    CENTER_TOL = 8.0  # centered cell lines may sit this far above the
    # row's first statute line

    def flush_cluster(cluster, cols, pageno):
        """A cluster is one or more physical rows (dense pages leave less
        than ROW_GAP between rows). The statute cell (column 1) repeats
        verbatim for every row, so its first wrapped line is a row anchor."""
        if not cluster or cols is None:
            return
        per_line = [(ln[0], split_cells(ln, cols)) for ln in cluster]

        if state["table_changed"]:
            first_col0 = next((c[0] for _, c in per_line if c[0]), None)
            if first_col0:
                state["marker"] = first_col0
                state["table_changed"] = False
        marker = state["marker"]

        anchor_ys = [y for y, c in per_line if c[0] and c[0] == marker]

        if not anchor_ys:
            cells = [[] for _ in range(6)]
            for _, c in per_line:
                for i, v in enumerate(c):
                    if v:
                        cells[i].append(v)
            col0 = collapse_ws(" ".join(cells[0]))
            has_date = any(DATE_RE.search(v) for v in cells[3])
            if not rows:
                warn.append(f"p{pageno + 1}: dropped orphan cluster {col0[:50]!r}")
            elif col0 and has_date and any(
                    DATE_RE.search(v) for v in rows[-1]["cells"][3]):
                # self-contained row with variant statute wording
                warn.append(f"p{pageno + 1}: statute variant row: {col0[:60]!r}")
                rows.append({"cells": cells, "page": pageno + 1})
            else:
                # continuation of the previous row (page break inside a row)
                for i in range(6):
                    rows[-1]["cells"][i].extend(cells[i])
            return

        # Split the cluster into one row per anchor. Cells are vertically
        # centered, so a tall cell may extend well above its row's anchor
        # line; the true boundary between two rows is the largest vertical
        # gap between the two anchors.
        ys = sorted({y for y, _ in per_line}, reverse=True)
        boundaries = []  # descending y; boundary[j] separates row j and j+1
        for j in range(len(anchor_ys) - 1):
            window = [y for y in ys if anchor_ys[j + 1] <= y <= anchor_ys[j]]
            best_gap, best_mid = -1.0, (anchor_ys[j] + anchor_ys[j + 1]) / 2
            for a, b in zip(window, window[1:]):
                if a - b > best_gap:
                    best_gap, best_mid = a - b, (a + b) / 2
            boundaries.append(best_mid)

        new_rows = [{"cells": [[] for _ in range(6)], "page": pageno + 1}
                    for _ in anchor_ys]
        for y, c in per_line:
            k = 0
            while k < len(boundaries) and y < boundaries[k]:
                k += 1
            for i, v in enumerate(c):
                if v:
                    new_rows[k]["cells"][i].append(v)
        rows.extend(new_rows)

    cols = None
    for pageno, page in enumerate(extract_pages(SOURCE)):
        lines = get_lines(page)
        consumed = set()
        headers = []  # (y, cols)
        for idx, ln in enumerate(lines):
            h = detect_header(lines, idx)
            if h:
                headers.append((ln[0], h[0]))
                consumed |= h[1]
        headers.sort(key=lambda h: -h[0])

        hi = -1
        cluster = []
        prev_y = None
        for idx, ln in enumerate(lines):
            y0, x0, chars, text = ln
            if idx in consumed:
                continue
            if re.match(r"^Page \d+ of \d+$", text):
                continue
            if re.match(r"^Table \d+\s*[:.]", text):
                flush_cluster(cluster, cols, pageno)
                cluster, prev_y = [], None
                state["table_changed"] = True
                continue
            if (re.match(r"^Master Sanctions List", text)
                    or re.match(r"^Updated \w+ \d+, \d{4}$", text)):
                continue
            # crossing a header band flushes the current cluster
            # (flush with the cols the cluster was built under)
            if hi + 1 < len(headers) and headers[hi + 1][0] > y0:
                flush_cluster(cluster, cols, pageno)
                cluster, prev_y = [], None
                while hi + 1 < len(headers) and headers[hi + 1][0] > y0:
                    hi += 1
                cols = headers[hi][1]
            if prev_y is not None and prev_y - y0 > ROW_GAP:
                flush_cluster(cluster, cols, pageno)
                cluster = []
            cluster.append(ln)
            prev_y = y0
        flush_cluster(cluster, cols, pageno)

    # ---- rows -> actions ----
    actions = []
    for r in rows:
        statute, entity, location, date, status, fr = (
            collapse_ws(" ".join(c)) for c in r["cells"])
        if not entity:
            warn.append(f"p{r['page']}: row with empty entity (statute={statute[:40]!r})")
            continue
        dm = DATE_RE.search(date)
        for name, aliases in split_parties(entity):
            name = dehyphenate(name)
            aliases = [dehyphenate(a) for a in aliases]
            # parenthetical alias clause: "Name (aka A, B, and C)"
            pm = re.search(r"\s*\((?:aka|a\.k\.a\.)[:\s]+([^)]*)\)", name)
            if pm:
                for part in re.split(r";|,\s*(?:and\s+)?|\s+and\s+", pm.group(1)):
                    part = collapse_ws(part)
                    if part and part.lower() not in {a.lower() for a in aliases}:
                        aliases.append(part)
                name = collapse_ws(name[:pm.start()] + name[pm.end():])
            # INKSNA successor boilerplate
            succ = re.search(
                r"[;,]?\s*(?:and\s+)?any successors?, sub-?units?, or subsidiar(?:y|ies) thereof\.?$",
                name, re.I)
            note_suffix = None
            if succ:
                name = name[:succ.start()].rstrip(" ;,.")
                note_suffix = ("Designation includes any successor, sub-unit, "
                               "or subsidiary thereof")
            # nationality tag, redundant with the location column
            name = collapse_ws(re.sub(
                r"\s*\([A-Za-z. ]{2,24}\s+(?:entity|entities|national|company)\)$",
                "", name))
            actions.append({
                "entity": name, "aliases": aliases, "statute": statute,
                "location": location,
                "date": dm.group(0) if dm else (date or None),
                "status": status or None, "fr": fr or None,
                "extra_note": note_suffix, "page": r["page"],
            })

    # ---- merge duplicates ----
    merged = {}
    order = []
    for a in actions:
        k = norm_name(a["entity"])
        if k not in merged:
            merged[k] = []
            order.append(k)
        merged[k].append(a)

    def to_iso(d):
        if not d:
            return None
        for fmt in ("%m/%d/%Y", "%m/%d/%y"):
            try:
                return datetime.strptime(d, fmt).date().isoformat()
            except ValueError:
                continue
        return None

    def to_country(loc):
        if not loc:
            return None
        key = loc.rstrip(".").strip().lower()
        if key in COUNTRY_MAP:
            return COUNTRY_MAP[key]
        if len(loc) <= 30 and ";" not in loc and not re.search(
                r"\b(previously|believed|originally|operating|based|residing)\b",
                loc, re.I):
            return loc.rstrip(".").strip()
        return None

    entities = []
    for k in order:
        acts = merged[k]
        first = acts[0]
        note_parts = []
        for a in acts:
            bits = [a["statute"] or "unknown authority"]
            if a["date"]:
                bits.append("imposed " + a["date"])
            if a["status"]:
                bits.append("status: " + a["status"])
            if a["fr"]:
                bits.append(a["fr"])
            note_parts.append("Authority: " + "; ".join(bits))
        extra = next((a["extra_note"] for a in acts if a.get("extra_note")), None)
        if extra:
            note_parts.append(extra)
        loc = next((a["location"] for a in acts if a["location"]), None)
        country = to_country(loc)
        if loc and not country:
            note_parts.append("Location: " + loc)
        aliases = []
        for a in acts:
            for al in a["aliases"]:
                if al.lower() not in {x.lower() for x in aliases}:
                    aliases.append(al)
        entities.append(entity_record(
            name=first["entity"],
            aliases=aliases,
            country=country,
            effective_date=to_iso(first["date"]),
            federal_register=first["fr"],
            notes=" | ".join(note_parts),
        ))

    write_output("state-nonproliferation", SOURCE, entities,
                 "state_nonproliferation.json")
    print(f"Rows parsed: {len(rows)}; actions: {len(actions)}; "
          f"unique parties: {len(entities)}")
    if warn:
        print(f"\nWarnings ({len(warn)}):")
        for w in warn[:20]:
            print("  !", w)
    print("\nSamples:")
    for e in entities[:4] + entities[-4:]:
        print("  *", e["name"], "|", e["country"], "|", e["effective_date"])
        print("     ", (e["notes"] or "")[:140])


if __name__ == "__main__":
    main()
