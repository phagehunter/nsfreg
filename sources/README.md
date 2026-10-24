# Raw sources for the extraction pipeline

The scripts in `pipeline/` read the official publications and write the JSON in
`data/`. Those publications are not committed here: several are multi-megabyte
PDFs, two are saved web pages, and every one of them is re-published by its
agency under a changing file name, so a copy in this repository would be stale
and misleading within weeks. The extracted JSON in `data/` is the committed,
citable artifact, and each file records the `source_file` it came from and the
date it was extracted.

## Where the files go

By default the pipeline looks in this folder for a directory named
`Appendix A - U.S. Proscribed Party Lists`, laid out by agency exactly as
below. To keep the downloads somewhere else, set `NSFREG_SOURCES` to the folder
that holds that directory:

```bash
export NSFREG_SOURCES="$HOME/Downloads/nsf-prohibitions-july-2026"
python3 pipeline/parse_csv_lists.py
```

Nothing in this folder is tracked by git except this file.

## What each parser expects

Paths are relative to `Appendix A - U.S. Proscribed Party Lists`. File names
are the ones the July 2026 snapshot used; a later download will carry a later
name, and the parser's own constant is where to change it.

| Parser | File | Where it comes from |
|---|---|---|
| `parse_dow_1260h.py` | `U.S. Department of War/Sec. 1260H of the National Defense Authorization Act (NDAA) for FY2021/2026-11571.pdf` | The Federal Register notice PDF, from federalregister.gov. The July 2026 snapshot used the notice of June 10, 2026 (Vol. 91, No. 111). |
| `parse_dow_1286.py` | `U.S. Department of War/Sec. 1286 of the NDAA for FY2019, as amended/FY24 Section 1286 List for public release_V2.pdf` | The Department's public-release PDF of the Section 1286 list. |
| `parse_bis_entity_list.py` | `U.S. Department of Commerce, Bureau of Industry and Security/Entity List/Supplement No. 4 to Part 744—Entity List.txt` | The eCFR text export of 15 CFR Part 744, Supplement No. 4. The export also carries Supplements 5 through 8; the parser selects the Entity List table. |
| `parse_bis_meu.py` | `U.S. Department of Commerce, Bureau of Industry and Security/Military End-User Entities/Supplement No. 7 to Part 744—'Military End-User' (MEU) List.docx` | The eCFR DOCX export of Supplement No. 7. |
| `parse_csv_lists.py` | `U.S. Department of Commerce, Bureau of Industry and Security/Denied Persons/dpl_04142026.csv` | The BIS Denied Persons List CSV export. |
| `parse_csv_lists.py` | `U.S. Customs and Border Protection/Withhold Release Orders & Findings list/withhold-release-orders-findings-fy26-2026-06-23.csv` | The CBP Withhold Release Orders and Findings CSV export. |
| `parse_csv_lists.py` | `U.S. Department of State/Debarred Parties/Statutory Debarments/Stat Debarred Parties_20250825_revised.csv` | The DDTC statutory debarments CSV export. |
| `parse_csv_lists.py` | `U.S. Department of State/Debarred Parties/Administrative Debarments/Admin Debarred Parties_06.01.23.csv` | The DDTC administrative debarments CSV export. |
| `parse_ofac_eo14032.py` | `U.S. Department of Treasury, Office of Foreign Assets Control/Annex of Executive Order 14032/14032.pdf` | The Annex to Executive Order 14032 as issued June 3, 2021. A static document; it does not change. |
| `parse_ofac_nscmic.py` | `U.S. Department of Treasury, Office of Foreign Assets Control/Non-SDN Chinese Military-Industrial Complex Companies/nscmiclist.pdf` | OFAC's Non-SDN Chinese Military-Industrial Complex Companies List PDF. |
| `parse_state_nonproliferation.py` | `U.S. Department of State/Nonproliferation Sanctions/May-2025-Updated-Master-Sanctions.pdf` | The State Department's master nonproliferation sanctions table. Dated to the month only. |
| `parse_fcc_covered.py` | `U.S. Federal Communications Commission/Equipment and Services Covered by Section 2 of The Secure Networks Act/List of Equipment and Services Covered By Section 2 of The Secure Networks Act _ Federal Communications Commission.html` | A browser-saved copy of the FCC Covered List page, saved as "Webpage, Complete". |
| `parse_dhs_uflpa.py` | `U.S. Department of Homeland Security/UFLPA Entity List/UFLPA Entity List _ Homeland Security.html` | A browser-saved copy of the DHS UFLPA Entity List page. |
| `parse_dhs_uflpa_live.py` | `data/source-uflpa-2026-07-09.html` (in the repository) | The live-fetched copy of the same DHS page, committed because it is small. This parser needs no download. |

The official URL for every list is in `data/lists.json` under `official_url`,
and on the Lists page of the site.

## Python dependencies

The CSV, text and HTML parsers use the standard library only. The others need:

| Parser | Needs |
|---|---|
| `parse_dow_1260h.py`, `parse_ofac_eo14032.py`, `pipeline/inspect_pdf.py` | `pypdf` |
| `parse_dow_1286.py`, `parse_state_nonproliferation.py`, `parse_ofac_nscmic.py` | `pdfminer.six` (`parse_ofac_nscmic.py` uses `pypdf` as well) |
| `parse_bis_meu.py` | `python-docx` |

`build.py`, which generates the site, needs the standard library only.

## Refreshing one list

1. Download the current publication and put it at the path above.
2. Run that list's parser. It rewrites one file in `data/`.
3. Update `snapshot`, `source_published` and `source_published_note` for that
   list in `data/lists.json`, and the `extracted` date in the per-list file if
   the parser did not set it.
4. Run `python3 build.py`. Every count on the site, the sitemap `lastmod` and
   the cache-busting string are recomputed from the data.
5. Commit the changed files in `data/`, the regenerated pages, and the
   regenerated `assets/lists.js` and `assets/entities.js`.
