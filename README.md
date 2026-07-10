# NSF Restricted Entities Guide (Independent)

**Live site: <https://curtishoffmann.com/nsfreg/>**

A static, searchable guide to the U.S. restricted party lists covered by NSF's
July 8, 2026 Dear Colleague Letter, **"Prohibition on Collaborations with
Restricted Entities."** Search 5,900+ entries across all 13 lists (BIS Entity
List, DoW Sec. 1260H & 1286, OFAC NS-CMIC, UFLPA, FCC Covered List, and more)
in one place. Built for NSF-affiliated researchers and research administrators.
Project led by [Curtis Hoffmann](https://curtishoffmann.com) —
[share your feedback](https://forms.gle/FavcasB5Feao7jVG6).

> **Independent.** This site is a community resource — not an NSF or U.S.
> government website, not a compliance determination, and not legal advice.
> Every page links to the authoritative sources.

## What's inside

| Page | Purpose |
|---|---|
| `index.html` | Unified search across a snapshot of all 13 restricted party lists (grouped results, agency filters, alias matching) |
| `policy.html` | The DCL explained in plain language: what's prohibited, who's responsible, key dates, open questions |
| `lists.html` | One explainer per list: legal basis, what's on it, update cadence, official link |
| `faq.html` | Plain-language FAQ for researchers and administrators |
| `checklist.html` | Preparation checklists (researcher track + institution track), progress saved in-browser |
| `about.html` | Data provenance, per-list snapshot dates, methodology, limitations |

Supporting directories:

- `data/` — per-list extracted JSON + `lists.json` metadata (official URLs, authorities, snapshot dates)
- `pipeline/` — Python scripts that parsed each official source, plus `build_index.py` which merges everything into `assets/entities.js`
- `assets/` — stylesheet, search engine (`app.js`), and the bundled search index (`entities.js`)

No build step, no frameworks, no external requests: the site is plain
HTML/CSS/JS and works offline once loaded.

## Deployment

The site is plain static files served by GitHub Pages from this repository's
`main` branch — no build step. Any static host works.

## Test locally

```bash
cd <this folder>
python3 -m http.server 8000
# open http://localhost:8000
```

(Opening `index.html` directly from the file system also works — the search
index is a plain `<script>` bundle, so no server is required.)

## Updating the data

The source lists change often (the BIS Entity List changes many times a year).
To refresh:

1. Download the current official publication for the list(s) that changed
   (links in `data/lists.json` or on the About page).
2. Re-run the matching parser in `pipeline/` (each script's docstring names its
   input), or edit the per-list JSON in `data/` directly for small corrections.
3. Update the `snapshot` string for that list in `data/lists.json`.
4. Rebuild the search bundle:

   ```bash
   python3 pipeline/build_index.py
   ```

5. Commit and push — GitHub Pages redeploys automatically.

## Data caveats

- PDF-derived lists (OFAC, DoW, State nonproliferation) can carry extraction
  artifacts, especially in transliterated names.
- The CBP list intentionally includes revoked historical orders — the site
  shows status badges.
- Entities are grouped across lists by exact normalized name only; the same
  organization under different spellings appears as separate results.
- A non-hit is **not** a clearance. Screen the official
  [Consolidated Screening List](https://www.trade.gov/consolidated-screening-list)
  and the per-list official sources for anything consequential.

## Questions about the policy itself

NSF directs questions to <researchsecurity@nsf.gov>.
