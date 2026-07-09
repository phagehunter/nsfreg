#!/usr/bin/env python3
"""Merge per-list JSON extracts (data/*.json) + lists.json metadata into the
site search bundle (assets/entities.js).

Run from the site root:  python3 pipeline/build_index.py
"""
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "assets" / "entities.js"

LIST_FILES = [
    "dow_1260h.json",
    "dow_1286.json",
    "bis_entity_list.json",
    "bis_meu.json",
    "bis_dpl.json",
    "ofac_eo14032_annex.json",
    "ofac_nscmic.json",
    "state_debarred_statutory.json",
    "state_debarred_admin.json",
    "state_nonproliferation.json",
    "fcc_covered.json",
    "dhs_uflpa.json",
    "cbp_wro.json",
]


def norm(s):
    """Search normalization: lowercase, strip diacritics and punctuation."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    meta = json.loads((DATA / "lists.json").read_text())
    list_ids = {l["id"] for l in meta["lists"]}

    records = []
    counts = {}
    missing = []
    for fname in LIST_FILES:
        path = DATA / fname
        if not path.exists():
            missing.append(fname)
            continue
        blob = json.loads(path.read_text())
        lid = blob["list_id"]
        assert lid in list_ids, f"unknown list_id {lid} in {fname}"
        counts[lid] = len(blob["entities"])
        for e in blob["entities"]:
            rec = {
                "n": e["name"],
                "l": lid,
            }
            if e.get("aliases"):
                rec["a"] = e["aliases"]
            if e.get("country"):
                rec["c"] = e["country"]
            if e.get("address"):
                rec["ad"] = e["address"][:300]
            if e.get("status"):
                rec["s"] = e["status"]
            if e.get("effective_date"):
                rec["d"] = e["effective_date"]
            if e.get("federal_register"):
                rec["fr"] = e["federal_register"][:120]
            if e.get("notes"):
                rec["no"] = e["notes"][:300]
            # precomputed search key: name + aliases (country searched separately)
            rec["k"] = norm(" | ".join([e["name"]] + (e.get("aliases") or [])))
            records.append(rec)

    bundle = {
        "generated": meta["generated"],
        "dcl_url": meta["dcl_url"],
        "lists": {l["id"]: l for l in meta["lists"]},
        "counts": counts,
        "entities": records,
    }
    OUT.parent.mkdir(exist_ok=True)
    js = "window.NSF_DATA=" + json.dumps(bundle, ensure_ascii=False, separators=(",", ":")) + ";"
    OUT.write_text(js, encoding="utf-8")

    total = sum(counts.values())
    print(f"Wrote {OUT} ({OUT.stat().st_size/1e6:.2f} MB)")
    print(f"Total entities: {total}")
    for lid, n in counts.items():
        print(f"  {lid}: {n}")
    if missing:
        print("MISSING (not yet extracted):", ", ".join(missing))


if __name__ == "__main__":
    main()
