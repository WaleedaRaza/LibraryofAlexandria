"""Check every gold anchor against extracted page text.

Usage: python eval/verify_gold.py <text_dir> [--jsonl out.jsonl]
<text_dir> holds one <asset-slug>.txt per book, pages separated by "\n\f".
"""
import json, re, sys, unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gold_v0 import ITEMS

def norm(s):
    s = unicodedata.normalize("NFKC", s)
    for a, b in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), ("—", "-"), ("–", "-")):
        s = s.replace(a, b)
    s = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", s)
    return re.sub(r"\s+", " ", s)

def main():
    text_dir = Path(sys.argv[1])
    pages = {}
    def book_pages(slug):
        if slug not in pages:
            pages[slug] = [norm(p) for p in (text_dir / f"{slug}.txt").read_text().split("\n\f")]
        return pages[slug]
    bad, rows = 0, []
    for i, (q, kind, gold, decoys) in enumerate(ITEMS, 1):
        for gd in gold:
            p = book_pages(gd["book"])
            if gd["anchor"] not in p[gd["page"] - 1]:
                found = [n + 1 for n, t in enumerate(p) if gd["anchor"] in t]
                print(f"MISS q{i:03} {gd['book'][:20]} p{gd['page']} found_on={found} :: {gd['anchor'][:60]}")
                bad += 1
        rows.append({"id": f"q{i:03}", "question": q, "type": kind, "gold": gold, "decoy_pages": decoys})
    print(f"{len(ITEMS)} questions, {sum(len(r['gold']) for r in rows)} gold passages, {bad} anchors missing")
    if "--jsonl" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--jsonl") + 1])
        out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()
