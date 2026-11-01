"""Download the 8 pilot PDFs from the public bucket and dump page text for the eval.

Usage: python eval/extract_pages.py <out_dir>
Writes <out_dir>/pdfs/<slug>.pdf and <out_dir>/text/<slug>.txt (pages joined by "\n\f").
"""
import sys, urllib.request
from pathlib import Path
import pymupdf

sys.path.insert(0, str(Path(__file__).parent))
from gold_v0 import ITEMS

BUCKET = "https://storage.googleapis.com/libxndr-library/books"

def main():
    out = Path(sys.argv[1]); (out / "pdfs").mkdir(parents=True, exist_ok=True); (out / "text").mkdir(exist_ok=True)
    slugs = sorted({g["book"] for _, _, gold, _ in ITEMS for g in gold})
    for slug in slugs:
        pdf = out / "pdfs" / f"{slug}.pdf"
        if not pdf.exists():
            urllib.request.urlretrieve(f"{BUCKET}/{slug}.pdf", pdf)
        doc = pymupdf.open(pdf)
        (out / "text" / f"{slug}.txt").write_text("\n\f".join(page.get_text() for page in doc))
        print(slug, doc.page_count, "pages")

if __name__ == "__main__":
    main()
