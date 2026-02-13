#!/usr/bin/env python3
"""
Alexandria Taxonomy Engine - System A

Implements the 4-pass local LLM pipeline as specified in manifest.md.

STAGE 1: Text Extraction (PyMuPDF)
STAGE 2: Structural Analysis (LLM Pass 1)
STAGE 3: Section Boundary Detection (LLM Pass 2)
STAGE 4: Section Enrichment (LLM Pass 3)
STAGE 5: Book-Level Synthesis (LLM Pass 4)
STAGE 6: Validation + Artifact Write

Usage:
    python -m admin.taxonomy_engine batch1books/Meditations.pdf artifacts/
    python -m admin.taxonomy_engine batch1books/ artifacts/ --batch
    python -m admin.taxonomy_engine batch1books/ artifacts/ --resume  # Resume from checkpoint
"""

import argparse
import json
import hashlib
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import time

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class SectionBoundary:
    """A detected section boundary."""
    level: int  # 1=major, 2=sub, 3=sub-sub
    type: str  # part, chapter, section, entry
    title: str
    start_offset: int
    end_offset: Optional[int] = None  # Set after all boundaries detected


@dataclass
class EnrichedSection:
    """Section with enrichment data."""
    id: str
    level: int
    type: str
    number: Optional[int]
    title: str
    start_offset: int
    end_offset: int
    word_count: int
    reading_time_minutes: int
    summary: str
    key_themes: List[str]
    notable_passages: List[Dict]
    difficulty: str
    subsections: List[Dict] = None
    connects_to: List[str] = None


# =============================================================================
# STAGE 1: TEXT EXTRACTION (PyMuPDF)
# =============================================================================

def extract_text_with_pymupdf(pdf_path: Path) -> Tuple[str, int, Optional[Dict]]:
    """
    Extract text from PDF using PyMuPDF (fitz).
    Returns: (full_text, page_count, toc_metadata)
    """
    try:
        import fitz  # PyMuPDF
        
        doc = fitz.open(str(pdf_path))
        page_count = len(doc)
        
        # Extract text per page, preserving page boundaries
        text_parts = []
        for page_num in range(page_count):
            page = doc[page_num]
            text = page.get_text()
            if text:
                # Clean up common extraction artifacts
                text = text.replace('\x00', '')
                text = text.replace('\r\n', '\n')
                # Preserve double newlines for paragraph breaks
                text_parts.append(text)
        
        full_text = "\n\n".join(text_parts)
        
        # Extract TOC if available
        toc = doc.get_toc() if hasattr(doc, 'get_toc') else None
        toc_metadata = None
        if toc:
            toc_metadata = {
                'entries': toc,
                'has_toc': True
            }
        
        doc.close()
        return full_text, page_count, toc_metadata
    
    except ImportError:
        print("ERROR: PyMuPDF not installed. Run: pip install pymupdf")
        return "", 0, None
    except Exception as e:
        print(f"ERROR extracting text from {pdf_path.name}: {e}")
        return "", 0, None


# =============================================================================
# LLM CLIENT (Ollama)
# =============================================================================

class OllamaClient:
    """Client for local Ollama LLM."""
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.1:8b"):
        self.base_url = base_url
        self.model = model
    
    def generate(self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 2000) -> str:
        """Generate text using Ollama API."""
        try:
            import requests
            
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.3  # Lower temp for structured tasks
                }
            }
            
            if system_prompt:
                payload["system"] = system_prompt
            
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=120
            )
            response.raise_for_status()
            
            result = response.json()
            return result.get("response", "")
        
        except ImportError:
            print("ERROR: requests not installed. Run: pip install requests")
            return ""
        except Exception as e:
            print(f"ERROR calling Ollama: {e}")
            return ""
    
    def check_available(self) -> bool:
        """Check if Ollama is running and model is available."""
        try:
            import requests
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                return any(self.model in name for name in model_names)
            return False
        except:
            return False


# =============================================================================
# STAGE 2: STRUCTURAL ANALYSIS (LLM Pass 1)
# =============================================================================

def analyze_structure(llm: OllamaClient, text: str, toc: Optional[Dict] = None) -> Dict:
    """
    LLM Pass 1: Determine book type and structure pattern.
    Input: First ~4K tokens + TOC if exists
    """
    # Take first ~4000 tokens (rough estimate: 1 token ≈ 4 chars)
    sample_text = text[:16000]  # ~4K tokens
    
    toc_context = ""
    if toc and toc.get('has_toc'):
        toc_entries = "\n".join([f"  {entry[1]} (page {entry[2]})" for entry in toc['entries'][:20]])
        toc_context = f"\n\nTable of Contents:\n{toc_entries}"
    
    prompt = f"""Analyze this book's structure. Given the beginning of the text{toc_context}, determine:

1. Book type: treatise, novel, dialogue, collection, manual, poetry, religious, other
2. Structure pattern: parts>chapters, books>entries, sections, continuous, other
3. Has front matter? (preface, introduction, foreword)
4. Has back matter? (notes, appendix, index, bibliography)

Text sample:
{sample_text[:2000]}...

Respond in JSON format:
{{
  "book_type": "...",
  "structure_pattern": "...",
  "has_front_matter": true/false,
  "has_back_matter": true/false,
  "front_matter_types": ["introduction", "preface", ...],
  "back_matter_types": ["notes", "appendix", ...],
  "hierarchy_levels": 1 or 2 or 3,
  "confidence": 0.0-1.0
}}"""

    system_prompt = "You are a book structure analyst. Respond only with valid JSON."
    
    response = llm.generate(prompt, system_prompt=system_prompt, max_tokens=500)
    
    # Parse JSON response
    try:
        # Extract JSON from response (may have markdown code blocks)
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()
        
        return json.loads(response)
    except:
        # Fallback structure
        return {
            "book_type": "unknown",
            "structure_pattern": "continuous",
            "has_front_matter": False,
            "has_back_matter": False,
            "hierarchy_levels": 1,
            "confidence": 0.3
        }


# =============================================================================
# STAGE 3: SECTION BOUNDARY DETECTION (LLM Pass 2)
# =============================================================================

def detect_boundaries(llm: OllamaClient, text: str, structure_info: Dict) -> List[SectionBoundary]:
    """
    LLM Pass 2: Detect section boundaries using sliding windows.
    Input: ~8K token chunks, sequential
    """
    boundaries = []
    
    # Chunk text into ~8K token windows (32K chars) with overlap
    chunk_size = 32000
    overlap = 4000
    
    book_type = structure_info.get("book_type", "unknown")
    pattern = structure_info.get("structure_pattern", "continuous")
    
    i = 0
    while i < len(text):
        chunk = text[i:i + chunk_size]
        chunk_end = min(i + chunk_size, len(text))
        
        prompt = f"""Given this is a {book_type} book with {pattern} structure, identify section boundaries in this text chunk.

Look for:
- Chapter headers
- Section breaks
- Part divisions
- Entry markers
- Any structural divisions

Text chunk (character positions {i} to {chunk_end}):
{chunk}

Respond with JSON array of boundaries found:
[
  {{
    "level": 1 or 2 or 3,
    "type": "chapter" or "section" or "part" or "entry",
    "title": "exact title as written",
    "offset": character position where this section starts
  }},
  ...
]

Only include boundaries that are CLEARLY marked in the text. Be conservative."""

        system_prompt = "You are a text structure detector. Respond only with valid JSON array."
        
        response = llm.generate(prompt, system_prompt=system_prompt, max_tokens=2000)
        
        # Parse boundaries
        try:
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()
            
            detected = json.loads(response)
            if isinstance(detected, list):
                for b in detected:
                    offset = b.get("offset", i)
                    if offset >= i and offset < chunk_end:
                        boundaries.append(SectionBoundary(
                            level=b.get("level", 1),
                            type=b.get("type", "section"),
                            title=b.get("title", "").strip(),
                            start_offset=offset
                        ))
        except Exception as e:
            print(f"  Warning: Failed to parse boundaries from chunk {i}: {e}")
        
        # Move to next chunk with overlap
        i += chunk_size - overlap
        
        # Small delay to avoid overwhelming Ollama
        time.sleep(0.5)
    
    # Sort boundaries by offset and set end offsets
    boundaries.sort(key=lambda b: b.start_offset)
    
    for i in range(len(boundaries)):
        if i < len(boundaries) - 1:
            boundaries[i].end_offset = boundaries[i + 1].start_offset
        else:
            boundaries[i].end_offset = len(text)
    
    return boundaries


# =============================================================================
# STAGE 4: SECTION ENRICHMENT (LLM Pass 3)
# =============================================================================

def enrich_section(llm: OllamaClient, section_text: str, section_info: Dict, book_context: Dict) -> Dict:
    """
    LLM Pass 3: Enrich a single section with summary, themes, passages.
    """
    prompt = f"""Analyze this section from a {book_context.get('book_type', 'book')}:

Title: {section_info.get('title', 'Untitled')}
Type: {section_info.get('type', 'section')}

Text:
{section_text[:4000]}...

Provide:
1. Summary (2-3 sentences)
2. Key themes (3-7 tags)
3. Notable passages (1-3 quotes with significance)
4. Difficulty level (accessible, moderate, challenging)
5. Estimated reading time in minutes

Respond in JSON:
{{
  "summary": "...",
  "key_themes": ["theme1", "theme2", ...],
  "notable_passages": [
    {{
      "text_preview": "...",
      "offset_start": 0,
      "offset_end": 100,
      "significance": "..."
    }}
  ],
  "difficulty": "accessible" or "moderate" or "challenging",
  "reading_time_minutes": 5
}}"""

    system_prompt = "You are a literary analyst. Respond only with valid JSON."
    
    response = llm.generate(prompt, system_prompt=system_prompt, max_tokens=1000)
    
    try:
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()
        
        return json.loads(response)
    except:
        # Fallback enrichment
        return {
            "summary": "Section content.",
            "key_themes": [],
            "notable_passages": [],
            "difficulty": "moderate",
            "reading_time_minutes": 5
        }


# =============================================================================
# STAGE 5: BOOK-LEVEL SYNTHESIS (LLM Pass 4)
# =============================================================================

def synthesize_book(llm: OllamaClient, sections: List[Dict], structure_info: Dict) -> Dict:
    """
    LLM Pass 4: Create thematic index, routing hints, cross-references.
    """
    # Build context from section summaries
    section_summaries = []
    for sec in sections:
        section_summaries.append({
            "id": sec.get("id"),
            "title": sec.get("title"),
            "summary": sec.get("summary", ""),
            "themes": sec.get("key_themes", [])
        })
    
    summaries_text = "\n\n".join([
        f"{s['title']}: {s['summary']} [Themes: {', '.join(s['themes'])}]"
        for s in section_summaries[:50]  # Limit context
    ])
    
    prompt = f"""Given all sections from this book, create:

1. Domain and subdomains (e.g., philosophy: stoicism, ethics)
2. Thematic index (theme → list of section IDs)
3. Routing hints (good_for, not_good_for, pairs_well_with)
4. Overall difficulty

Section summaries:
{summaries_text}

Respond in JSON:
{{
  "domain": "...",
  "subdomains": ["...", ...],
  "thematic_index": {{
    "theme_name": ["sec_001", "sec_002", ...],
    ...
  }},
  "routing_hints": {{
    "good_for": ["use case 1", "use case 2", ...],
    "not_good_for": ["use case 1", ...],
    "pairs_well_with": ["Book Title - Author", ...]
  }},
  "overall_difficulty": "accessible" or "moderate" or "challenging"
}}"""

    system_prompt = "You are a book taxonomy expert. Respond only with valid JSON."
    
    response = llm.generate(prompt, system_prompt=system_prompt, max_tokens=2000)
    
    try:
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()
        
        return json.loads(response)
    except:
        return {
            "domain": "general",
            "subdomains": [],
            "thematic_index": {},
            "routing_hints": {
                "good_for": [],
                "not_good_for": [],
                "pairs_well_with": []
            },
            "overall_difficulty": "moderate"
        }


# =============================================================================
# STAGE 6: VALIDATION
# =============================================================================

def validate_artifact(artifact: Dict, original_text: str) -> Tuple[bool, List[str], float]:
    """
    Validate artifact quality.
    Returns: (is_valid, flags, confidence_score)
    """
    flags = []
    confidence = 1.0
    
    sections = artifact.get("sections", [])
    
    # Check coverage
    if sections:
        first_offset = sections[0].get("start_offset", 0)
        last_section = sections[-1]
        last_offset = last_section.get("end_offset", len(original_text))
        
        if first_offset > 0:
            flags.append("Missing text before first section")
            confidence -= 0.1
        
        if last_offset < len(original_text) - 100:  # Allow 100 char tolerance
            flags.append(f"Missing {len(original_text) - last_offset} characters at end")
            confidence -= 0.1
        
        # Check for overlaps
        for i in range(len(sections) - 1):
            if sections[i].get("end_offset", 0) > sections[i + 1].get("start_offset", 0):
                flags.append(f"Overlapping sections: {sections[i].get('id')} and {sections[i + 1].get('id')}")
                confidence -= 0.2
        
        # Check for gaps
        for i in range(len(sections) - 1):
            gap = sections[i + 1].get("start_offset", 0) - sections[i].get("end_offset", 0)
            if gap > 100:  # More than 100 chars gap
                flags.append(f"Gap of {gap} characters between sections")
                confidence -= 0.05
    
    # Check section quality
    sections_without_summary = sum(1 for s in sections if not s.get("summary"))
    if sections_without_summary > 0:
        flags.append(f"{sections_without_summary} sections missing summaries")
        confidence -= 0.1
    
    sections_without_themes = sum(1 for s in sections if not s.get("key_themes"))
    if sections_without_themes > 0:
        flags.append(f"{sections_without_themes} sections missing themes")
        confidence -= 0.05
    
    # Check structure matches detected pattern
    structure = artifact.get("structure", {})
    detected_pattern = structure.get("pattern", "")
    if detected_pattern == "continuous" and len(sections) > 1:
        flags.append("Detected continuous structure but found multiple sections")
        confidence -= 0.2
    
    confidence = max(0.0, min(1.0, confidence))
    
    is_valid = confidence >= 0.6 and len(flags) < 5
    
    return is_valid, flags, confidence


# =============================================================================
# MAIN PIPELINE
# =============================================================================

def process_book(pdf_path: Path, output_dir: Path, llm: OllamaClient) -> Dict:
    """Process a single book through the full pipeline."""
    print(f"\n{'='*70}")
    print(f"Processing: {pdf_path.name}")
    print(f"{'='*70}")
    
    # STAGE 1: Text Extraction
    print("Stage 1: Extracting text...")
    text, page_count, toc = extract_text_with_pymupdf(pdf_path)
    if not text:
        return {"error": "Failed to extract text"}
    
    print(f"  Extracted {len(text)} characters, {page_count} pages")
    
    # Generate book ID
    text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
    book_id = f"book_{text_hash}"
    
    # STAGE 2: Structural Analysis
    print("Stage 2: Analyzing structure...")
    structure_info = analyze_structure(llm, text, toc)
    print(f"  Type: {structure_info.get('book_type')}, Pattern: {structure_info.get('structure_pattern')}")
    
    # STAGE 3: Boundary Detection
    print("Stage 3: Detecting section boundaries...")
    boundaries = detect_boundaries(llm, text, structure_info)
    print(f"  Found {len(boundaries)} sections")
    
    if not boundaries:
        # Fallback: create single section
        boundaries = [SectionBoundary(level=1, type="section", title="Full Text", start_offset=0, end_offset=len(text))]
    
    # STAGE 4: Section Enrichment
    print("Stage 4: Enriching sections...")
    enriched_sections = []
    for i, boundary in enumerate(boundaries):
        section_text = text[boundary.start_offset:boundary.end_offset]
        section_id = f"sec_{i+1:03d}"
        
        section_dict = {
            "id": section_id,
            "level": boundary.level,
            "type": boundary.type,
            "number": i + 1 if boundary.level == 1 else None,
            "title": boundary.title,
            "start_offset": boundary.start_offset,
            "end_offset": boundary.end_offset,
            "word_count": len(section_text.split())
        }
        
        enrichment = enrich_section(llm, section_text, section_dict, structure_info)
        section_dict.update(enrichment)
        
        # Calculate reading time (rough: 200 words per minute)
        if not section_dict.get("reading_time_minutes"):
            section_dict["reading_time_minutes"] = max(1, section_dict["word_count"] // 200)
        
        enriched_sections.append(section_dict)
        print(f"  Enriched {section_id}: {boundary.title[:50]}")
        time.sleep(0.3)  # Rate limiting
    
    # STAGE 5: Book Synthesis
    print("Stage 5: Synthesizing book-level data...")
    synthesis = synthesize_book(llm, enriched_sections, structure_info)
    
    # Build artifact
    artifact = {
        "artifact_version": 2,
        "id": book_id,
        "meta": {
            "title": pdf_path.stem,  # Will be improved with metadata extraction
            "author": "Unknown",  # Will be improved
            "domain": synthesis.get("domain", "general"),
            "subdomains": synthesis.get("subdomains", []),
            "book_type": structure_info.get("book_type", "unknown"),
            "difficulty": synthesis.get("overall_difficulty", "moderate"),
            "page_count": page_count,
            "word_count": len(text.split()),
            "char_count": len(text)
        },
        "structure": {
            "pattern": structure_info.get("structure_pattern", "continuous"),
            "hierarchy_levels": structure_info.get("hierarchy_levels", 1),
            "has_front_matter": structure_info.get("has_front_matter", False),
            "has_back_matter": structure_info.get("has_back_matter", False),
            "total_sections": len(enriched_sections)
        },
        "sections": enriched_sections,
        "thematic_index": synthesis.get("thematic_index", {}),
        "routing_hints": synthesis.get("routing_hints", {}),
        "extraction_meta": {
            "model": llm.model,
            "date": datetime.now(timezone.utc).isoformat(),
            "confidence": 0.0,  # Will be set by validation
            "human_verified": False,
            "flags": []
        }
    }
    
    # STAGE 6: Validation
    print("Stage 6: Validating artifact...")
    is_valid, flags, confidence = validate_artifact(artifact, text)
    artifact["extraction_meta"]["confidence"] = confidence
    artifact["extraction_meta"]["flags"] = flags
    
    print(f"  Confidence: {confidence:.2f}")
    if flags:
        print(f"  Flags: {', '.join(flags[:3])}")
    if not is_valid:
        print(f"  ⚠️  Low confidence - flagged for review")
    
    # Write artifact
    output_path = output_dir / f"{book_id}.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)
    
    print(f"  ✅ Artifact written: {output_path}")
    
    return {
        "book_id": book_id,
        "confidence": confidence,
        "is_valid": is_valid,
        "flags": flags,
        "sections": len(enriched_sections)
    }


def main():
    parser = argparse.ArgumentParser(description="Taxonomy Engine - 4-pass LLM pipeline")
    parser.add_argument("input", type=Path, help="PDF file or directory")
    parser.add_argument("output", type=Path, help="Output directory for artifacts")
    parser.add_argument("--model", default="llama3.1:8b", help="Ollama model name")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama base URL")
    parser.add_argument("--batch", action="store_true", help="Process all PDFs in directory")
    parser.add_argument("--resume", action="store_true", help="Skip books that already have artifacts")
    args = parser.parse_args()
    
    # Check Ollama
    llm = OllamaClient(base_url=args.ollama_url, model=args.model)
    print("Checking Ollama connection...")
    if not llm.check_available():
        print(f"❌ ERROR: Ollama not available or model '{args.model}' not found")
        print(f"   Make sure Ollama is running: ollama serve")
        print(f"   Pull the model: ollama pull {args.model}")
        sys.exit(1)
    print(f"✅ Ollama connected, using model: {args.model}")
    
    # Create output directory
    args.output.mkdir(parents=True, exist_ok=True)
    
    # Get PDF files
    if args.input.is_file():
        pdf_files = [args.input]
    else:
        pdf_files = list(args.input.glob("*.pdf"))
    
    if not pdf_files:
        print(f"❌ No PDF files found in {args.input}")
        sys.exit(1)
    
    print(f"\nFound {len(pdf_files)} PDF files")
    
    # Process each book
    results = []
    for pdf_path in pdf_files:
        # Check if already processed
        if args.resume:
            # Try to find existing artifact (would need to match by hash)
            # For now, skip if JSON already exists with same stem
            artifact_path = args.output / f"{pdf_path.stem}.json"
            if artifact_path.exists():
                print(f"⏭️  Skipping {pdf_path.name} (artifact exists)")
                continue
        
        try:
            result = process_book(pdf_path, args.output, llm)
            results.append(result)
        except Exception as e:
            print(f"❌ Error processing {pdf_path.name}: {e}")
            results.append({"error": str(e)})
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    successful = [r for r in results if "error" not in r]
    print(f"Processed: {len(successful)}/{len(results)}")
    if successful:
        avg_confidence = sum(r.get("confidence", 0) for r in successful) / len(successful)
        print(f"Average confidence: {avg_confidence:.2f}")
        low_confidence = sum(1 for r in successful if r.get("confidence", 1) < 0.7)
        if low_confidence > 0:
            print(f"⚠️  {low_confidence} books flagged for review")


if __name__ == '__main__':
    main()
