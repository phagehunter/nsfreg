# Session log — 2026-07-09 — BIS Entity List + MEU List parsers

Files created (no existing files modified or deleted):
- pipeline/parse_bis_entity_list.py — parser for Supplement No. 4 (Entity List) eCFR .txt export
- pipeline/parse_bis_meu.py — parser for Supplement No. 7 (MEU List) .docx
- data/bis_entity_list.json — 3,409 entities, 91 countries
- data/bis_meu.json — 70 entities (China; other MEU countries are [Reserved])

Commands with side effects:
- mkdir -p pipeline/ data/ (under 2026-07-09-nsf-restricted-entities-site/)
- /usr/bin/python3 pipeline/parse_bis_entity_list.py  (writes data/bis_entity_list.json)
- /usr/bin/python3 pipeline/parse_bis_meu.py          (writes data/bis_meu.json)

Sources read (read-only):
- "Appendix A .../U.S. Department of Commerce, Bureau of Industry and Security/Entity List/Supplement No. 4 to Part 744—Entity List.txt"
- "Appendix A .../Military End-User Entities/Supplement No. 7 to Part 744—'Military End-User' (MEU) List.docx"
