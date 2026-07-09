#!/usr/bin/env python3
"""Parse the DoD FY24 Section 1286 list (NDAA FY2019, as amended).

Layout (discovered via pdfminer coordinates):
  - Page 1 (index 0): introduction — skipped.
  - Pages 2-10: "Table 1: List of Institutions ..." — one institution per
    line at x0 ~ 77-78; continuation lines of a wrapped name indented at
    x0 ~ 94; alias bullets ("•") at x0 ~ 95-96; continuation of a wrapped
    bullet at x0 ~ 114. Entries ending in "a.k.a." carry alias bullets.
    Some bullets are emitted by pdfminer as a bare "•" fragment plus a
    separate text fragment at the same y — fragments sharing a baseline
    are merged before classification.
  - Page 11 (index 10): "Table 2: Foreign Talent Recruitment Programs ..."
    — same format, no bullets; the final catch-all sentence ("Any program
    that meets one of the criteria ...") is not an entity and is skipped.

The source does not state a per-entity country, so country is null.
Word cross-reference artifacts ("Error! Bookmark not defined.") and
superscript footnote markers are stripped.
"""
import os
import re

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTTextLine

from common import BASE_DIR, clean_text, entity_record, write_output

SOURCE = os.path.join(
    BASE_DIR,
    "U.S. Department of War",
    "Sec. 1286 of the NDAA for FY2019, as amended",
    "FY24 Section 1286 List for public release_V2.pdf",
)

MAIN_MAX = 85.0     # main entry lines start below this x0
BULLET_MAX = 106.0  # bullet / main-continuation indent band
Y_TOL = 3.0         # fragments within this vertical distance share a line

NOTE_T1 = ("FY2024 Section 1286 list, Table 1: institutions with specified "
           "characteristics (PRC, Russian Federation, and other countries)")
NOTE_T2 = ("FY2024 Section 1286 list, Table 2: foreign talent recruitment "
           "programs that pose a threat to national security interests")


def get_logical_lines():
    """Yield (page_index, x0, text) with same-baseline fragments merged."""
    for i, page in enumerate(extract_pages(SOURCE)):
        frags = []
        for el in page:
            if isinstance(el, LTTextContainer):
                for ln in el:
                    if isinstance(ln, LTTextLine):
                        t = ln.get_text().strip()
                        if t:
                            frags.append((ln.y0, ln.x0, t))
        frags.sort(key=lambda f: (-f[0], f[1]))
        clusters = []  # list of lists of (y0, x0, text) sharing a baseline
        for y0, x0, t in frags:
            if clusters and abs(clusters[-1][0][0] - y0) < Y_TOL:
                clusters[-1].append((y0, x0, t))
            else:
                clusters.append([(y0, x0, t)])
        for cl in clusters:
            cl.sort(key=lambda f: f[1])  # assemble left-to-right
            yield (i, cl[0][0], cl[0][1], " ".join(f[2] for f in cl))


def clean_name(s):
    s = s.replace("Error! Bookmark not defined.", "")
    s = clean_text(s)
    s = re.sub(r"(?<=[)a-z])\d$", "", s)  # trailing superscript footnote marker
    return s.strip()


def main():
    entries = []
    table = 0
    cur = None
    cur_target = None
    skipping = False

    for pageno, y0, x0, text in get_logical_lines():
        if pageno == 0:
            continue
        if pageno == 1 and y0 > 640:      # FY24 / Table 1 title block
            continue
        if re.match(r"^\d{1,2}$", text):  # bottom-center page number
            continue
        if text.startswith("Table 2"):
            table = 2
            cur_target = None
            skipping = True               # swallow wrapped title ("Interests")
            continue
        if table == 0:
            table = 1
        if text.startswith("Any program that meets"):
            # final catch-all sentence — not an entity; nothing follows it
            break
        if skipping:
            if x0 >= MAIN_MAX or (table == 2 and text == "Interests"):
                continue
            skipping = False

        if x0 < MAIN_MAX:
            if cur:
                entries.append(cur)
            cur = {"name": [text], "aliases": [], "table": table}
            cur_target = cur["name"]
        elif x0 < BULLET_MAX and text.startswith("•"):
            if cur is None:
                continue
            cur["aliases"].append([text.lstrip("• ").strip()])
            cur_target = cur["aliases"][-1]
        else:
            # wrapped continuation of whatever came last (name or bullet)
            if cur_target is not None:
                cur_target.append(text)
    if cur:
        entries.append(cur)

    entities = []
    for e in entries:
        raw = clean_text(" ".join(p for p in e["name"] if p))
        has_aka = bool(re.search(r"a\.k\.a\.?\s*$", raw))
        name = clean_name(re.sub(r"\s*a\.k\.a\.?\s*$", "", raw))
        aliases = [a for a in (clean_name(" ".join(p for p in al if p))
                               for al in e["aliases"]) if a]
        # An alias beginning with "(...)" is a hanging parenthetical that
        # belongs to the end of the previous alias (bullet text indented at
        # the wrap level shares its baseline with the next bare bullet).
        fixed = []
        for a in aliases:
            m = re.match(r"^(\([^)]*\))\s*(.*)$", a)
            if m and fixed:
                fixed[-1] += " " + m.group(1)
                if m.group(2):
                    fixed.append(m.group(2))
            else:
                fixed.append(a)
        aliases = fixed
        if aliases and not has_aka:
            print(f"  WARN: aliases without a.k.a. marker on {name!r}")
        if "a.k.a" in name:
            print(f"  WARN: residual a.k.a. inside name {name!r}")
        entities.append(entity_record(
            name=name,
            aliases=aliases,
            country=None,
            notes=NOTE_T1 if e["table"] == 1 else NOTE_T2,
        ))

    write_output("dow-1286", SOURCE, entities, "dow_1286.json")

    t1 = [e for e in entities if "Table 1" in e["notes"]]
    t2 = [e for e in entities if "Table 2" in e["notes"]]
    print(f"Table 1 institutions: {len(t1)}; Table 2 talent programs: {len(t2)}")
    print("\nSamples:")
    for e in entities[:3] + t1[-2:] + t2:
        print("  *", e["name"], "| aliases:", e["aliases"])


if __name__ == "__main__":
    main()
