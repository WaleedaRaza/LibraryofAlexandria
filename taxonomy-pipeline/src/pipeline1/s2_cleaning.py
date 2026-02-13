"""Stage 2: Text Cleaning.

Deterministic pipeline that transforms raw extracted text into
clean, readable text. Order of operations matters.

Once clean_text is produced, it is FROZEN. All downstream offsets
reference this exact string. Never modify it after this stage.
"""

from __future__ import annotations
import hashlib
import re
from collections import Counter
from pathlib import Path

from src.schema import CleaningResult
from src.config import Config


# ─── Individual Cleaning Functions ───
# Each returns (cleaned_text, description_of_what_changed)


def strip_repeating_headers(
    text: str, page_boundaries: list[int], threshold: float = 0.5
) -> tuple[str, str | None]:
    """Remove headers/footers that repeat across pages.

    Strategy: extract first and last N characters of each page,
    find strings that appear on >threshold fraction of pages.
    """
    if len(page_boundaries) < 3:
        return text, None

    # Build page slices
    pages = []
    for i, start in enumerate(page_boundaries):
        end = page_boundaries[i + 1] if i + 1 < len(page_boundaries) else len(text)
        pages.append(text[start:end])

    if not pages:
        return text, None

    # Extract first and last lines of each page
    first_lines = []
    last_lines = []
    for page in pages:
        lines = [l.strip() for l in page.strip().split("\n") if l.strip()]
        if lines:
            first_lines.append(lines[0])
        if len(lines) > 1:
            last_lines.append(lines[-1])

    stripped_headers = []

    # Find repeating first lines (headers)
    if first_lines:
        counts = Counter(first_lines)
        for line, count in counts.items():
            if count / len(pages) >= threshold and len(line) > 2:
                stripped_headers.append(line)

    # Find repeating last lines (footers) — but not if they're just numbers
    if last_lines:
        counts = Counter(last_lines)
        for line, count in counts.items():
            if count / len(pages) >= threshold and len(line) > 2:
                # Don't strip if it's just a page number (handled separately)
                if not re.match(r'^\d+$', line.strip()):
                    stripped_headers.append(line)

    if not stripped_headers:
        return text, None

    # Remove the repeating strings
    cleaned = text
    for header in stripped_headers:
        # Escape for regex, strip with surrounding whitespace
        pattern = re.escape(header)
        cleaned = re.sub(r'\n?' + pattern + r'\n?', '\n', cleaned)

    desc = f"stripped repeating: {stripped_headers[:3]}"  # Log first 3
    return cleaned, desc


def strip_page_numbers(
    text: str, page_boundaries: list[int], proximity: int = 20
) -> tuple[str, int]:
    """Remove bare page numbers near page boundaries.

    A bare number (1-4 digits, alone on a line or surrounded by whitespace)
    within `proximity` characters of a page boundary is likely a page number.
    """
    if not page_boundaries:
        return text, 0

    # Find all bare numbers in the text
    # Pattern: number alone on a line, or surrounded by multiple newlines
    bare_number_pattern = re.compile(r'\n\s*(\d{1,4})\s*\n')

    removals = []
    for match in bare_number_pattern.finditer(text):
        num_start = match.start()
        num_end = match.end()
        num_center = (num_start + num_end) // 2

        # Check if this number is near any page boundary
        for boundary in page_boundaries:
            if abs(num_center - boundary) < proximity * 5:
                # Additional check: the number should be plausible as a page number
                num_val = int(match.group(1))
                if 1 <= num_val <= 9999:
                    removals.append((match.start(), match.end(), match.group(1)))
                    break

    if not removals:
        return text, 0

    # Remove from end to start to preserve offsets
    cleaned = text
    for start, end, _num in reversed(removals):
        cleaned = cleaned[:start] + "\n" + cleaned[end:]

    return cleaned, len(removals)


def rejoin_hyphenation(text: str) -> tuple[str, int]:
    """Rejoin words split by hyphen + newline.

    "philoso-\\npher" → "philosopher"

    But preserve real hyphens: "well-known" stays as-is.
    We only rejoin when the hyphen is at a line break.
    """
    # Pattern: word chars, hyphen, newline (optional whitespace), word chars
    pattern = re.compile(r'(\w+)-\n\s*(\w+)')

    count = 0

    def rejoin(match):
        nonlocal count
        left = match.group(1)
        right = match.group(2)
        # Heuristic: if the combined word is all lowercase, likely a broken word
        # If left part ends with a capital or right starts with capital, keep hyphen
        if right[0].isupper():
            return match.group(0)  # Keep as-is (likely a proper noun line break)
        count += 1
        return left + right

    cleaned = pattern.sub(rejoin, text)
    return cleaned, count


def normalize_whitespace(text: str) -> tuple[str, int]:
    """Normalize excessive whitespace.

    - 3+ consecutive newlines → 2 newlines (paragraph break)
    - Tab characters → spaces
    - Form feeds → removed
    - Trailing whitespace on lines → removed
    """
    original_len = len(text)

    # Remove form feeds
    text = text.replace('\f', '')

    # Tabs to spaces
    text = text.replace('\t', ' ')

    # Remove trailing whitespace on each line
    text = re.sub(r'[ \t]+\n', '\n', text)

    # Collapse 3+ newlines to 2 (preserve paragraph breaks)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Collapse multiple spaces to single (but not newlines)
    text = re.sub(r' {2,}', ' ', text)

    # Strip leading/trailing whitespace from whole document
    text = text.strip()

    changes = abs(original_len - len(text))
    return text, changes


def normalize_encoding(text: str) -> tuple[str, int]:
    """Normalize ligatures, smart quotes, and other encoding artifacts."""
    replacements = {
        '\ufb01': 'fi',   # ﬁ
        '\ufb02': 'fl',   # ﬂ
        '\ufb03': 'ffi',  # ﬃ
        '\ufb04': 'ffl',  # ﬄ
        '\u2018': "'",    # left single quote
        '\u2019': "'",    # right single quote
        '\u201c': '"',    # left double quote
        '\u201d': '"',    # right double quote
        '\u2013': '-',    # en dash
        '\u2014': '--',   # em dash
        '\u2026': '...',  # ellipsis
        '\u00a0': ' ',    # non-breaking space
        '\u200b': '',     # zero-width space
        '\u200c': '',     # zero-width non-joiner
        '\u200d': '',     # zero-width joiner
        '\ufeff': '',     # BOM
    }

    count = 0
    for old, new in replacements.items():
        occurrences = text.count(old)
        if occurrences > 0:
            text = text.replace(old, new)
            count += occurrences

    return text, count


# ─── Main Stage Function ───

def run(pdf_path: Path, context: dict, config: Config) -> CleaningResult:
    """Clean raw extracted text.

    Runs cleaning steps in strict order:
    1. Headers/footers
    2. Page numbers
    3. Hyphenation
    4. Whitespace
    5. Encoding

    The output clean_text is FROZEN after this stage.
    """
    extraction = context["s1_extraction"]
    text = extraction.raw_text
    log = []

    cfg = config.pipeline1.cleaning

    # 1. Strip repeating headers/footers
    text, desc = strip_repeating_headers(
        text, extraction.page_boundaries, cfg.header_repeat_threshold
    )
    if desc:
        log.append(desc)

    # 2. Strip page numbers at boundaries
    text, count = strip_page_numbers(
        text, extraction.page_boundaries, cfg.page_number_proximity
    )
    if count:
        log.append(f"stripped_page_numbers: {count} instances")

    # 3. Rejoin hyphenated words
    text, count = rejoin_hyphenation(text)
    if count:
        log.append(f"rejoined_hyphenation: {count} instances")

    # 4. Normalize whitespace
    text, changes = normalize_whitespace(text)
    if changes:
        log.append(f"normalized_whitespace: ~{changes} chars cleaned")

    # 5. Normalize encoding
    text, count = normalize_encoding(text)
    if count:
        log.append(f"normalized_encoding: {count} characters")

    # Compute hash — this is the immutable reference
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    return CleaningResult(
        clean_text=text,
        char_count=len(text),
        word_count=len(text.split()),
        cleaning_log=log,
        content_hash=content_hash,
    )
