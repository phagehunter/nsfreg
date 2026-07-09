# Session log — 2026-07-09

Task: parse four U.S. proscribed-party CSV sources into normalized JSON for the
static site. All work confined to pipeline/ and data/.

## Files created
- pipeline/parse_csv_lists.py — combined parser for the four CSV sources
  (CBP WRO/Findings, BIS Denied Persons List, State Dept statutory and
  administrative debarments). Stdlib only, /usr/bin/python3 (3.9).
- data/cbp_wro.json — 67 entities (list_id cbp-wro)
- data/bis_dpl.json — 564 entities (list_id bis-dpl)
- data/state_debarred_statutory.json — 779 entities (list_id state-debarred-statutory)
- data/state_debarred_admin.json — 8 entities (list_id state-debarred-admin)

## Commands with side effects
- /usr/bin/python3 pipeline/parse_csv_lists.py  (run 3x; writes the four JSON
  files above; re-runs overwrite the script's own prior output only)

No pre-existing files were modified or deleted. Source CSVs were read only.

---

# Session log — 2026-07-09 (HTML sources: DHS UFLPA, FCC Covered List)

Task: parse two browser-saved HTML sources into normalized JSON. All work
confined to pipeline/ and data/. Stdlib only (bs4 not installed).

## Files created
- pipeline/parse_fcc_covered.py — parser for the FCC Covered List page
  (html.parser-based table extraction).
- data/fcc_covered.json — 15 entries (list_id fcc-covered): 13 named
  companies + 2 category rows (foreign-produced UAS; foreign-produced
  routers) flagged in notes as "Category listing (not a named company)".
- pipeline/parse_dhs_uflpa.py — parser for the DHS UFLPA Entity List page.
  NOT RUN TO COMPLETION: the saved source HTML
  "Appendix A .../U.S. Department of Homeland Security/UFLPA Entity List/
  UFLPA Entity List _ Homeland Security.html" is 0 bytes (browser save
  captured only CSS/JS/tracker stubs). Script exits 1 with a diagnostic and
  writes nothing. data/dhs_uflpa.json was NOT created — the page must be
  re-saved and the parser re-run. Parsing logic was verified against a
  synthetic fixture in the session scratchpad (since deleted).

## Commands with side effects
- /usr/bin/python3 pipeline/parse_fcc_covered.py  (run 2x; writes
  data/fcc_covered.json; re-runs overwrite its own prior output only)
- /usr/bin/python3 pipeline/parse_dhs_uflpa.py  (exits 1, no output written)

No pre-existing files were modified or deleted. Source HTML was read only.

---

# Session log — 2026-07-09 (PDF sources: DoW 1260H & 1286, OFAC NS-CMIC & EO 14032, State nonproliferation)

Task: parse five PDF sources into normalized JSON. All work confined to
pipeline/ and data/. Used /usr/bin/python3 (3.9) with pypdf and the
pre-installed pdfminer (needed for coordinate-based extraction where pypdf's
text order/spacing was unreliable).

## Files created (pipeline/)
- common.py — shared helpers (typography normalization, dehyphenation,
  whitespace collapse, schema record/writer)
- inspect_pdf.py — ad-hoc page-dump inspection tool
- parse_dow_1260h.py — DoD Sec. 1260H FR notice (2026-11571.pdf)
- parse_dow_1286.py — DoD FY24 Sec. 1286 list
- parse_ofac_nscmic.py — OFAC NS-CMIC list (Dec 16, 2021)
- parse_ofac_eo14032.py — E.O. 14032 Annex
- parse_state_nonproliferation.py — State Dept Master Sanctions List (May 2025)

## Files created/overwritten (data/) — this session's own outputs only
- dow_1260h.json (80 entities)
- dow_1286.json (134 entities)
- ofac_nscmic.json (68 entities)
- ofac_eo14032_annex.json (59 entities)
- state_nonproliferation.json (528 entities)

## Commands with side effects
- /usr/bin/python3 pipeline/parse_*.py — wrote/overwrote the five JSON files
  above (multiple iterations while debugging; re-runs overwrite this
  session's own outputs only).

No deletions, renames, network access, installs, or git operations.
Pre-existing JSONs from other sessions (bis_*, cbp_*, dhs_*, fcc_*,
state_debarred_*) were not touched. Source PDFs were read only.
