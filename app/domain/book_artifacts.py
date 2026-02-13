"""
Alexandria - Book Artifacts Domain Model

Page-anchored knowledge artifacts that make books navigable.
This is the "per-book intelligence" that powers god-mode navigation.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
import json


class LandmarkType(Enum):
    """Types of navigable landmarks within a book."""
    CONCEPT = "concept"           # Core idea/theme
    DEFINITION = "definition"     # Where a term is defined
    ARGUMENT = "argument"         # Where a claim is argued
    EXAMPLE = "example"           # Case study/illustration
    COUNTERPOINT = "counterpoint" # Objection/counter-argument
    CONCLUSION = "conclusion"     # Synthesis/resolution
    QUOTE = "quote"               # Notable quotation


class SectionType(Enum):
    """Types of structural sections."""
    TOC_REAL = "toc_real"         # Extracted from actual TOC
    TOC_INFERRED = "toc_inferred" # Synthesized from headings
    PART = "part"                 # Major division
    CHAPTER = "chapter"           # Chapter
    SECTION = "section"           # Sub-section


class HighlightType(Enum):
    """User intent behind a highlight."""
    IMPORTANT = "important"       # 🟨 Yellow - key passage
    DEFINITION = "definition"     # 🟦 Blue - term definition
    DISAGREE = "disagree"         # 🟥 Red - disagree with this
    INSIGHT = "insight"           # 🟩 Green - personal insight
    QUESTION = "question"         # 🟣 Purple - confused/need clarity


class Provenance(Enum):
    """How we got this knowledge."""
    EXTRACTED_TOC = "extracted_toc"
    HEADING_DETECTION = "heading_detection"
    LLM_BOOTSTRAP = "llm_bootstrap"
    LLM_REFINEMENT = "llm_refinement"
    USER_CONFIRMED = "user_confirmed"
    INTERACTION_DERIVED = "interaction_derived"
    EXTERNAL_RESEARCH = "external_research"


@dataclass
class PageRange:
    """A range of pages - the fundamental anchor."""
    start: int
    end: int
    
    def __post_init__(self):
        if self.end < self.start:
            self.end = self.start
    
    def contains(self, page: int) -> bool:
        return self.start <= page <= self.end
    
    def overlaps(self, other: 'PageRange') -> bool:
        return not (self.end < other.start or other.end < self.start)
    
    def to_dict(self) -> Dict[str, int]:
        return {"start": self.start, "end": self.end}


@dataclass
class BookSection:
    """A structural section of the book (chapter, part, etc)."""
    id: str
    title: str
    pages: PageRange
    section_type: SectionType
    order: int = 0
    confidence: float = 0.5
    provenance: Provenance = Provenance.LLM_BOOTSTRAP
    parent_id: Optional[str] = None
    children: List['BookSection'] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "page_start": self.pages.start,
            "page_end": self.pages.end,
            "section_type": self.section_type.value,
            "order": self.order,
            "confidence": self.confidence,
            "provenance": self.provenance.value,
            "parent_id": self.parent_id,
        }


@dataclass
class Landmark:
    """A navigable knowledge point within the book."""
    id: str
    label: str
    landmark_type: LandmarkType
    pages: PageRange
    description: Optional[str] = None
    importance: float = 0.5
    confidence: float = 0.5
    provenance: Provenance = Provenance.LLM_BOOTSTRAP
    related_ids: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "landmark_type": self.landmark_type.value,
            "page_start": self.pages.start,
            "page_end": self.pages.end,
            "description": self.description,
            "importance": self.importance,
            "confidence": self.confidence,
            "provenance": self.provenance.value,
            "related_ids": self.related_ids,
        }


@dataclass
class ReadingPathStep:
    """A single step in a reading path."""
    pages: PageRange
    reason: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_start": self.pages.start,
            "page_end": self.pages.end,
            "reason": self.reason,
        }


@dataclass
class ReadingPath:
    """A goal-based navigation sequence through the book."""
    id: str
    goal: str          # 'understand_thesis', 'get_counterarguments', etc.
    name: str          # Human-readable name
    steps: List[ReadingPathStep]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "name": self.name,
            "steps": [s.to_dict() for s in self.steps],
        }


@dataclass
class ExternalProfile:
    """External knowledge about the book (not from the book itself)."""
    canonical_description: Optional[str] = None
    author_background: Optional[str] = None
    major_critiques: List[str] = field(default_factory=list)
    related_works: List[str] = field(default_factory=list)
    discourse_position: Optional[str] = None  # Where it sits in the broader discourse
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_description": self.canonical_description,
            "author_background": self.author_background,
            "major_critiques": self.major_critiques,
            "related_works": self.related_works,
            "discourse_position": self.discourse_position,
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, data: str) -> 'ExternalProfile':
        d = json.loads(data) if data else {}
        return cls(
            canonical_description=d.get("canonical_description"),
            author_background=d.get("author_background"),
            major_critiques=d.get("major_critiques", []),
            related_works=d.get("related_works", []),
            discourse_position=d.get("discourse_position"),
        )


@dataclass
class BookArtifacts:
    """
    The complete intelligence artifact bundle for a book.
    
    This is what the per-book agent produces and maintains.
    All downstream LLMs consume this for navigation/guidance.
    """
    book_id: str
    total_pages: int
    version: int = 1
    status: str = "pending"  # 'pending', 'processing', 'complete', 'failed'
    
    # Structure overlay
    sections: List[BookSection] = field(default_factory=list)
    structure_confidence: float = 0.0
    
    # Landmarks by type
    concepts: List[Landmark] = field(default_factory=list)
    definitions: List[Landmark] = field(default_factory=list)
    arguments: List[Landmark] = field(default_factory=list)
    examples: List[Landmark] = field(default_factory=list)
    counterpoints: List[Landmark] = field(default_factory=list)
    
    # Reading paths
    paths: List[ReadingPath] = field(default_factory=list)
    
    # External knowledge
    external_profile: Optional[ExternalProfile] = None
    
    # Metadata
    bootstrap_notes: Optional[str] = None
    
    @property
    def all_landmarks(self) -> List[Landmark]:
        """All landmarks combined."""
        return (
            self.concepts + 
            self.definitions + 
            self.arguments + 
            self.examples + 
            self.counterpoints
        )
    
    def get_landmarks_for_page(self, page: int) -> List[Landmark]:
        """Get all landmarks that cover a specific page."""
        return [lm for lm in self.all_landmarks if lm.pages.contains(page)]
    
    def get_section_for_page(self, page: int) -> Optional[BookSection]:
        """Get the section containing a specific page."""
        for section in self.sections:
            if section.pages.contains(page):
                return section
        return None
    
    def get_best_entry_for_intent(self, intent: str) -> Optional[PageRange]:
        """
        Given a user intent, find the best page range to land on.
        This is the core of "smart entry".
        """
        intent_lower = intent.lower()
        
        # Check definitions first
        for defn in self.definitions:
            if intent_lower in defn.label.lower():
                return defn.pages
        
        # Check concepts
        for concept in self.concepts:
            if intent_lower in concept.label.lower():
                return concept.pages
        
        # Check arguments
        for arg in self.arguments:
            if intent_lower in arg.label.lower():
                return arg.pages
        
        # Fallback: first section
        if self.sections:
            return self.sections[0].pages
        
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "book_id": self.book_id,
            "total_pages": self.total_pages,
            "version": self.version,
            "status": self.status,
            "structure_confidence": self.structure_confidence,
            "sections": [s.to_dict() for s in self.sections],
            "concepts": [l.to_dict() for l in self.concepts],
            "definitions": [l.to_dict() for l in self.definitions],
            "arguments": [l.to_dict() for l in self.arguments],
            "examples": [l.to_dict() for l in self.examples],
            "counterpoints": [l.to_dict() for l in self.counterpoints],
            "paths": [p.to_dict() for p in self.paths],
            "external_profile": self.external_profile.to_dict() if self.external_profile else None,
            "bootstrap_notes": self.bootstrap_notes,
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass 
class NavigationContext:
    """
    Context for runtime navigation decisions.
    Combines all four knowledge sources from the spec.
    """
    # A: Parsed book knowledge
    artifacts: BookArtifacts
    
    # B: Live researched knowledge
    external_profile: Optional[ExternalProfile] = None
    
    # C: User interaction memory (aggregated)
    popular_pages: List[int] = field(default_factory=list)
    common_jumps: Dict[int, List[int]] = field(default_factory=dict)  # page -> common destinations
    highlight_density: Dict[int, int] = field(default_factory=dict)  # page -> highlight count
    
    # D: Query + session context
    user_query: Optional[str] = None
    session_pages_viewed: List[int] = field(default_factory=list)
    session_highlights: List[str] = field(default_factory=list)
    
    def get_entry_page(self) -> int:
        """Determine best entry page given all context."""
        # If we have a query, use it to find best entry
        if self.user_query and self.artifacts:
            entry = self.artifacts.get_best_entry_for_intent(self.user_query)
            if entry:
                return entry.start
        
        # Use popular pages if available
        if self.popular_pages:
            return self.popular_pages[0]
        
        # Default to page 1
        return 1
    
    def get_suggested_jumps(self, current_page: int) -> List[Dict[str, Any]]:
        """Get suggested next jumps from current page."""
        suggestions = []
        
        # From common user jumps
        if current_page in self.common_jumps:
            for dest in self.common_jumps[current_page][:2]:
                suggestions.append({
                    "page": dest,
                    "reason": "Readers often jump here next",
                    "source": "interaction"
                })
        
        # From landmarks
        current_landmarks = self.artifacts.get_landmarks_for_page(current_page)
        for lm in current_landmarks:
            for related_id in lm.related_ids[:2]:
                # Find the related landmark
                for other in self.artifacts.all_landmarks:
                    if other.id == related_id:
                        suggestions.append({
                            "page": other.pages.start,
                            "reason": f"Related: {other.label}",
                            "source": "landmark"
                        })
                        break
        
        return suggestions[:3]  # Max 3 suggestions
