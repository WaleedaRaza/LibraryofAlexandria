#!/usr/bin/env python3
"""
Alexandria Library - PDF to Structured Text Extraction

FOUR-PASS HYBRID APPROACH:
1. Regex Pass — cheap, fast, catches obvious "Chapter X" patterns
2. TOC Extraction — for books with clear Table of Contents
3. LLM Pass — only for books where regex found <2 chapters (optional)
4. Fallback — if all fail, create "Full Text" chapter

Usage:
    python -m admin.extract_chapters batch1books/ extracted/
    python -m admin.extract_chapters batch1books/ extracted/ --llm  # Enable LLM pass
    python -m admin.extract_chapters batch1books/single.pdf extracted/  # Single file

Output:
    JSON files per book with:
    - title, author, domain
    - chapters: [{number, title, start_offset, end_offset}]
    - content: full text
"""

import argparse
import json
import re
import uuid
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class Chapter:
    """A detected chapter/section boundary."""
    number: int
    title: str
    start_offset: int
    end_offset: int
    detection_method: str  # 'regex', 'toc', 'llm', 'fallback'


@dataclass
class ExtractedBook:
    """Full extraction result for a book."""
    id: str
    source_file: str
    title: str
    author: str
    domain: str
    word_count: int
    char_count: int
    page_count: int
    chapters: List[Chapter]
    content: str
    extraction_date: str
    extraction_method: str  # Primary method used


# =============================================================================
# TEXT EXTRACTION
# =============================================================================

def extract_text_from_pdf(pdf_path: Path) -> Tuple[str, int]:
    """
    Extract all text from PDF.
    Returns (text, page_count).
    """
    try:
        import pypdf
        
        reader = pypdf.PdfReader(str(pdf_path))
        text_parts = []
        page_count = len(reader.pages)
        
        for page in reader.pages:
            text = page.extract_text()
            if text:
                # Clean up common PDF extraction artifacts
                text = text.replace('\x00', '')  # Null bytes
                text = re.sub(r'\n{3,}', '\n\n', text)  # Excessive newlines
                text_parts.append(text)
        
        full_text = "\n\n".join(text_parts)
        return full_text, page_count
    
    except ImportError:
        print("ERROR: pypdf not installed. Run: pip install pypdf")
        return "", 0
    except Exception as e:
        print(f"ERROR extracting text from {pdf_path.name}: {e}")
        return "", 0


# =============================================================================
# PASS 1: REGEX-BASED CHAPTER DETECTION
# =============================================================================

# Ordered by specificity - check more specific patterns first
CHAPTER_PATTERNS = [
    # Explicit chapter markers with various numbering (strict beginning)
    (r'^CHAPTER\s+([IVXLCDM]+|[0-9]+)(?:[:\.\s]+(.+))?$', 'chapter_explicit'),
    (r'^Chapter\s+([IVXLCDM]+|[0-9]+)(?:[:\.\s]+(.+))?$', 'chapter_explicit'),
    # Handle mangled PDF text like "eBook.comChapter 1" - extract from anywhere
    (r'Chapter\s+([0-9]+)\s*$', 'chapter_num_anywhere'),
    (r'^CHAPTER\s+(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Eleven|Twelve|Thirteen|Fourteen|Fifteen|Sixteen|Seventeen|Eighteen|Nineteen|Twenty)(?:[:\.\s]+(.+))?$', 'chapter_word'),
    (r'^Chapter\s+(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Eleven|Twelve|Thirteen|Fourteen|Fifteen|Sixteen|Seventeen|Eighteen|Nineteen|Twenty)(?:[:\.\s]+(.+))?$', 'chapter_word'),
    
    # Part markers (numbered, roman, or word)
    (r'^PART\s+([IVXLCDM]+|[0-9]+)(?:[:\.\s]+(.+))?$', 'part'),
    (r'^Part\s+([IVXLCDM]+|[0-9]+)(?:[:\.\s]+(.+))?$', 'part'),
    (r'^PART\s+(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)(?:[:\.\s]+(.+))?$', 'part_word'),
    (r'^Part\s+(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)(?:[:\.\s]+(.+))?$', 'part_word'),
    
    # Book markers (for multi-book works like War and Peace)
    (r'^BOOK\s+([IVXLCDM]+|[0-9]+)(?:[:\.\s]+(.+))?$', 'book'),
    (r'^Book\s+([IVXLCDM]+|[0-9]+)(?:[:\.\s]+(.+))?$', 'book'),
    (r'^BOOK\s+(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)(?:[:\.\s]+(.+))?$', 'book_word'),
    (r'^Book\s+(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)(?:[:\.\s]+(.+))?$', 'book_word'),
    
    # Roman numeral only (common in older texts)
    (r'^([IVXLCDM]+)\s*$', 'roman_only'),
    (r'^([IVXLCDM]+)\.\s*$', 'roman_only'),
    
    # Numbered sections (e.g., "1. Introduction")
    (r'^([0-9]+)\.\s+([A-Z][A-Za-z\s]{3,50})$', 'numbered_section'),
    
    # "Title Part One" format (like "1984 Part One")
    (r'^.+\s+Part\s+(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)\s*$', 'title_part'),
]

# Patterns that indicate we should NOT treat as chapter
SKIP_PATTERNS = [
    r'^PAGE\s+\d+',
    r'^\d+$',  # Just a number
    r'^Copyright',
    r'^ISBN',
    r'^Published',
    r'^First\s+Edition',
    r'^Printed\s+in',
    r'^Table\s+of\s+Contents',
    r'^CONTENTS$',
    r'^PREFACE$',
    r'^INTRODUCTION$',
    r'^FOREWORD$',
    r'^ACKNOWLEDGMENTS?$',
    r'^INDEX$',
    r'^BIBLIOGRAPHY$',
    r'^NOTES$',
    r'^APPENDIX',
]


def is_valid_chapter_candidate(line: str, offset: int, text: str, found_chapters: List) -> bool:
    """Check if this line should be considered a chapter start."""
    # Skip if matches exclusion pattern
    for pattern in SKIP_PATTERNS:
        if re.match(pattern, line.strip(), re.IGNORECASE):
            return False
    
    # Skip if too close to start (likely front matter)
    if offset < 500 and len(found_chapters) == 0:
        # Allow if explicitly "Chapter 1"
        if not re.match(r'^(CHAPTER|Chapter)\s+(1|I|One)', line.strip()):
            return False
    
    # Skip if very short content follows
    remaining = text[offset:offset+200]
    if len(remaining.strip()) < 100:
        return False
    
    return True


def detect_chapters_regex(text: str) -> List[Chapter]:
    """
    PASS 1: Detect chapter boundaries using regex patterns.
    """
    chapters = []
    lines = text.split('\n')
    current_offset = 0
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        
        # Skip empty lines
        if not line_stripped:
            current_offset += len(line) + 1
            continue
        
        # Try each pattern
        for pattern, pattern_type in CHAPTER_PATTERNS:
            match = re.match(pattern, line_stripped)
            if match:
                if not is_valid_chapter_candidate(line_stripped, current_offset, text, chapters):
                    break
                
                # Build title from match groups
                groups = match.groups()
                if len(groups) >= 2 and groups[1]:
                    title = f"{line_stripped}"
                else:
                    title = line_stripped
                    # Look ahead for chapter title on next line
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if next_line and len(next_line) < 80 and not re.match(r'^\d+$', next_line):
                            if not any(re.match(p, next_line, re.IGNORECASE) for p in SKIP_PATTERNS):
                                title = f"{line_stripped}: {next_line}"
                
                chapters.append(Chapter(
                    number=len(chapters) + 1,
                    title=title[:200],  # Cap title length
                    start_offset=current_offset,
                    end_offset=0,  # Set later
                    detection_method=f'regex:{pattern_type}'
                ))
                break
        
        current_offset += len(line) + 1
    
    # Calculate end offsets
    for i, ch in enumerate(chapters):
        if i < len(chapters) - 1:
            ch.end_offset = chapters[i + 1].start_offset
        else:
            ch.end_offset = len(text)
    
    return chapters


# =============================================================================
# PASS 2: TABLE OF CONTENTS EXTRACTION
# =============================================================================

def extract_toc_entries(text: str) -> List[Dict]:
    """
    PASS 2: Try to find and parse a Table of Contents.
    Returns list of {title, page_number} entries.
    """
    toc_entries = []
    
    # Find TOC section (usually in first 20% of text)
    search_text = text[:int(len(text) * 0.2)]
    
    # Look for TOC markers
    toc_start_patterns = [
        r'TABLE\s+OF\s+CONTENTS',
        r'CONTENTS\s*\n',
        r'Contents\s*\n',
    ]
    
    toc_start = -1
    for pattern in toc_start_patterns:
        match = re.search(pattern, search_text, re.IGNORECASE)
        if match:
            toc_start = match.end()
            break
    
    if toc_start == -1:
        return []
    
    # Extract lines after TOC marker
    toc_text = search_text[toc_start:toc_start + 5000]
    lines = toc_text.split('\n')
    
    # Pattern for TOC entries: "Title......12" or "Title   12"
    toc_line_patterns = [
        r'^(.+?)[\.\s]{3,}(\d+)\s*$',  # Dotted or spaced
        r'^(.+?)\s{2,}(\d+)\s*$',       # Multiple spaces
        r'^([IVXLCDM]+\.\s+.+?)\s+(\d+)\s*$',  # Roman numeral chapters
    ]
    
    consecutive_empty = 0
    for line in lines:
        line_stripped = line.strip()
        
        if not line_stripped:
            consecutive_empty += 1
            if consecutive_empty > 3 and len(toc_entries) > 2:
                break  # End of TOC
            continue
        
        consecutive_empty = 0
        
        for pattern in toc_line_patterns:
            match = re.match(pattern, line_stripped)
            if match:
                title = match.group(1).strip()
                page = int(match.group(2))
                
                # Skip obvious non-chapters
                if title.lower() in ['preface', 'introduction', 'acknowledgments', 'index', 'bibliography']:
                    continue
                
                toc_entries.append({
                    'title': title,
                    'page': page
                })
                break
    
    return toc_entries


def toc_to_chapters(toc_entries: List[Dict], text: str, page_count: int) -> List[Chapter]:
    """
    Convert TOC entries to chapter boundaries.
    Maps page numbers to text offsets.
    """
    if not toc_entries:
        return []
    
    # Estimate chars per page
    chars_per_page = len(text) / max(page_count, 1)
    
    chapters = []
    for i, entry in enumerate(toc_entries):
        # Estimate offset from page number
        estimated_offset = int((entry['page'] - 1) * chars_per_page)
        
        # Search for actual chapter marker near estimated position
        search_start = max(0, estimated_offset - 500)
        search_end = min(len(text), estimated_offset + 1000)
        search_text = text[search_start:search_end]
        
        # Try to find the chapter title in the text
        title_words = entry['title'].split()[:3]  # First 3 words
        if title_words:
            pattern = r'\b' + r'\s+'.join(re.escape(w) for w in title_words)
            match = re.search(pattern, search_text, re.IGNORECASE)
            if match:
                actual_offset = search_start + match.start()
            else:
                actual_offset = estimated_offset
        else:
            actual_offset = estimated_offset
        
        chapters.append(Chapter(
            number=i + 1,
            title=entry['title'][:200],
            start_offset=actual_offset,
            end_offset=0,
            detection_method='toc'
        ))
    
    # Set end offsets
    for i, ch in enumerate(chapters):
        if i < len(chapters) - 1:
            ch.end_offset = chapters[i + 1].start_offset
        else:
            ch.end_offset = len(text)
    
    return chapters


# =============================================================================
# PASS 3: LLM-BASED DETECTION (OPTIONAL)
# =============================================================================

async def detect_chapters_llm(text: str, title: str) -> List[Chapter]:
    """
    PASS 3: Use LLM to identify chapter structure.
    Only called for books where regex found <2 chapters.
    """
    try:
        from app.config import settings
        import openai
        
        if not settings.OPENAI_API_KEY:
            print("  ⚠️  No OpenAI API key - skipping LLM pass")
            return []
        
        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        
        # Send first ~8000 chars (usually includes TOC or first chapters)
        sample = text[:8000]
        
        prompt = f"""Analyze this text from "{title}" and identify the chapter/section structure.

TEXT SAMPLE:
{sample}

Identify ALL chapters or major sections. For each, provide:
1. number (sequential: 1, 2, 3...)
2. title (the chapter/section title as it appears)
3. marker (the exact text that marks the start - copy it verbatim so I can find it)

Return ONLY a JSON array like:
[
  {{"number": 1, "title": "Chapter 1: The Beginning", "marker": "CHAPTER 1\\nThe Beginning"}},
  {{"number": 2, "title": "Chapter 2: The Journey", "marker": "CHAPTER 2\\nThe Journey"}}
]

If you cannot identify clear chapters, return an empty array: []
"""
        
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=2000
        )
        
        result = response.choices[0].message.content.strip()
        
        # Parse JSON
        if result.startswith('```'):
            result = result.split('```')[1]
            if result.startswith('json'):
                result = result[4:]
        
        parsed = json.loads(result)
        
        if not isinstance(parsed, list):
            return []
        
        chapters = []
        for item in parsed:
            marker = item.get('marker', item.get('title', ''))
            
            # Find marker in text
            offset = text.find(marker)
            if offset == -1:
                # Try fuzzy match
                marker_words = marker.split()[:3]
                if marker_words:
                    pattern = r'\b' + r'\s+'.join(re.escape(w) for w in marker_words)
                    match = re.search(pattern, text, re.IGNORECASE)
                    offset = match.start() if match else 0
            
            chapters.append(Chapter(
                number=item.get('number', len(chapters) + 1),
                title=item.get('title', marker)[:200],
                start_offset=max(0, offset),
                end_offset=0,
                detection_method='llm'
            ))
        
        # Set end offsets
        for i, ch in enumerate(chapters):
            if i < len(chapters) - 1:
                ch.end_offset = chapters[i + 1].start_offset
            else:
                ch.end_offset = len(text)
        
        return chapters
    
    except Exception as e:
        print(f"  ⚠️  LLM detection failed: {e}")
        return []


# =============================================================================
# METADATA PARSING
# =============================================================================

def parse_title_author_from_filename(filename: str) -> Tuple[str, str]:
    """Parse title and author from filename."""
    name = Path(filename).stem
    
    # Handle "Title - Author.pdf" format
    if " - " in name:
        parts = name.rsplit(" - ", 1)  # Split from right to handle titles with dashes
        title = parts[0].strip()
        author = parts[1].strip() if len(parts) > 1 else "Unknown"
        
        # Clean up version markers
        title = re.sub(r'\s*V\s*\d+$', '', title)
        title = re.sub(r'\s*\(\d+\)$', '', title)
    else:
        title = name
        author = "Unknown"
    
    # Clean up common artifacts
    title = re.sub(r'^\d{4}\.\d+\.', '', title)  # Remove year.id prefix
    title = title.replace('_', ' ')
    title = re.sub(r'\s+', ' ', title).strip()
    
    return title, author


def infer_domain(title: str, author: str) -> str:
    """Infer domain from title/author keywords."""
    text = f"{title} {author}".lower()
    
    domain_keywords = {
        "Philosophy": ["stoic", "marcus aurelius", "meditations", "philosophy", "plato", "aristotle", 
                      "nietzsche", "kant", "hegel", "kierkegaard", "spinoza", "ethics", "metaphysics",
                      "sartre", "heidegger", "wittgenstein", "phenomenology", "existential"],
        "Strategy": ["war", "strategy", "sun tzu", "clausewitz", "machiavelli", "prince", "art of war",
                    "game theory", "decision", "conflict"],
        "Technology": ["security", "hacking", "cryptography", "software", "programming", "engineering",
                      "computer", "algorithm", "systems", "distributed", "code", "database"],
        "Psychology": ["psychology", "thinking", "behavior", "mind", "brain", "cognitive", "emotional",
                      "intelligence", "consciousness", "freud", "jung", "habit", "trauma"],
        "Economics": ["economics", "market", "capitalism", "wealth", "money", "trade", "keynes",
                     "hayek", "debt", "capital"],
        "Business": ["business", "management", "leadership", "startup", "entrepreneur", "innovation"],
        "Literature": ["novel", "fiction", "story", "tales", "poetry", "poems"],
        "Religion": ["bible", "quran", "dharma", "buddha", "god", "spiritual", "sacred", "religious",
                    "gospel", "bhagavad", "gita", "zen", "tao"],
        "History": ["history", "civilization", "empire", "revolution", "century", "ancient", "medieval"],
        "Science": ["physics", "biology", "chemistry", "evolution", "darwin", "quantum", "relativity"],
    }
    
    for domain, keywords in domain_keywords.items():
        if any(keyword in text for keyword in keywords):
            return domain
    
    return "General"


# =============================================================================
# MAIN EXTRACTION PIPELINE
# =============================================================================

def process_pdf(
    pdf_path: Path, 
    output_dir: Path, 
    use_llm: bool = False,
    verbose: bool = True
) -> Dict:
    """
    Process a single PDF through the 4-pass extraction pipeline.
    """
    result = {
        'source_file': str(pdf_path),
        'status': 'pending'
    }
    
    # 1. Extract text
    if verbose:
        print(f"  [1/4] Extracting text...")
    text, page_count = extract_text_from_pdf(pdf_path)
    
    if not text or len(text) < 100:
        result['status'] = 'failed'
        result['error'] = 'No text extracted'
        return result
    
    # 2. Parse metadata
    title, author = parse_title_author_from_filename(pdf_path.name)
    domain = infer_domain(title, author)
    
    # 3. PASS 1: Regex detection
    if verbose:
        print(f"  [2/4] Regex chapter detection...")
    chapters = detect_chapters_regex(text)
    detection_method = 'regex'
    
    if verbose:
        print(f"        Found {len(chapters)} chapters via regex")
    
    # 4. PASS 2: TOC extraction (if regex found < 3 chapters)
    if len(chapters) < 3:
        if verbose:
            print(f"  [3/4] TOC extraction...")
        toc_entries = extract_toc_entries(text)
        if toc_entries:
            toc_chapters = toc_to_chapters(toc_entries, text, page_count)
            if len(toc_chapters) > len(chapters):
                chapters = toc_chapters
                detection_method = 'toc'
                if verbose:
                    print(f"        Found {len(chapters)} chapters via TOC")
    else:
        if verbose:
            print(f"  [3/4] TOC extraction... skipped (regex found enough)")
    
    # 5. PASS 3: LLM detection (if enabled and still < 2 chapters)
    if use_llm and len(chapters) < 2:
        if verbose:
            print(f"  [4/4] LLM detection...")
        import asyncio
        try:
            llm_chapters = asyncio.run(detect_chapters_llm(text, title))
            if len(llm_chapters) > len(chapters):
                chapters = llm_chapters
                detection_method = 'llm'
                if verbose:
                    print(f"        Found {len(chapters)} chapters via LLM")
        except Exception as e:
            if verbose:
                print(f"        LLM failed: {e}")
    else:
        if verbose:
            print(f"  [4/4] LLM detection... skipped")
    
    # 6. PASS 4: Fallback
    if not chapters:
        chapters = [Chapter(
            number=1,
            title="Full Text",
            start_offset=0,
            end_offset=len(text),
            detection_method='fallback'
        )]
        detection_method = 'fallback'
        if verbose:
            print(f"        Using fallback (single chapter)")
    
    # Build final result
    book_id = f"book_{uuid.uuid4().hex[:12]}"
    
    extracted = ExtractedBook(
        id=book_id,
        source_file=str(pdf_path),
        title=title,
        author=author,
        domain=domain,
        word_count=len(text.split()),
        char_count=len(text),
        page_count=page_count,
        chapters=chapters,
        content=text,
        extraction_date=datetime.now(timezone.utc).isoformat(),
        extraction_method=detection_method
    )
    
    # Save to JSON
    output_file = output_dir / f"{pdf_path.stem}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        # Convert to dict for JSON serialization
        data = asdict(extracted)
        data['chapters'] = [asdict(ch) for ch in chapters]
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    return {
        'source_file': str(pdf_path),
        'status': 'success',
        'title': title,
        'author': author,
        'domain': domain,
        'word_count': extracted.word_count,
        'chapter_count': len(chapters),
        'detection_method': detection_method,
        'output_file': str(output_file)
    }


def process_directory(
    input_dir: Path, 
    output_dir: Path,
    use_llm: bool = False,
    verbose: bool = True
) -> Dict:
    """Process all PDFs in a directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    pdfs = sorted(input_dir.glob('*.pdf'))
    print(f"\n{'='*60}")
    print(f"ALEXANDRIA PDF EXTRACTION PIPELINE")
    print(f"{'='*60}")
    print(f"Input:  {input_dir}")
    print(f"Output: {output_dir}")
    print(f"PDFs:   {len(pdfs)}")
    print(f"LLM:    {'Enabled' if use_llm else 'Disabled'}")
    print(f"{'='*60}\n")
    
    results = {
        'total': len(pdfs),
        'success': [],
        'failed': [],
        'by_method': {'regex': 0, 'toc': 0, 'llm': 0, 'fallback': 0},
        'low_chapters': [],  # Books with only 1 chapter (needs review)
    }
    
    for i, pdf in enumerate(pdfs):
        print(f"[{i+1:3d}/{len(pdfs)}] {pdf.name[:60]}...")
        
        try:
            result = process_pdf(pdf, output_dir, use_llm=use_llm, verbose=verbose)
            
            if result['status'] == 'success':
                results['success'].append(result)
                method = result.get('detection_method', 'unknown')
                if method in results['by_method']:
                    results['by_method'][method] += 1
                
                if result['chapter_count'] <= 1:
                    results['low_chapters'].append({
                        'file': pdf.name,
                        'title': result.get('title', ''),
                        'chapters': result['chapter_count'],
                        'method': method
                    })
                
                status = f"✅ {result['chapter_count']} ch ({method})"
            else:
                results['failed'].append(result)
                status = f"❌ {result.get('error', 'Unknown error')}"
            
            print(f"        {status}\n")
            
        except Exception as e:
            results['failed'].append({
                'source_file': str(pdf),
                'status': 'failed',
                'error': str(e)
            })
            print(f"        ❌ Exception: {e}\n")
    
    # Save summary
    summary = {
        'extraction_date': datetime.now(timezone.utc).isoformat(),
        'input_directory': str(input_dir),
        'output_directory': str(output_dir),
        'total_pdfs': results['total'],
        'successful': len(results['success']),
        'failed': len(results['failed']),
        'by_detection_method': results['by_method'],
        'needs_review': len(results['low_chapters']),
        'low_chapter_books': results['low_chapters'],
        'failed_books': results['failed']
    }
    
    summary_file = output_dir / '_extraction_summary.json'
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"EXTRACTION COMPLETE")
    print(f"{'='*60}")
    print(f"✅ Successful: {len(results['success'])}/{results['total']}")
    print(f"❌ Failed:     {len(results['failed'])}/{results['total']}")
    print(f"\nDetection Methods:")
    for method, count in results['by_method'].items():
        print(f"  - {method}: {count}")
    print(f"\n⚠️  Needs Review (1 chapter): {len(results['low_chapters'])}")
    print(f"\nSummary saved to: {summary_file}")
    print(f"{'='*60}\n")
    
    return results


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Extract structured text with chapters from PDFs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Process all PDFs in a directory
    python -m admin.extract_chapters batch1books/ extracted/
    
    # Process with LLM enhancement for tricky books
    python -m admin.extract_chapters batch1books/ extracted/ --llm
    
    # Process a single PDF
    python -m admin.extract_chapters batch1books/1984.pdf extracted/
    
    # Quiet mode (less verbose)
    python -m admin.extract_chapters batch1books/ extracted/ -q
"""
    )
    parser.add_argument("input", type=Path, help="Input PDF file or directory")
    parser.add_argument("output", type=Path, help="Output directory for JSON files")
    parser.add_argument("--llm", action="store_true", help="Enable LLM pass for difficult books")
    parser.add_argument("-q", "--quiet", action="store_true", help="Less verbose output")
    
    args = parser.parse_args()
    
    if not args.input.exists():
        print(f"ERROR: Input not found: {args.input}")
        sys.exit(1)
    
    if args.input.is_file():
        # Single file
        args.output.mkdir(parents=True, exist_ok=True)
        result = process_pdf(args.input, args.output, use_llm=args.llm, verbose=not args.quiet)
        if result['status'] == 'success':
            print(f"\n✅ Extracted: {result['title']}")
            print(f"   Chapters: {result['chapter_count']} ({result['detection_method']})")
            print(f"   Output: {result['output_file']}")
        else:
            print(f"\n❌ Failed: {result.get('error', 'Unknown error')}")
            sys.exit(1)
    else:
        # Directory
        process_directory(args.input, args.output, use_llm=args.llm, verbose=not args.quiet)


if __name__ == "__main__":
    main()
