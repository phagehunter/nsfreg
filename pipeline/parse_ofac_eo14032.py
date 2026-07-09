#!/usr/bin/env python3
"""Parse the Annex to Executive Order 14032 (86 FR 30145, June 7, 2021).

The order text occupies pages 1-3; the Annex is a plain one-per-line list
of ALL-CAPS company names rendered on pages 4-5 (after the "Annex" line on
page 4 and the "2" page marker on page 5). Names are kept in the original
ALL-CAPS as printed in the Federal Register. All entities are Chinese
companies per the order (country "China").

Prohibitions for Annex-listed persons took effect Aug 2, 2021
(sec. 1(b)(i) of the order); effective_date uses that date.
"""
import os
import re

from pypdf import PdfReader

from common import BASE_DIR, clean_text, entity_record, write_output

SOURCE = os.path.join(
    BASE_DIR,
    "U.S. Department of Treasury, Office of Foreign Assets Control",
    "Annex of Executive Order 14032",
    "14032.pdf",
)

FED_REG = "86 FR 30145 (June 7, 2021)"
EFFECTIVE = "2021-08-02"

SKIP_PATTERNS = (
    r"Federal Register\s*/\s*Vol\.",
    r"^VerDate ",
    r"Billing code",
    r"^\[FR Doc",
    r"Filed \d",
    r"Presidential Documents",
    r"</GPH>",
    r"^khammond",
    r"^Annex$",
    r"^\d+$",
)

NAME_RE = re.compile(r"^[A-Z][A-Z0-9 &().,'’-]+$")


def main():
    reader = PdfReader(SOURCE)
    names = []
    seen_annex = False
    for page in reader.pages[3:5]:
        for raw in (page.extract_text() or "").splitlines():
            line = raw.strip()
            if not line:
                continue
            if line == "Annex":
                seen_annex = True
                continue
            if any(re.search(p, line) for p in SKIP_PATTERNS):
                continue
            if not NAME_RE.match(line):
                continue
            if not seen_annex:
                continue
            names.append(clean_text(line))

    entities = [
        entity_record(
            name=n,
            country="China",
            effective_date=EFFECTIVE,
            federal_register=FED_REG,
            notes="Listed in the Annex to E.O. 14032 (replacing the Annex "
                  "to E.O. 13959)",
        )
        for n in names
    ]

    write_output("ofac-eo14032", SOURCE, entities, "ofac_eo14032_annex.json")
    print("\nSamples:")
    for e in entities[:3] + entities[-3:]:
        print("  *", e["name"])


if __name__ == "__main__":
    main()
