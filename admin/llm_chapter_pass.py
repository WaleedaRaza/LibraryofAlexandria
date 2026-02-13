#!/usr/bin/env python3
"""
Alexandria Library - LLM Chapter Detection Pass

Runs GPT-4o-mini on books that have only 1 chapter (fallback detection)
to properly detect chapter structure.

Usage:
    python -m admin.llm_chapter_pass extracted/
    python -m admin.llm_chapter_pass extracted/ --limit 10  # Test on 10 books first
"""

import argparse
import json
import re
import sys
import asyncio
from pathlib import Path
from typing import List, Dict
from datetime import datetime, timezone
from dataclasses import dataclass, asdict

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings


@dataclass
class Chapter:
    number: int
    title: str
    start_offset: int
    end_offset: int
    detection_method: str


async def detect_chapters_with_llm(text: str, title: str, author: str) -> List[Dict]:
    """Use GPT-4o-mini to identify chapter structure."""
    try:
        import openai
        
        if not settings.OPENAI_API_KEY:
            print("  ⚠️  No OpenAI API key")
            return []
        
        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        
        # Send first ~10k chars (usually includes TOC or first chapters)
        sample = text[:10000]
        
        prompt = f"""Analyze this text from "{title}" by {author} and identify ALL chapters or major sections.

TEXT SAMPLE (first 10,000 characters):
---
{sample}
---

Your task:
1. Identify ALL chapters, parts, books, or major sections
2. For each, provide the EXACT text that marks the start (so I can find it with string search)

Return ONLY a JSON array like this:
[
  {{"number": 1, "title": "Chapter 1: The Beginning", "marker": "Chapter 1"}},
  {{"number": 2, "title": "Part Two: The Journey", "marker": "Part Two"}}
]

Rules:
- Include Roman numerals (I, II, III), word numbers (One, Two), and Arabic (1, 2, 3)
- The "marker" must be the EXACT text that appears in the book (case-sensitive)
- If the text sample shows a Table of Contents, use that as your guide
- If no clear chapters exist, return an empty array: []
- Do NOT make up chapters - only return what you can identify from the text

JSON array only, no explanation:"""

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
            result = result.strip()
        
        parsed = json.loads(result)
        
        if not isinstance(parsed, list):
            return []
        
        return parsed
    
    except json.JSONDecodeError as e:
        print(f"  ⚠️  JSON parse error: {e}")
        return []
    except Exception as e:
        print(f"  ⚠️  LLM error: {e}")
        return []


def find_marker_offset(text: str, marker: str) -> int:
    """Find the offset of a marker in text, with fuzzy matching."""
    # Exact match
    offset = text.find(marker)
    if offset >= 0:
        return offset
    
    # Case-insensitive
    lower_text = text.lower()
    lower_marker = marker.lower()
    offset = lower_text.find(lower_marker)
    if offset >= 0:
        return offset
    
    # Try first few words
    words = marker.split()[:3]
    if words:
        pattern = r'\b' + r'\s+'.join(re.escape(w) for w in words)
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.start()
    
    return -1


async def process_single_book(json_path: Path, verbose: bool = True) -> Dict:
    """Process a single book through LLM chapter detection."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    title = data.get('title', 'Unknown')
    author = data.get('author', 'Unknown')
    text = data.get('content', '')
    
    if verbose:
        print(f"  Calling LLM for: {title[:50]}...")
    
    # Get LLM chapter detection
    llm_chapters = await detect_chapters_with_llm(text, title, author)
    
    if not llm_chapters:
        if verbose:
            print(f"  ⚠️  LLM found no chapters")
        return {'status': 'no_chapters', 'file': str(json_path)}
    
    # Convert to proper chapter objects with offsets
    chapters = []
    for i, ch in enumerate(llm_chapters):
        marker = ch.get('marker', ch.get('title', ''))
        offset = find_marker_offset(text, marker)
        
        if offset < 0:
            # Skip if marker not found
            continue
        
        chapters.append({
            'number': ch.get('number', i + 1),
            'title': ch.get('title', marker)[:200],
            'start_offset': offset,
            'end_offset': 0,  # Set later
            'detection_method': 'llm'
        })
    
    if not chapters:
        if verbose:
            print(f"  ⚠️  Could not locate markers in text")
        return {'status': 'markers_not_found', 'file': str(json_path)}
    
    # Sort by offset and set end offsets
    chapters.sort(key=lambda x: x['start_offset'])
    for i, ch in enumerate(chapters):
        if i < len(chapters) - 1:
            ch['end_offset'] = chapters[i + 1]['start_offset']
        else:
            ch['end_offset'] = len(text)
    
    # Update the JSON file
    data['chapters'] = chapters
    data['extraction_method'] = 'llm'
    data['llm_pass_date'] = datetime.now(timezone.utc).isoformat()
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    if verbose:
        print(f"  ✅ Found {len(chapters)} chapters via LLM")
    
    return {
        'status': 'success',
        'file': str(json_path),
        'chapters_found': len(chapters)
    }


async def run_llm_pass(input_dir: Path, limit: int = None, verbose: bool = True):
    """Run LLM pass on all single-chapter books."""
    
    # Find books with only 1 chapter (fallback detection)
    candidates = []
    for json_path in input_dir.glob('*.json'):
        if json_path.name.startswith('_'):
            continue
        
        try:
            with open(json_path) as f:
                data = json.load(f)
            
            chapters = data.get('chapters', [])
            method = data.get('extraction_method', '')
            
            # Only process fallback or single-chapter books
            if len(chapters) <= 1 or method == 'fallback':
                word_count = data.get('word_count', 0)
                # Skip very short texts (probably pamphlets)
                if word_count > 5000:
                    candidates.append(json_path)
        except:
            pass
    
    if limit:
        candidates = candidates[:limit]
    
    print(f"\n{'='*60}")
    print(f"LLM CHAPTER DETECTION PASS")
    print(f"{'='*60}")
    print(f"Books to process: {len(candidates)}")
    print(f"Model: {settings.OPENAI_MODEL}")
    print(f"{'='*60}\n")
    
    results = {
        'success': [],
        'no_chapters': [],
        'markers_not_found': [],
        'errors': []
    }
    
    for i, json_path in enumerate(candidates):
        print(f"[{i+1}/{len(candidates)}] {json_path.stem[:60]}...")
        
        try:
            result = await process_single_book(json_path, verbose=verbose)
            
            if result['status'] == 'success':
                results['success'].append(result)
            elif result['status'] == 'no_chapters':
                results['no_chapters'].append(result)
            elif result['status'] == 'markers_not_found':
                results['markers_not_found'].append(result)
            else:
                results['errors'].append(result)
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results['errors'].append({'file': str(json_path), 'error': str(e)})
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(0.5)
    
    # Summary
    print(f"\n{'='*60}")
    print(f"LLM PASS COMPLETE")
    print(f"{'='*60}")
    print(f"✅ Chapters detected: {len(results['success'])}")
    print(f"⚠️  No chapters found: {len(results['no_chapters'])}")
    print(f"⚠️  Markers not found: {len(results['markers_not_found'])}")
    print(f"❌ Errors: {len(results['errors'])}")
    print(f"{'='*60}\n")
    
    # Save report
    report_path = input_dir / '_llm_pass_report.json'
    with open(report_path, 'w') as f:
        json.dump({
            'date': datetime.now(timezone.utc).isoformat(),
            'total_processed': len(candidates),
            'results': {k: len(v) for k, v in results.items()},
            'details': results
        }, f, indent=2)
    
    print(f"Report saved to: {report_path}")
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Run LLM chapter detection on single-chapter books"
    )
    parser.add_argument("input", type=Path, help="Directory with extracted JSON files")
    parser.add_argument("--limit", type=int, help="Limit number of books to process")
    parser.add_argument("-q", "--quiet", action="store_true", help="Less verbose")
    
    args = parser.parse_args()
    
    if not args.input.exists():
        print(f"ERROR: Directory not found: {args.input}")
        sys.exit(1)
    
    asyncio.run(run_llm_pass(args.input, limit=args.limit, verbose=not args.quiet))


if __name__ == "__main__":
    main()
