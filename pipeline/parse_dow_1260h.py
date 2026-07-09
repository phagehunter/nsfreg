#!/usr/bin/env python3
"""Parse the June 10, 2026 Federal Register notice (91 FR 35189, FR Doc 2026-11571)
listing DoD Section 1260H "Chinese military companies".

Structure: after the SUPPLEMENTARY INFORMATION intro ends with
"... in accordance with section 1260H:", each entity is a heading
(possibly wrapped over lines, possibly with parenthetical short name /
"formerly" name / "(and X subsidiaries: ...)" clause) followed by one or
more bullet ("•") justification paragraphs, each ending with a
"(Section[s] 1260H...)." citation. A removals section follows
("The Deputy Secretary of Defense has determined that the following
previously listed entities should be removed ..."), then boilerplate and
the signature block. Unrelated adjacent notices share the PDF.
"""
import os
import re
import sys

from pypdf import PdfReader

from common import (BASE_DIR, clean_text, collapse_ws, entity_record,
                    normalize_typography, truncate_note, write_output)

SOURCE = os.path.join(
    BASE_DIR,
    "U.S. Department of War",
    "Sec. 1260H of the National Defense Authorization Act (NDAA) for FY2021",
    "2026-11571.pdf",
)

START_MARKER = "in accordance with section 1260H:"
REMOVAL_MARKER = ("The Deputy Secretary of Defense has determined that the "
                  "following previously listed entities should be removed")
REMOVAL_END_MARKER = 'The list of entities designated as "Chinese military companies" in Mandarin'

FED_REG = "91 FR 35189 (June 10, 2026)"
EFFECTIVE = "2026-06-10"

# Trailing parenthetical words that are part of the name, not an alias.
NAME_PART_PARENS = {"limited", "ltd", "ltd.", "group", "holdings"}


def get_lines():
    reader = PdfReader(SOURCE)
    lines = []
    for page in reader.pages:
        for raw in (page.extract_text() or "").splitlines():
            if re.match(r"^\d{5}\s+Federal Register\s*/\s*Vol\.", raw):
                continue
            if "VerDate Sep" in raw:
                continue
            lines.append(raw.rstrip())
    return lines


def split_trailing_parens(heading):
    """Split a heading into base name + trailing top-level parenthetical groups.

    Only parens at the very end of the heading (possibly several in a row)
    are treated as annotation groups; parens with text after them stay in
    the name (e.g. "SDIC Intelligence (Xiamen) Information Co., Ltd.").
    """
    groups = []  # (start, end, content) of top-level parens
    depth = 0
    start = None
    for i, ch in enumerate(heading):
        if ch == "(":
            if depth == 0:
                start = i
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and start is not None:
                groups.append((start, i, heading[start + 1:i]))
                start = None
    # keep only trailing groups (nothing but whitespace between/after them)
    trailing = []
    end = len(heading)
    for s, e, content in reversed(groups):
        if heading[e + 1:end].strip() == "":
            trailing.insert(0, (s, e, content))
            end = s
        else:
            break
    # re-attach corporate-suffix parens like "(Limited)" to the name
    while trailing and trailing[0][2].strip().lower() in NAME_PART_PARENS:
        end = trailing[0][1] + 1
        trailing.pop(0)
    base = heading[:trailing[0][0]] if trailing else heading[:end] if end != len(heading) else heading
    return collapse_ws(base), [collapse_ws(c) for _, _, c in trailing]


def parse_heading(heading):
    name, parens = split_trailing_parens(heading)
    aliases = []
    subsidiaries = None
    for content in parens:
        low = content.lower()
        if low.startswith("and ") and "subsidiar" in low.split(":")[0]:
            subsidiaries = content.split(":", 1)[1].strip() if ":" in content else content
        elif low.startswith("formerly "):
            aliases.append(collapse_ws(content[len("formerly "):]))
        elif low.startswith("also known as "):
            aliases.append(collapse_ws(content[len("also known as "):]))
        else:
            aliases.append(content)
    return name, aliases, subsidiaries


BULLET_END = re.compile(r"\)\.")


def split_bullet_and_heading(segment):
    """A '•'-delimited segment is [bullet justification][next heading].
    The bullet always ends at the LAST ')."  (citation like
    "(Section 1260H(g)(2)(B)(i)(I))."); headings never contain ').'."""
    last = None
    for m in BULLET_END.finditer(segment):
        last = m
    if last is None:
        return segment.strip(), ""
    return segment[:last.end()].strip(), segment[last.end():].strip()


def ws_tolerant(marker):
    """Regex matching the marker with any whitespace between words."""
    return re.compile(r"\s+".join(re.escape(w) for w in marker.split()))


def main():
    lines = get_lines()
    text = normalize_typography("\n".join(lines))

    m_start = ws_tolerant(START_MARKER).search(text)
    m_removal = ws_tolerant(REMOVAL_MARKER).search(text)
    if not m_start or not m_removal or m_removal.start() < m_start.end():
        sys.exit("FATAL: start/removal markers not found in expected order")
    start_end, removal = m_start.end(), m_removal.start()

    additions_text = clean_text(text[start_end:removal])

    segments = additions_text.split("•")
    entities = []
    pending_heading = segments[0].strip()
    pending_bullets = []

    def flush():
        if not pending_heading:
            return
        name, aliases, subsidiaries = parse_heading(pending_heading)
        note_parts = []
        if subsidiaries:
            note_parts.append("Listed together with subsidiaries: " + subsidiaries.rstrip(".") + ".")
        if pending_bullets:
            note_parts.append(truncate_note(" ".join(pending_bullets)))
        entities.append(entity_record(
            name=name,
            aliases=aliases,
            country="China",
            effective_date=EFFECTIVE,
            federal_register=FED_REG,
            notes=" | ".join(note_parts) if note_parts else None,
        ))

    for seg in segments[1:]:
        bullet, next_heading = split_bullet_and_heading(seg)
        pending_bullets.append(bullet)
        if next_heading:
            flush()
            pending_heading = next_heading
            pending_bullets = []
    flush()

    # ---- removals section (excluded from output; reported) ----
    removal_end = text.find(REMOVAL_END_MARKER.split('"')[0] + '"', removal)
    rem_block = text[removal:removal + 5000]
    rem_start = rem_block.find(":") + 1
    end_pat = re.search(r"The list of entities designated", rem_block)
    rem_lines = [normalize_typography(l).strip()
                 for l in rem_block[rem_start:end_pat.start() if end_pat else None].splitlines()]
    removals, buf = [], ""
    for l in rem_lines:
        if not l:
            continue
        buf = (buf + " " + l).strip()
        if buf.endswith(".") or buf.endswith(")"):
            removals.append(clean_text(buf))
            buf = ""
    if buf:
        removals.append(clean_text(buf))
    # re-attach parenthetical short names that landed on their own line
    merged = []
    for r in removals:
        if r.startswith("(") and merged:
            merged[-1] += " " + r
        else:
            merged.append(r)
    removals = merged

    write_output("dow-1260h", SOURCE, entities, "dow_1260h.json")

    print(f"\nRemoved entities (excluded from output, {len(removals)}):")
    for r in removals:
        print("  -", r)
    print("\nSample entities:")
    for e in entities[:3] + entities[-3:]:
        print("  *", e["name"], "| aliases:", e["aliases"])
    print(f"\nTotal designated entities: {len(entities)}")


if __name__ == "__main__":
    main()
