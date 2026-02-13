"""
Alexandria - Per-Book Agent

The intelligence that transforms a messy PDF into a navigable knowledge asset.

This agent:
1. Bootstraps: One-time parse to create StructureMap + Landmarks
2. Refines: Incremental updates based on new evidence
3. Researches: Fetches external context about the book

It produces BookArtifacts that all other LLMs consume.
"""

import json
import hashlib
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

from ..config import Settings
from ..domain.book_artifacts import (
    BookArtifacts, BookSection, Landmark, ReadingPath, ReadingPathStep,
    ExternalProfile, PageRange, LandmarkType, SectionType, Provenance
)


@dataclass
class PageSample:
    """A sample of page content for the LLM."""
    page_number: int
    text: str
    word_count: int
    quality: float


class BookAgent:
    """
    Per-book intelligence agent.
    
    Produces and maintains BookArtifacts for a single book.
    """
    
    def __init__(self, book_id: str, title: str, author: str):
        self.book_id = book_id
        self.title = title
        self.author = author
        self.settings = Settings()
        self._client = None
    
    @property
    def client(self):
        """Lazy load OpenAI client."""
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.settings.OPENAI_API_KEY)
        return self._client
    
    def bootstrap(self, pages: List[PageSample]) -> BookArtifacts:
        """
        One-time bootstrap: Create initial BookArtifacts from page samples.
        
        Strategy:
        1. Sample strategically (first, last, TOC candidates, dense pages)
        2. Detect structure (sections/chapters)
        3. Extract landmarks (concepts, definitions, arguments)
        4. Generate reading paths
        """
        total_pages = max(p.page_number for p in pages) if pages else 0
        
        artifacts = BookArtifacts(
            book_id=self.book_id,
            total_pages=total_pages,
            version=1,
            status="processing",
        )
        
        try:
            # Step 1: Detect structure
            sections = self._detect_structure(pages)
            artifacts.sections = sections
            artifacts.structure_confidence = self._calculate_structure_confidence(sections)
            
            # Step 2: Extract landmarks
            landmarks = self._extract_landmarks(pages, sections)
            
            # Sort landmarks by type
            for lm in landmarks:
                if lm.landmark_type == LandmarkType.CONCEPT:
                    artifacts.concepts.append(lm)
                elif lm.landmark_type == LandmarkType.DEFINITION:
                    artifacts.definitions.append(lm)
                elif lm.landmark_type == LandmarkType.ARGUMENT:
                    artifacts.arguments.append(lm)
                elif lm.landmark_type == LandmarkType.EXAMPLE:
                    artifacts.examples.append(lm)
                elif lm.landmark_type == LandmarkType.COUNTERPOINT:
                    artifacts.counterpoints.append(lm)
            
            # Step 3: Generate reading paths
            paths = self._generate_reading_paths(sections, landmarks)
            artifacts.paths = paths
            
            artifacts.status = "complete"
            
        except Exception as e:
            artifacts.status = "failed"
            artifacts.bootstrap_notes = str(e)
        
        return artifacts
    
    def _detect_structure(self, pages: List[PageSample]) -> List[BookSection]:
        """Detect chapter/section structure from pages."""
        if not pages:
            return []
        
        # Strategic sampling
        samples = self._get_strategic_samples(pages)
        
        # Build prompt
        sample_text = "\n\n".join([
            f"=== PAGE {s.page_number} ===\n{s.text[:1500]}"
            for s in samples[:15]  # Limit to 15 samples
        ])
        
        prompt = f"""Analyze this book and identify its structure (chapters, parts, sections).

BOOK: "{self.title}" by {self.author}
TOTAL PAGES: {max(p.page_number for p in pages)}

SAMPLE PAGES:
{sample_text}

Respond with a JSON array of sections. Each section should have:
- title: The section/chapter title
- type: "part", "chapter", or "section"
- page_start: Starting page number
- page_end: Ending page number (estimate if unsure)
- confidence: 0.0 to 1.0 (how confident are you in this boundary)

Focus on major divisions. Don't invent structure that isn't there.
If the book has no clear structure, return a single "Full Text" section.

Respond ONLY with valid JSON array, no other text."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000,
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse JSON
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            sections_data = json.loads(content)
            
            # Convert to BookSection objects
            sections = []
            for i, s in enumerate(sections_data):
                section_id = f"sec_{self.book_id}_{i+1}"
                
                section_type = SectionType.CHAPTER
                if s.get("type") == "part":
                    section_type = SectionType.PART
                elif s.get("type") == "section":
                    section_type = SectionType.SECTION
                
                sections.append(BookSection(
                    id=section_id,
                    title=s.get("title", f"Section {i+1}"),
                    pages=PageRange(
                        start=s.get("page_start", 1),
                        end=s.get("page_end", max(p.page_number for p in pages))
                    ),
                    section_type=section_type,
                    order=i + 1,
                    confidence=s.get("confidence", 0.5),
                    provenance=Provenance.LLM_BOOTSTRAP,
                ))
            
            return sections
            
        except Exception as e:
            # Fallback: single section
            return [BookSection(
                id=f"sec_{self.book_id}_1",
                title="Full Text",
                pages=PageRange(1, max(p.page_number for p in pages) if pages else 1),
                section_type=SectionType.SECTION,
                order=1,
                confidence=0.2,
                provenance=Provenance.LLM_BOOTSTRAP,
            )]
    
    def _extract_landmarks(
        self, 
        pages: List[PageSample], 
        sections: List[BookSection]
    ) -> List[Landmark]:
        """Extract navigable landmarks (concepts, definitions, arguments)."""
        if not pages:
            return []
        
        # Get page samples from key sections
        key_pages = self._get_key_pages(pages, sections)
        
        sample_text = "\n\n".join([
            f"=== PAGE {p.page_number} ===\n{p.text[:1200]}"
            for p in key_pages[:12]
        ])
        
        prompt = f"""Analyze this book and identify key navigable landmarks.

BOOK: "{self.title}" by {self.author}

SAMPLE PAGES:
{sample_text}

Identify landmarks in these categories:
1. CONCEPTS: Core ideas/themes the book explores
2. DEFINITIONS: Where key terms are defined
3. ARGUMENTS: Where major claims are argued
4. EXAMPLES: Notable case studies or illustrations
5. COUNTERPOINTS: Objections or counter-arguments discussed

For each landmark, provide:
- label: The concept/term/argument name
- type: "concept", "definition", "argument", "example", or "counterpoint"
- page_start: Where it begins
- page_end: Where it ends
- description: One sentence description
- importance: 0.0 to 1.0 (how central to the book)

Focus on the most important 10-15 landmarks.

Respond ONLY with valid JSON array, no other text."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2500,
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse JSON
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            landmarks_data = json.loads(content)
            
            # Convert to Landmark objects
            landmarks = []
            for i, lm in enumerate(landmarks_data):
                landmark_id = f"lm_{self.book_id}_{i+1}"
                
                lm_type = LandmarkType.CONCEPT
                type_str = lm.get("type", "concept").lower()
                if type_str == "definition":
                    lm_type = LandmarkType.DEFINITION
                elif type_str == "argument":
                    lm_type = LandmarkType.ARGUMENT
                elif type_str == "example":
                    lm_type = LandmarkType.EXAMPLE
                elif type_str == "counterpoint":
                    lm_type = LandmarkType.COUNTERPOINT
                
                landmarks.append(Landmark(
                    id=landmark_id,
                    label=lm.get("label", f"Landmark {i+1}"),
                    landmark_type=lm_type,
                    pages=PageRange(
                        start=lm.get("page_start", 1),
                        end=lm.get("page_end", lm.get("page_start", 1))
                    ),
                    description=lm.get("description"),
                    importance=lm.get("importance", 0.5),
                    confidence=0.6,
                    provenance=Provenance.LLM_BOOTSTRAP,
                ))
            
            return landmarks
            
        except Exception as e:
            return []
    
    def _generate_reading_paths(
        self, 
        sections: List[BookSection], 
        landmarks: List[Landmark]
    ) -> List[ReadingPath]:
        """Generate goal-based reading paths."""
        paths = []
        
        # Path 1: Quick Overview
        if sections:
            steps = []
            for section in sections[:5]:
                steps.append(ReadingPathStep(
                    pages=PageRange(section.pages.start, min(section.pages.start + 3, section.pages.end)),
                    reason=f"Start of: {section.title}"
                ))
            
            if steps:
                paths.append(ReadingPath(
                    id=f"path_{self.book_id}_overview",
                    goal="quick_overview",
                    name="Quick Overview",
                    steps=steps
                ))
        
        # Path 2: Core Arguments
        argument_landmarks = [lm for lm in landmarks if lm.landmark_type == LandmarkType.ARGUMENT]
        if argument_landmarks:
            steps = [
                ReadingPathStep(pages=lm.pages, reason=lm.label)
                for lm in sorted(argument_landmarks, key=lambda x: -x.importance)[:5]
            ]
            paths.append(ReadingPath(
                id=f"path_{self.book_id}_arguments",
                goal="understand_arguments",
                name="Core Arguments",
                steps=steps
            ))
        
        # Path 3: Key Definitions
        definition_landmarks = [lm for lm in landmarks if lm.landmark_type == LandmarkType.DEFINITION]
        if definition_landmarks:
            steps = [
                ReadingPathStep(pages=lm.pages, reason=f"Definition: {lm.label}")
                for lm in definition_landmarks[:5]
            ]
            paths.append(ReadingPath(
                id=f"path_{self.book_id}_definitions",
                goal="learn_terminology",
                name="Key Definitions",
                steps=steps
            ))
        
        return paths
    
    def _get_strategic_samples(self, pages: List[PageSample]) -> List[PageSample]:
        """Get strategically sampled pages for structure detection."""
        if not pages:
            return []
        
        samples = []
        total = len(pages)
        
        # First 5 pages (intro, TOC candidates)
        samples.extend(pages[:5])
        
        # Last 3 pages (conclusion, index)
        samples.extend(pages[-3:])
        
        # Every ~20 pages through the book
        for i in range(10, total, max(total // 10, 20)):
            if i < len(pages):
                samples.append(pages[i])
        
        # Pages with high word count (content-rich)
        dense_pages = sorted(pages, key=lambda p: -p.word_count)[:5]
        samples.extend(dense_pages)
        
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for p in samples:
            if p.page_number not in seen:
                seen.add(p.page_number)
                unique.append(p)
        
        return sorted(unique, key=lambda p: p.page_number)
    
    def _get_key_pages(
        self, 
        pages: List[PageSample], 
        sections: List[BookSection]
    ) -> List[PageSample]:
        """Get key pages for landmark extraction."""
        key_pages = []
        
        # First page of each section
        for section in sections:
            for page in pages:
                if page.page_number == section.pages.start:
                    key_pages.append(page)
                    break
        
        # Densest pages overall
        dense = sorted(pages, key=lambda p: -p.word_count)[:10]
        key_pages.extend(dense)
        
        # First and last pages
        if pages:
            key_pages.append(pages[0])
            key_pages.append(pages[-1])
        
        # Deduplicate
        seen = set()
        unique = []
        for p in key_pages:
            if p.page_number not in seen:
                seen.add(p.page_number)
                unique.append(p)
        
        return sorted(unique, key=lambda p: p.page_number)
    
    def _calculate_structure_confidence(self, sections: List[BookSection]) -> float:
        """Calculate overall structure confidence."""
        if not sections:
            return 0.0
        
        avg_confidence = sum(s.confidence for s in sections) / len(sections)
        
        # Bonus for having multiple sections
        if len(sections) > 3:
            avg_confidence += 0.1
        
        return min(1.0, avg_confidence)
    
    def research_external(self) -> ExternalProfile:
        """Fetch external knowledge about the book."""
        prompt = f"""Provide background context for this book:

TITLE: "{self.title}"
AUTHOR: {self.author}

Respond with JSON containing:
- canonical_description: 1-2 sentence description of what the book is about
- author_background: Brief author context (1 sentence)
- major_critiques: Array of 2-3 common criticisms (if any)
- related_works: Array of 2-3 related/similar books
- discourse_position: Where this book sits in its field (1 sentence)

Respond ONLY with valid JSON, no other text."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=800,
            )
            
            content = response.choices[0].message.content.strip()
            
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            data = json.loads(content)
            
            return ExternalProfile(
                canonical_description=data.get("canonical_description"),
                author_background=data.get("author_background"),
                major_critiques=data.get("major_critiques", []),
                related_works=data.get("related_works", []),
                discourse_position=data.get("discourse_position"),
            )
            
        except Exception as e:
            return ExternalProfile()
