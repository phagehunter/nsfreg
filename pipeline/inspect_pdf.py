#!/usr/bin/env python3
"""Quick inspection tool: dump text of a PDF page range to stdout."""
import sys
from pypdf import PdfReader

path = sys.argv[1]
start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
end = int(sys.argv[3]) if len(sys.argv) > 3 else start + 1

r = PdfReader(path)
print(f"== {path} : {len(r.pages)} pages ==", file=sys.stderr)
for i in range(start, min(end, len(r.pages))):
    print(f"\n----- PAGE {i} -----")
    print(r.pages[i].extract_text())
