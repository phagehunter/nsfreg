#!/usr/bin/env python3
"""Build the NSF Restricted Entities Guide from src/ templates and data/.

Every page on the site is generated here, so the header, footer, meta block and
JSON-LD exist once instead of six times, and every number printed on a page is
computed from data/ rather than typed into the markup.

Usage, from the repository root:

    python3 build.py            # build the site
    python3 build.py --check    # build into memory and report, writing nothing

Outputs:
    index.html policy.html lists.html faq.html checklist.html about.html
    assets/lists.js        list metadata, per-list counts and totals (small)
    assets/entities.js     the search index (large, loaded on demand)
    data/derived/nonproliferation_status.json
    sitemap.xml  llms.txt
"""

import argparse
import collections
import hashlib
import html
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
DATA = ROOT / "data"
ASSETS = ROOT / "assets"
DERIVED = DATA / "derived"

LIST_FILES = {
    "dow-1260h": "dow_1260h.json",
    "dow-1286": "dow_1286.json",
    "bis-entity-list": "bis_entity_list.json",
    "bis-meu": "bis_meu.json",
    "bis-dpl": "bis_dpl.json",
    "ofac-eo14032": "ofac_eo14032_annex.json",
    "ofac-nscmic": "ofac_nscmic.json",
    "state-debarred-statutory": "state_debarred_statutory.json",
    "state-debarred-admin": "state_debarred_admin.json",
    "state-nonproliferation": "state_nonproliferation.json",
    "fcc-covered": "fcc_covered.json",
    "dhs-uflpa": "dhs_uflpa.json",
    "cbp-wro": "cbp_wro.json",
}

# Order the lists appear in on the Lists page and the About table.
DISPLAY_ORDER = list(LIST_FILES.keys())

AGENCY_BADGE = {
    "DoW": "dow",
    "Commerce/BIS": "bis",
    "Treasury/OFAC": "ofac",
    "State/DDTC": "state",
    "State/ISN": "state",
    "FCC": "fcc",
    "DHS": "dhs",
    "CBP": "cbp",
}

STATUS_ACTIVE = "Active"
STATUS_HISTORICAL = "Lifted or expired"


# ---------------------------------------------------------------- utilities

def e(s):
    """Escape a value for use in HTML text or an attribute."""
    return html.escape("" if s is None else str(s), quote=True)


def fill(template, mapping):
    """Replace every {{key}} in template. Unknown placeholders are an error."""
    def sub(m):
        key = m.group(1)
        if key not in mapping:
            raise KeyError(f"no value for placeholder {{{{{key}}}}}")
        return str(mapping[key])
    return re.sub(r"\{\{(\w+)\}\}", sub, template)


def norm(s):
    """Search normalization: lowercase, strip diacritics and punctuation."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def thousands(n):
    return f"{n:,}"


# ------------------------------------------------------- derived list status

MEASURE_STATUS = re.compile(r"status:\s*([^;|]+)", re.I)


def classify_measure(raw):
    """Map one measure's status clause onto active / historical."""
    s = raw.strip().rstrip(".")
    low = s.lower()
    if low.startswith("active"):
        return "active", s
    for word in ("lifted", "expired", "terminated", "waived", "ended", "all provisions expired"):
        if low.startswith(word) or word in low:
            return "historical", s
    return "unknown", s


def derive_nonproliferation_status(entities):
    """Give each State/ISN record a status derived from its own notes field.

    Each record's notes field holds one or more measures separated by '|', and
    each measure carries its own 'status:' clause. A record counts as Active
    when any one of its measures is still active; otherwise every measure has
    been lifted, expired, terminated or waived, and the record is historical.
    Records whose notes carry no status clause are left without a status rather
    than guessed at.
    """
    counts = collections.Counter()
    detail_rows = []
    for rec in entities:
        measures = [m.strip() for m in (rec.get("notes") or "").split("|")]
        kinds, texts = [], []
        for m in measures:
            found = MEASURE_STATUS.search(m)
            if not found:
                continue
            kind, text = classify_measure(found.group(1))
            kinds.append(kind)
            texts.append(text)
        if not kinds:
            counts["no status clause"] += 1
            continue
        status = STATUS_ACTIVE if "active" in kinds else STATUS_HISTORICAL
        rec["status"] = status
        rec["status_detail"] = "; ".join(dict.fromkeys(texts))
        counts[status] += 1
        detail_rows.append({
            "name": rec["name"],
            "status": status,
            "measures": texts,
        })
    return counts, detail_rows


# -------------------------------------------------------------- data loading

def load():
    meta = json.loads((DATA / "lists.json").read_text(encoding="utf-8"))
    lists = {l["id"]: l for l in meta["lists"]}
    missing = set(LIST_FILES) - set(lists)
    if missing:
        raise SystemExit(f"lists.json is missing metadata for: {sorted(missing)}")

    per_list = {}
    for lid, fname in LIST_FILES.items():
        path = DATA / fname
        if not path.exists():
            raise SystemExit(f"missing extract: {path}")
        blob = json.loads(path.read_text(encoding="utf-8"))
        if blob["list_id"] != lid:
            raise SystemExit(f"{fname} declares list_id {blob['list_id']}, expected {lid}")
        if blob["count"] != len(blob["entities"]):
            raise SystemExit(
                f"{fname} declares {blob['count']} entries but holds {len(blob['entities'])}")
        per_list[lid] = blob
        lists[lid]["retrieved"] = blob["extracted"]
        lists[lid]["source_file"] = blob["source_file"]
    return meta, lists, per_list


def build_index(lists, per_list):
    """Flatten every extract into the search index and count what is there."""
    records = []
    counts = {}
    gaps = {}
    status_counts = collections.Counter()
    npp_counts, npp_detail = collections.Counter(), []

    for lid in DISPLAY_ORDER:
        blob = per_list[lid]
        entities = blob["entities"]
        if lid == "state-nonproliferation":
            npp_counts, npp_detail = derive_nonproliferation_status(entities)
        counts[lid] = len(entities)
        gaps[lid] = {
            "no_country": sum(1 for x in entities if not x.get("country")),
            "no_address": sum(1 for x in entities if not x.get("address")),
            "total": len(entities),
        }
        for x in entities:
            rec = {"n": x["name"], "l": lid}
            if x.get("aliases"):
                rec["a"] = x["aliases"]
            if x.get("country"):
                rec["c"] = x["country"]
            if x.get("address"):
                rec["ad"] = x["address"][:300]
            if x.get("status"):
                rec["s"] = x["status"]
                status_counts[x["status"]] += 1
            if x.get("status_detail"):
                rec["sd"] = x["status_detail"][:200]
            if x.get("effective_date"):
                rec["d"] = x["effective_date"]
            if x.get("federal_register"):
                rec["fr"] = x["federal_register"][:120]
            if x.get("notes"):
                rec["no"] = x["notes"][:300]
            records.append(rec)

    totals = {
        "entries": len(records),
        "lists": len(DISPLAY_ORDER),
        "agencies": len({lists[lid]["agency_short"].split("/")[0] for lid in DISPLAY_ORDER}),
        "retrieved": max(lists[lid]["retrieved"] for lid in DISPLAY_ORDER),
    }
    return records, counts, totals, gaps, status_counts, npp_counts, npp_detail


# ------------------------------------------------------------ HTML fragments

def nav_html(current, nav):
    out = ['    <nav class="primary" aria-label="Primary">']
    for item in nav:
        href = "index.html" if item["page"] == "index" else f'{item["page"]}.html'
        cur = ' aria-current="page"' if item["page"] == current else ""
        out.append(f'      <a href="{href}"{cur}>{item["label"]}</a>')
    out.append("    </nav>")
    return "\n".join(out)


def snapshot_label(l):
    """Human snapshot label plus a machine-readable date where one exists."""
    pub = l.get("source_published")
    if pub:
        return f'<time datetime="{e(pub)}">{e(l["snapshot"])}</time>'
    return e(l["snapshot"])


def list_cards_html(lists, counts, status_counts_by_list):
    out = ['    <div id="list-cards">']
    for lid in DISPLAY_ORDER:
        l = lists[lid]
        n = counts[lid]
        badge = AGENCY_BADGE.get(l["agency_short"], "")
        extra = ""
        sc = status_counts_by_list.get(lid)
        if sc:
            parts = [f"{thousands(v)} {k.lower()}" for k, v in sc.most_common()]
            extra = f'<dt>Status</dt><dd>{e(", ".join(parts))}</dd>'
        out.append(
            f'      <article class="list-card" id="{e(lid)}">\n'
            f'        <span class="badge {badge}">{e(l["agency"])}</span>\n'
            f'        <h3>{e(l["short_name"])}</h3>\n'
            f'        <p class="official">{e(l["official_name"])}</p>\n'
            f'        <p>{e(l["description"])}</p>\n'
            f"        <dl>\n"
            f'          <dt>Legal basis</dt><dd>{e(l["authority"])}</dd>\n'
            f'          <dt>Updates</dt><dd>{e(l["update_cadence"])}</dd>\n'
            f'          <dt>This snapshot</dt><dd>{snapshot_label(l)} · <strong>{thousands(n)} entries</strong></dd>\n'
            f'          <dt>Retrieved</dt><dd><time datetime="{e(l["retrieved"])}">{e(l["retrieved"])}</time></dd>\n'
            f"          {extra}\n"
            f"        </dl>\n"
            f'        <div class="note"><strong>For researchers:</strong> {e(l["researcher_note"])}</div>\n'
            f'        <p class="list-card-actions"><a class="btn" href="{e(l["official_url"])}" target="_blank" rel="noopener">{e(l["official_url_label"])} ↗</a> '
            f'<a class="btn ghost" href="index.html?list={e(lid)}">Search this snapshot</a></p>\n'
            f"      </article>"
        )
    out.append("    </div>")
    return "\n".join(out)


def snapshot_rows_html(lists, counts):
    rows = ["        <tbody>"]
    for lid in DISPLAY_ORDER:
        l = lists[lid]
        pub = l.get("source_published")
        pub_cell = f'<time datetime="{e(pub)}">{e(pub)}</time>' if pub else \
            f'<span class="muted" title="{e(l["source_published_note"])}">none published</span>'
        rows.append(
            f"          <tr><td>{e(l['short_name'])}</td><td>{e(l['agency_short'])}</td>"
            f"<td>{e(l['snapshot'])}</td><td>{pub_cell}</td>"
            f"<td><time datetime=\"{e(l['retrieved'])}\">{e(l['retrieved'])}</time></td>"
            f"<td class=\"num\">{thousands(counts[lid])}</td>"
            f"<td><a href=\"{e(l['official_url'])}\" target=\"_blank\" rel=\"noopener\">{e(l['official_url_label'])}</a></td></tr>"
        )
    rows.append("        </tbody>")
    return "\n".join(rows)


def data_gaps_html(lists, gaps, npp_counts, totals):
    """State the field-level gaps in the snapshot instead of hiding them."""
    no_country = [(lid, g) for lid, g in gaps.items() if g["no_country"]]
    no_address = [(lid, g) for lid, g in gaps.items() if g["no_address"]]
    no_country.sort(key=lambda kv: -kv[1]["no_country"])
    no_address.sort(key=lambda kv: -kv[1]["no_address"])

    def line(items, field):
        bits = []
        for lid, g in items[:6]:
            bits.append(f'{e(lists[lid]["short_name"])} ({thousands(g[field])} of {thousands(g["total"])})')
        return "; ".join(bits)

    active = npp_counts.get(STATUS_ACTIVE, 0)
    historical = npp_counts.get(STATUS_HISTORICAL, 0)
    return f"""    <h2>What the snapshot does not contain</h2>
    <p>These gaps are counted from the extracted data at build time, so the numbers below describe this exact snapshot.</p>
    <ul>
      <li><strong>No country recorded:</strong> {line(no_country, "no_country")}.</li>
      <li><strong>No address recorded:</strong> {line(no_address, "no_address")}.</li>
      <li><strong>Designations no longer in force:</strong> of the {thousands(active + historical)} State nonproliferation
        records, <strong>{thousands(active)}</strong> still carry at least one active measure and
        <strong>{thousands(historical)}</strong> have had every measure lifted, expired, terminated or waived. Both are kept
        in the index, because a historical designation is often what a reviewer is looking for, and both carry a status badge
        in search results. The <a href="index.html">search page</a> can filter on either.</li>
      <li><strong>Field coverage varies by source.</strong> A blank field means the official publication did not carry that
        field for that entry, not that the entity has no country or address.</li>
    </ul>"""


# --------------------------------------------------------------- JSON-LD

def jsonld_for(page, cfg, ctx, body):
    base = ctx["base_url"]
    author = {"@type": "Person", "name": ctx["author"]["name"], "url": ctx["author"]["url"]}
    url = base + cfg["url"]
    kind = cfg["jsonld"]

    if kind == "website":
        doc = {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": ctx["site_name"],
            "url": base,
            "description": cfg["description"],
            "author": author,
            "potentialAction": {
                "@type": "SearchAction",
                "target": {"@type": "EntryPoint",
                           "urlTemplate": base + "index.html?q={search_term_string}"},
                "query-input": "required name=search_term_string",
            },
        }
    elif kind == "faq":
        qa = re.findall(r"<summary>(.*?)</summary>(.*?)</details>", body, re.S)
        doc = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "url": url,
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": text_of(q),
                    "acceptedAnswer": {"@type": "Answer", "text": text_of(a)},
                }
                for q, a in qa
            ],
        }
    elif kind == "howto":
        steps = []
        for strong in re.findall(r'<label for="[^"]+"><strong>(.*?)</strong>', body, re.S):
            steps.append({"@type": "HowToStep", "name": text_of(strong)})
        doc = {
            "@context": "https://schema.org",
            "@type": "HowTo",
            "name": "Prepare for NSF's prohibition on collaborations with restricted entities",
            "description": cfg["description"],
            "url": url,
            "author": author,
            "step": steps,
        }
    elif kind == "itemlist":
        doc = {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": "U.S. restricted party lists in Appendix A of NSF's July 2026 Dear Colleague Letter",
            "url": url,
            "numberOfItems": ctx["totals"]["lists"],
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i + 1,
                    "name": ctx["lists"][lid]["official_name"],
                    "url": url + "#" + lid,
                }
                for i, lid in enumerate(DISPLAY_ORDER)
            ],
        }
    elif kind == "dataset":
        doc = {
            "@context": "https://schema.org",
            "@type": "Dataset",
            "name": "Snapshot of the U.S. restricted party lists named in NSF's July 2026 Dear Colleague Letter",
            "description": (
                f'{thousands(ctx["totals"]["entries"])} entries extracted from the official publications of '
                f'{ctx["totals"]["lists"]} U.S. restricted party lists, retrieved {ctx["totals"]["retrieved"]}.'
            ),
            "url": url,
            "creator": author,
            "dateModified": ctx["totals"]["retrieved"],
            "isAccessibleForFree": True,
            "license": "https://www.usa.gov/government-works",
            "distribution": [
                {"@type": "DataDownload", "encodingFormat": "application/json",
                 "contentUrl": base + "data/" + LIST_FILES[lid]}
                for lid in DISPLAY_ORDER
            ],
        }
    else:  # article
        doc = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": cfg["og_title"],
            "description": cfg["description"],
            "url": url,
            "author": author,
            "publisher": author,
            "dateModified": ctx["totals"]["retrieved"],
            "isAccessibleForFree": True,
        }
    return json.dumps(doc, ensure_ascii=False, indent=2)


def text_of(fragment):
    """Plain text of an HTML fragment, for JSON-LD values."""
    t = re.sub(r"<[^>]+>", " ", fragment)
    t = html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


# ------------------------------------------------------------------- outputs

def render_site(ctx, write=True):
    base = (SRC / "base.html").read_text(encoding="utf-8")
    head_t = (SRC / "partials" / "head.html").read_text(encoding="utf-8")
    ribbon = (SRC / "partials" / "ribbon.html").read_text(encoding="utf-8").rstrip("\n")
    header_t = (SRC / "partials" / "header.html").read_text(encoding="utf-8").rstrip("\n")
    footer_t = (SRC / "partials" / "footer.html").read_text(encoding="utf-8").rstrip("\n")

    numbers = {
        "entries": thousands(ctx["totals"]["entries"]),
        "lists": str(ctx["totals"]["lists"]),
        "agencies": str(ctx["totals"]["agencies"]),
        "retrieved": ctx["totals"]["retrieved"],
    }
    written = []
    for page, cfg in ctx["site"]["pages"].items():
        body = (SRC / "pages" / f"{page}.html").read_text(encoding="utf-8").rstrip("\n")
        body = fill(body, {
            "total_entities": numbers["entries"],
            "list_cards": ctx["fragments"]["list_cards"],
            "snapshot_rows": ctx["fragments"]["snapshot_rows"],
            "data_gaps": ctx["fragments"]["data_gaps"],
        }) if "{{" in body else body

        cfg = dict(cfg)
        for key in ("title", "description", "og_title"):
            cfg[key] = cfg[key].format(**numbers)

        head = fill(head_t, {
            "title": cfg["title"],
            "description": e(cfg["description"]),
            "canonical": ctx["base_url"] + cfg["url"],
            "og_title": e(cfg["og_title"]),
            "og_description": e(cfg["description"]),
            "og_image_alt": e(ctx["site"]["og_image_alt"].format(**numbers)),
            "jsonld": jsonld_for(page, cfg, ctx, body),
            "v": ctx["version"],
        }).rstrip("\n")

        fineprint = (
            "List data are snapshots of official publications and may lag the live lists."
            if page == "about" else
            'List data are snapshots (see <a href="about.html">per-list dates</a>) of official '
            "publications and may lag the live lists."
        ) + (" Search on this site is a convenience, not a compliance determination. "
             "Verify every result at its official source before acting.")

        scripts = "\n".join(
            f'<script src="assets/{name}.js?v={ctx["version"]}" defer></script>'
            for name in cfg["scripts"]
        )

        out = fill(base, {
            "head": head,
            "ribbon": ribbon,
            "header": fill(header_t, {"nav": nav_html(page, ctx["site"]["nav"])}),
            "body": body,
            "footer": fill(footer_t, {"fineprint": fineprint}),
            "scripts": scripts,
        })
        if write:
            (ROOT / cfg["file"]).write_text(out, encoding="utf-8")
        written.append((cfg["file"], len(out)))
    return written


def write_sitemap(ctx):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for page, cfg in ctx["site"]["pages"].items():
        lines.append(
            f'  <url><loc>{ctx["base_url"]}{cfg["url"]}</loc>'
            f'<lastmod>{ctx["lastmod"]}</lastmod>'
            f'<priority>{cfg["priority"]}</priority></url>')
    lines.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_llms(ctx):
    t = ctx["totals"]
    lists = ctx["lists"]
    rows = "\n".join(
        f'- {lists[lid]["short_name"]} ({lists[lid]["agency_short"]}): '
        f'{thousands(ctx["counts"][lid])} entries, retrieved {lists[lid]["retrieved"]}, '
        f'official source {lists[lid]["official_url"]}'
        for lid in DISPLAY_ORDER)
    text = f"""# NSF Restricted Entities Guide (Independent)

> An independent, static guide to the {t["lists"]} U.S. restricted party lists named in Appendix A of
> NSF's Dear Colleague Letter of July 8, 2026, "Prohibition on Collaborations with Restricted
> Entities". {thousands(t["entries"])} entries extracted from the official publications, searchable in one place.
> Not an NSF or U.S. government website, not a compliance determination, and not legal advice.

Site: {ctx["base_url"]}
Maintainer: {ctx["author"]["name"]} ({ctx["author"]["url"]})
Snapshot retrieved: {t["retrieved"]}
Source repository: https://github.com/phagehunter/nsfreg

## Pages

- {ctx["base_url"]}: search all {thousands(t["entries"])} entries across every list in the snapshot.
- {ctx["base_url"]}policy.html: what the Dear Colleague Letter prohibits, who certifies, and the FY2027 dates.
- {ctx["base_url"]}lists.html: one explainer per list, with legal basis, update cadence and official link.
- {ctx["base_url"]}faq.html: plain-language answers for researchers and research administrators.
- {ctx["base_url"]}checklist.html: preparation checklists for researchers and for institutions.
- {ctx["base_url"]}about.html: provenance, per-list snapshot dates, methodology and known gaps.

## The lists in this snapshot

{rows}

## How the data was produced

Each list was extracted from its official publication by a script in pipeline/ and stored as JSON in
data/. build.py computes every count on the site from those files; no figure on a page is typed by
hand. Designation status for the State nonproliferation list is derived from the per-measure status
clauses carried in each record's own notes field.

## Limits a reader should know

- A snapshot, not the live lists. Several sources change monthly or more often.
- A non-match is not a clearance. Names vary by translation, abbreviation and subsidiary.
- Entities are grouped across lists by exact normalized name only.
- PDF-derived lists can carry extraction artifacts, especially in transliterated names.
"""
    (ROOT / "llms.txt").write_text(text, encoding="utf-8")


def write_assets(ctx, records, write=True):
    lists_payload = {
        "generated": ctx["meta"]["generated"],
        "dcl_url": ctx["meta"]["dcl_url"],
        "lists": {lid: ctx["lists"][lid] for lid in DISPLAY_ORDER},
        "counts": ctx["counts"],
        "totals": ctx["totals"],
        "status_counts": dict(ctx["status_counts"]),
    }
    lists_js = "window.NSF_LISTS=" + json.dumps(
        lists_payload, ensure_ascii=False, separators=(",", ":")) + ";\n"
    entities_js = "window.NSF_ENTITIES=" + json.dumps(
        records, ensure_ascii=False, separators=(",", ":")) + ";\n"
    if write:
        (ASSETS / "lists.js").write_text(lists_js, encoding="utf-8")
        (ASSETS / "entities.js").write_text(entities_js, encoding="utf-8")
    return len(lists_js.encode()), len(entities_js.encode())


def write_derived(npp_detail, npp_counts, write=True):
    payload = {
        "list_id": "state-nonproliferation",
        "derived_by": "build.py derive_nonproliferation_status()",
        "method": (
            "Each record's notes field carries one measure per authority, separated by '|', and each "
            "measure carries its own 'status:' clause. A record is Active when any measure is active; "
            "otherwise every measure has been lifted, expired, terminated or waived."
        ),
        "counts": dict(npp_counts),
        "records": npp_detail,
    }
    if write:
        DERIVED.mkdir(exist_ok=True)
        (DERIVED / "nonproliferation_status.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(npp_detail)


def version_for(paths):
    """Short content hash over the assets the pages reference.

    A file that does not exist yet contributes nothing, so --check still works
    on a fresh clone where the generated assets have not been written.
    """
    h = hashlib.sha256()
    for p in sorted(paths):
        p = Path(p)
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:8]


# ----------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="report what would be built without writing any file")
    args = ap.parse_args()
    write = not args.check

    meta, lists, per_list = load()
    records, counts, totals, gaps, status_counts, npp_counts, npp_detail = build_index(lists, per_list)

    status_by_list = collections.defaultdict(collections.Counter)
    for r in records:
        if r.get("s"):
            status_by_list[r["l"]][r["s"]] += 1

    site = json.loads((SRC / "site.json").read_text(encoding="utf-8"))
    # sitemap lastmod is the later of the data retrieval date and the date the
    # pages themselves last changed, so rebuilding without a change is a no-op.
    lastmod = max(totals["retrieved"], site["site_updated"])
    ctx = {
        "meta": meta,
        "site": site,
        "lists": lists,
        "counts": counts,
        "totals": totals,
        "status_counts": status_counts,
        "base_url": site["base_url"],
        "site_name": site["site_name"],
        "author": site["author"],
        "lastmod": lastmod,
    }

    n_lists_js, n_entities_js = write_assets(ctx, records, write=write)
    n_derived = write_derived(npp_detail, npp_counts, write=write)

    # One cache-busting string for the whole site, derived from the bytes of
    # every asset a page references, so it changes exactly when they do.
    ctx["version"] = version_for([
        ASSETS / name for name in
        ("styles.css", "app.js", "checklist.js", "lists.js", "entities.js")
    ])

    ctx["fragments"] = {
        "list_cards": list_cards_html(lists, counts, status_by_list),
        "snapshot_rows": snapshot_rows_html(lists, counts),
        "data_gaps": data_gaps_html(lists, gaps, npp_counts, totals),
    }

    written = render_site(ctx, write=write)
    if write:
        write_sitemap(ctx)
        write_llms(ctx)

    print(f"{'built' if write else 'checked'} nsfreg  asset version {ctx['version']}")
    print(f"  entries {thousands(totals['entries'])} across {totals['lists']} lists, "
          f"{totals['agencies']} agencies, retrieved {totals['retrieved']}")
    for f, n in written:
        print(f"  {f:16} {n/1024:7.1f} KB")
    print(f"  assets/lists.js    {n_lists_js/1024:7.1f} KB")
    print(f"  assets/entities.js {n_entities_js/1024:7.1f} KB  (loaded on demand)")
    print(f"  derived status for {n_derived} State nonproliferation records: "
          + ", ".join(f"{v} {k}" for k, v in npp_counts.most_common()))
    unknown = [r for r in records if r.get("s") and r["s"] not in (STATUS_ACTIVE, STATUS_HISTORICAL)
               and r["l"] == "state-nonproliferation"]
    if unknown:
        print(f"  WARNING: {len(unknown)} nonproliferation records with an unmapped status")


if __name__ == "__main__":
    main()
