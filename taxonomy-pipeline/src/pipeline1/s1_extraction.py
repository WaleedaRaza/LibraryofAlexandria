"""Stage 1: PDF Text Extraction.

Pure deterministic — no LLM. Extracts raw text, page boundaries,
TOC metadata, and OCR quality heuristics from a PDF.
"""

from __future__ import annotations
import re
from pathlib import Path

import fitz  # PyMuPDF

from src.schema import ExtractionResult, TocEntry
from src.config import Config


def count_gibberish(text: str) -> float:
    """Heuristic: ratio of non-standard characters suggesting OCR artifacts.

    Looks for patterns common in bad OCR:
    - Isolated single characters surrounded by spaces
    - Unusual character sequences
    - Very low word-to-character ratio
    """
    if not text:
        return 1.0

    total_chars = len(text)
    if total_chars == 0:
        return 1.0

    # Count characters that are unusual in normal text
    gibberish_chars = 0
    for ch in text:
        code = ord(ch)
        # Control chars (except newline, tab, carriage return)
        if code < 32 and code not in (9, 10, 13):
            gibberish_chars += 1
        # Replacement character
        elif code == 0xFFFD:
            gibberish_chars += 1

    # Check for OCR-typical patterns: lots of isolated single chars
    isolated = len(re.findall(r'\s[a-zA-Z]\s', text))
    isolated_ratio = isolated / max(total_chars / 100, 1)

    # Word length check — OCR garbage tends to have very short "words"
    words = text.split()
    if words:
        avg_word_len = sum(len(w) for w in words) / len(words)
        short_word_penalty = max(0, (3.0 - avg_word_len) / 3.0)  # penalty if avg < 3
    else:
        short_word_penalty = 1.0

    gibberish_ratio = (gibberish_chars / total_chars) + (isolated_ratio * 0.1) + (short_word_penalty * 0.2)
    return min(gibberish_ratio, 1.0)


def run(pdf_path: Path, context: dict, config: Config) -> ExtractionResult:
    """Extract text from PDF.

    Returns raw text with page break markers, TOC if available,
    and quality heuristics.
    """
    doc = fitz.open(str(pdf_path))

    raw_text = ""
    page_boundaries = []

    for page in doc:
        page_boundaries.append(len(raw_text))
        page_text = page.get_text("text")
        raw_text += page_text
        raw_text += "\n\n"  # Page separator

    # Extract embedded TOC
    toc_raw = doc.get_toc()  # [[level, title, page_num], ...]
    toc_entries = [
        TocEntry(title=entry[1].strip(), page_num=entry[2])
        for entry in toc_raw
        if entry[1].strip()  # Skip empty titles
    ]

    # Quality heuristics
    gibberish_ratio = count_gibberish(raw_text)
    is_ocr = gibberish_ratio > config.pipeline1.extraction.ocr_detection_threshold

    doc.close()

    return ExtractionResult(
        raw_text=raw_text,
        page_count=len(page_boundaries),
        page_boundaries=page_boundaries,
        has_toc=len(toc_entries) > 0,
        toc_entries=toc_entries,
        is_ocr=is_ocr,
        extraction_quality=round(1.0 - gibberish_ratio, 3),
    )
