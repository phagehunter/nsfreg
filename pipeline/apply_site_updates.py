#!/usr/bin/env python3
"""One-time site update (2026-07-09): header credit + feedback link, social
share metadata (Open Graph/Twitter), real favicons, footer share buttons,
SEO tags, and the About-page corrections copy.

Idempotent: skips a page if the utility bar is already present.
Run from site root: python3 pipeline/apply_site_updates.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://curtishoffmann.com/nsfreg"
FORM = "https://forms.gle/FavcasB5Feao7jVG6"

PAGES = {
    "index.html": {
        "og_title": "NSF Restricted Entities Guide — search all 13 U.S. restricted party lists",
        "desc": "Free searchable guide to the U.S. restricted party lists in NSF's July 2026 Dear Colleague Letter. Check collaborators, appointments, and funders across 5,900+ entries from the Entity List, Sec. 1260H, UFLPA, and more.",
    },
    "policy.html": {
        "og_title": "NSF's FY2027 restricted-entity prohibition, explained in plain language",
        "desc": "What NSF's July 8, 2026 Dear Colleague Letter prohibits, who it applies to, what AORs and senior/key personnel must certify, and the key FY2027 dates — explained for researchers.",
    },
    "lists.html": {
        "og_title": "The 13 U.S. restricted party lists in NSF's prohibition, one by one",
        "desc": "Plain-language explainers for every restricted party list in Appendix A of NSF's DCL: legal basis, maintaining agency, what entities appear, and links to the authoritative sources.",
    },
    "faq.html": {
        "og_title": "NSF restricted entities prohibition — FAQ for researchers",
        "desc": "When does NSF's restricted-entity prohibition take effect? What counts as collaboration? What must be certified? Plain-language answers for NSF-funded researchers and administrators.",
    },
    "checklist.html": {
        "og_title": "Compliance checklist for NSF's FY2027 restricted-entity prohibition",
        "desc": "Step-by-step preparation checklists for PIs, senior/key personnel, and research administrators ahead of NSF's FY2027 prohibition on collaborations with restricted entities.",
    },
    "about.html": {
        "og_title": "About the NSF Restricted Entities Guide — data & methodology",
        "desc": "How this independent guide was built: per-list snapshot dates, extraction methodology, known limitations, and the official sources every result should be verified against.",
    },
}

UTILITY = (
    '  <div class="utility">\n'
    '    <div class="wrap">\n'
    '      <span>Project led by <a href="https://curtishoffmann.com" target="_blank" rel="noopener">Curtis Hoffmann</a></span>\n'
    f'      <a class="feedback" href="{FORM}" target="_blank" rel="noopener">Share Your Feedback ↗</a>\n'
    "    </div>\n"
    "  </div>\n"
)

SHARE_TEXT = (
    "NSF will prohibit collaboration with restricted entities on NSF-funded projects starting FY2027. "
    "Search all 13 U.S. restricted party lists in one place: " + BASE + "/"
)


def urlenc(s):
    from urllib.parse import quote
    return quote(s, safe="")


SHARE = (
    '      <div class="share" aria-label="Share this guide">\n'
    '        <span class="share-label">Share this guide:</span>\n'
    f'        <a class="share-btn" href="https://www.linkedin.com/sharing/share-offsite/?url={urlenc(BASE + "/")}" target="_blank" rel="noopener">'
    '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M20.45 20.45h-3.55v-5.57c0-1.33-.03-3.04-1.85-3.04-1.86 0-2.14 1.45-2.14 2.94v5.67H9.35V9h3.41v1.56h.05c.47-.9 1.63-1.85 3.36-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28zM5.34 7.43a2.06 2.06 0 1 1 0-4.12 2.06 2.06 0 0 1 0 4.12zM7.12 20.45H3.56V9h3.56v11.45z"/></svg>'
    "LinkedIn</a>\n"
    f'        <a class="share-btn" href="https://bsky.app/intent/compose?text={urlenc(SHARE_TEXT)}" target="_blank" rel="noopener">'
    '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 10.8c-1.09-2.12-4.06-6.07-6.82-8.02C2.53.9 1.52 1.22.86 1.52.09 1.87 0 3.05 0 3.74c0 .7.38 5.7.63 6.53.82 2.75 3.73 3.68 6.42 3.38-3.94.58-7.44 2.02-2.85 7.12 5.05 5.23 6.92-1.12 7.8-4.34.88 3.22 1.9 9.34 7.72 4.34 4.36-4.34 1.16-6.54-2.78-7.12 2.69.3 5.6-.63 6.42-3.38.25-.83.63-5.84.63-6.53 0-.7-.09-1.87-.86-2.22-.66-.3-1.67-.62-4.32 1.26C16.06 4.73 13.1 8.68 12 10.8z"/></svg>'
    "Bluesky</a>\n"
    f'        <a class="share-btn" href="mailto:?subject={urlenc("NSF Restricted Entities Guide")}&amp;body={urlenc(SHARE_TEXT)}">'
    '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m2 7 10 7L22 7"/></svg>'
    "Email</a>\n"
    "      </div>\n"
)

JSONLD_INDEX = """<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "WebSite",
  "name": "NSF Restricted Entities Guide (Independent)",
  "url": "%s/",
  "description": "Independent searchable guide to the U.S. restricted party lists covered by NSF's July 2026 prohibition on collaborations with restricted entities.",
  "author": {"@type": "Person", "name": "Curtis Hoffmann", "url": "https://curtishoffmann.com"},
  "potentialAction": {
    "@type": "SearchAction",
    "target": {"@type": "EntryPoint", "urlTemplate": "%s/index.html?q={search_term_string}"},
    "query-input": "required name=search_term_string"
  }
}
</script>""" % (BASE, BASE)


def head_block(page, cfg):
    canon = f"{BASE}/" if page == "index.html" else f"{BASE}/{page}"
    lines = [
        f'<link rel="canonical" href="{canon}">',
        '<meta name="author" content="Curtis Hoffmann">',
        '<meta name="robots" content="index, follow">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:url" content="{canon}">',
        f'<meta property="og:title" content="{cfg["og_title"]}">',
        f'<meta property="og:description" content="{cfg["desc"]}">',
        f'<meta property="og:image" content="{BASE}/assets/og-card.png">',
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        '<meta property="og:image:alt" content="NSF Restricted Entities Guide — search 5,900+ entries across all 13 U.S. restricted party lists">',
        '<meta property="og:site_name" content="NSF Restricted Entities Guide (Independent)">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{cfg["og_title"]}">',
        f'<meta name="twitter:description" content="{cfg["desc"]}">',
        f'<meta name="twitter:image" content="{BASE}/assets/og-card.png">',
        '<link rel="icon" href="assets/favicon.svg" type="image/svg+xml">',
        '<link rel="icon" href="assets/favicon-32.png" sizes="32x32" type="image/png">',
        '<link rel="icon" href="assets/favicon-192.png" sizes="192x192" type="image/png">',
        '<link rel="apple-touch-icon" href="assets/apple-touch-icon.png">',
    ]
    if page == "index.html":
        lines.append(JSONLD_INDEX)
    return "\n".join(lines) + "\n"


def main():
    for page, cfg in PAGES.items():
        p = ROOT / page
        html = p.read_text(encoding="utf-8")
        if 'class="utility"' in html:
            print(f"{page}: already updated, skipping")
            continue

        # 1. replace inline data-URI favicon with real favicon set + meta block
        html, n = re.subn(
            r'^<link rel="icon" href="data:image/svg\+xml.*$\n',
            head_block(page, cfg),
            html,
            count=1,
            flags=re.M,
        )
        assert n == 1, f"{page}: favicon anchor not found"

        # 2. refresh the meta description to the richer SEO copy
        html, n = re.subn(
            r'<meta name="description" content="[^"]*">',
            f'<meta name="description" content="{cfg["desc"]}">',
            html,
            count=1,
        )
        assert n == 1, f"{page}: description not found"

        # 3. utility bar at top of header
        html, n = re.subn(
            r'(<header class="site">\n)',
            r"\1" + UTILITY,
            html,
            count=1,
        )
        assert n == 1, f"{page}: header anchor not found"

        # 4. share row above footer fineprint
        html, n = re.subn(
            r'(\n\s*<p class="fineprint">)',
            "\n" + SHARE + r"\1",
            html,
            count=1,
        )
        assert n == 1, f"{page}: fineprint anchor not found"

        p.write_text(html, encoding="utf-8")
        print(f"{page}: updated")

    # 5. About page corrections copy
    p = ROOT / "about.html"
    html = p.read_text(encoding="utf-8")
    new_corr = (
        "<p>Spotted an extraction error or a stale snapshot? Submit your feedback "
        f'<a href="{FORM}" target="_blank" rel="noopener">here</a>. '
        "You can also open an issue or pull request on this site's GitHub repository — the per-list JSON in "
        "<code>data/</code> and parsers in <code>pipeline/</code> make fixes straightforward.</p>"
    )
    html, n = re.subn(
        r"<p>Spotted an extraction error or a stale snapshot\?.*?</p>",
        new_corr,
        html,
        count=1,
        flags=re.S,
    )
    if n:
        p.write_text(html, encoding="utf-8")
        print("about.html: corrections copy updated")
    else:
        print("about.html: corrections copy already updated or not found")


if __name__ == "__main__":
    main()
