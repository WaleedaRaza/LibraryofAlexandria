"""
Alexandria Library - Agent Contracts
THIS FILE IS SACRED.

All agent inputs and outputs are defined here.
No agent may deviate from these contracts.
If a contract is wrong, fix it here - don't work around it.

RULES:
- All agents return structured outputs (dataclasses)
- All agents can refuse (is_valid=False, refusal_reason set)
- No agent may produce free-form answers
- No agent may access data not in its input
"""

from dataclasses import dataclass, field
from typing import List, Optional


# =============================================================================
# INTENT CLASSIFIER CONTRACTS
# =============================================================================

@dataclass
class DomainMatch:
    """
    A single domain match with optional subdomain.
    """
    domain: str                     # Philosophy, Strategy, etc.
    subdomain: Optional[str]        # More specific: Stoicism, Game Theory, etc.
    confidence: float               # 0.0 to 1.0


@dataclass
class IntentResult:
    """
    Output of Intent Classifier.
    
    Maps a user question to 1-3 conceptual domains.
    Returns MULTIPLE domains when a question spans knowledge areas.
    Does NOT select books - that's the Reading Router's job.
    
    Example: "Why does my boss act like that?"
    - Strategy/Power Dynamics (0.9)
    - Psychology/Organizational (0.7)
    - Sociology/Institutions (0.5)
    """
    matches: List[DomainMatch] = field(default_factory=list)  # 1-3 domain matches
    is_valid: bool = True          # False if we can't/shouldn't route
    refusal_reason: Optional[str] = None  # Why we refused (if is_valid=False)
    
    # Convenience properties for backward compatibility
    @property
    def domain(self) -> str:
        """Primary domain (highest confidence)."""
        return self.matches[0].domain if self.matches else "Philosophy"
    
    @property
    def subdomain(self) -> Optional[str]:
        """Primary subdomain."""
        return self.matches[0].subdomain if self.matches else None
    
    @property
    def confidence(self) -> float:
        """Primary confidence."""
        return self.matches[0].confidence if self.matches else 0.0
    
    # FORBIDDEN fields (do not add):
    # - answer: str  (we don't answer, we route)
    # - books: list  (that's Reading Router's job)
    # - summary: str (we don't summarize)


# =============================================================================
# READING ROUTER CONTRACTS
# =============================================================================

@dataclass
class ReadingRecommendation:
    """
    A single reading recommendation.
    Points to a specific place to read.
    """
    book_id: str
    book_title: str
    book_author: str
    chapter_id: str             # References chapters.id
    chapter_number: int
    chapter_title: str
    rationale: str              # Why read this (1-2 sentences, no spoilers)
    
    # FORBIDDEN fields (do not add):
    # - summary: str (they should read it)
    # - key_points: list (they should discover them)
    # - answer: str (the text IS the answer)
    # - relevance_score: float (no ranking theater)


@dataclass
class ReadingPath:
    """
    A conceptual angle of approach to the question.
    Each path represents a DIFFERENT way to understand the problem.
    
    Example for "Why does my boss act like that?":
    - Path 1: Power dynamics (48 Laws of Power)
    - Path 2: Organizational behavior (Thinking in Systems)
    - Path 3: Moral psychology (The Righteous Mind)
    
    These are NOT ranked. They are PARALLEL.
    The user chooses which angle resonates.
    """
    angle: str                  # e.g., "Power dynamics", "Organizational behavior"
    recommendations: List[ReadingRecommendation] = field(default_factory=list)
    
    # FORBIDDEN fields:
    # - priority: int (paths are parallel, not ranked)
    # - summary: str (no summarizing the angle)


@dataclass
class RoutingResult:
    """
    Output of Reading Router.
    
    Given a domain and available books, returns PARALLEL reading paths.
    Each path is a different angle of approach.
    Returns 1-3 paths, each with 1-2 recommendations.
    Total max: 5 recommendations across all paths.
    """
    paths: List[ReadingPath] = field(default_factory=list)
    is_valid: bool = True
    refusal_reason: Optional[str] = None
    
    # FORBIDDEN fields:
    # - answer: str (reading IS the answer)
    # - synthesis: str (no cross-book synthesis)
    # - rationale: str (each path has its own angle)
    
    @property
    def recommendations(self) -> List[ReadingRecommendation]:
        """Flatten all paths into a single list for backward compatibility."""
        return [rec for path in self.paths for rec in path.recommendations]
    
    @property
    def total_count(self) -> int:
        """Total number of recommendations across all paths."""
        return sum(len(path.recommendations) for path in self.paths)


# =============================================================================
# TEXT COMPANION CONTRACTS
# =============================================================================

@dataclass
class TextSpan:
    """
    A specific span of text within a chapter.
    This is what the user has selected.
    
    INVARIANT: The text must be sliced from book_text.content
    using the chapter's offsets + this span's offsets.
    """
    start_offset: int   # Offset within chapter text
    end_offset: int     # Offset within chapter text
    text: str           # The actual text (for verification)
    
    def __post_init__(self):
        # Validate span
        if self.start_offset < 0:
            raise ValueError("start_offset must be non-negative")
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")
        if len(self.text) != (self.end_offset - self.start_offset):
            raise ValueError("text length must match offset range")


@dataclass
class CompanionRequest:
    """
    Input to Text Companion.
    
    ALL fields are REQUIRED. The companion cannot operate without context.
    This prevents out-of-scope questions.
    """
    book_id: str        # Which book
    chapter_id: str     # Which chapter
    text_span: TextSpan # What text is selected
    question: str       # What user is asking about the text
    
    # FORBIDDEN fields:
    # - general_question: str (must be about the text)
    # - context: str (we don't accept external context)


@dataclass
class CompanionResponse:
    """
    Output of Text Companion.
    
    Explains ONLY the selected text span.
    Does NOT:
    - Give general advice
    - Make modern extrapolations
    - Synthesize across books
    - Answer questions not about the text
    """
    explanation: str                # Clarification of the text
    is_valid: bool = True
    refusal_reason: Optional[str] = None
    suggested_chapter: Optional[str] = None  # If question is out of scope, suggest where to look
    
    # FORBIDDEN fields:
    # - advice: str (we clarify, not advise)
    # - application: str (no modern application)
    # - related_texts: list (no cross-book in V1)


# =============================================================================
# VALIDATION HELPERS
# =============================================================================

VALID_DOMAINS = [
    # Core Knowledge
    "Philosophy",
    "Strategy",
    "Psychology",
    "Economics",
    "Business",
    "Technology",
    
    # Humanities
    "History",
    "Literature",
    "Politics",
    "Religion",
    "Art",
    "Sociology",
    
    # Sciences
    "Science",
    "Mathematics",
    "Medicine",
    
    # Applied
    "Law",
    "Education",
    "Communication",
]

VALID_SUBDOMAINS = {
    # Core Knowledge
    "Philosophy": [
        "Stoicism", "Ethics", "Existentialism", "Epistemology", 
        "Metaphysics", "Political Philosophy", "Eastern Philosophy", "Logic"
    ],
    "Strategy": [
        "Military Strategy", "Power Dynamics", "Negotiation", "Game Theory",
        "Geopolitics", "Competitive Strategy", "Decision Theory"
    ],
    "Psychology": [
        "Cognitive Science", "Social Psychology", "Behavioral Economics", 
        "Developmental Psychology", "Clinical Psychology", "Evolutionary Psychology",
        "Organizational Psychology", "Neuroscience"
    ],
    "Economics": [
        "Microeconomics", "Macroeconomics", "Political Economy", "Finance",
        "Development Economics", "Economic History", "Monetary Theory"
    ],
    "Business": [
        "Management", "Leadership", "Entrepreneurship", "Marketing",
        "Operations", "Organizational Behavior", "Innovation", "Finance"
    ],
    "Technology": [
        "Software Engineering", "Systems Design", "Security", "Databases",
        "Artificial Intelligence", "Networks", "Cryptography", "Architecture"
    ],
    
    # Humanities
    "History": [
        "Ancient History", "Medieval History", "Modern History", "Military History",
        "Economic History", "Cultural History", "Historiography"
    ],
    "Literature": [
        "Fiction", "Poetry", "Drama", "Classics", "Literary Criticism",
        "Rhetoric", "Narrative", "Mythology"
    ],
    "Politics": [
        "Political Theory", "Governance", "International Relations", "Democracy",
        "Authoritarianism", "Revolutions", "Policy"
    ],
    "Religion": [
        "Theology", "Spirituality", "Comparative Religion", "Mysticism",
        "Religious History", "Ethics", "Sacred Texts"
    ],
    "Art": [
        "Aesthetics", "Art History", "Design", "Creativity",
        "Visual Arts", "Music", "Architecture"
    ],
    "Sociology": [
        "Social Theory", "Culture", "Institutions", "Class",
        "Race", "Gender", "Urbanization", "Social Movements"
    ],
    
    # Sciences
    "Science": [
        "Physics", "Biology", "Chemistry", "Complexity",
        "Evolution", "Ecology", "Cosmology", "Scientific Method"
    ],
    "Mathematics": [
        "Logic", "Statistics", "Probability", "Game Theory",
        "Geometry", "Number Theory", "Applied Mathematics"
    ],
    "Medicine": [
        "Anatomy", "Physiology", "Public Health", "Nutrition",
        "Mental Health", "Disease", "Longevity"
    ],
    
    # Applied
    "Law": [
        "Legal Theory", "Constitutional Law", "Criminal Law", "International Law",
        "Justice", "Rights", "Regulation"
    ],
    "Education": [
        "Pedagogy", "Learning Theory", "Curriculum", "Assessment",
        "Higher Education", "Self-Education"
    ],
    "Communication": [
        "Rhetoric", "Persuasion", "Media", "Journalism",
        "Public Speaking", "Writing", "Propaganda"
    ],
}


def validate_domain(domain: str) -> bool:
    """Check if domain is valid."""
    return domain in VALID_DOMAINS


def validate_subdomain(domain: str, subdomain: str) -> bool:
    """Check if subdomain is valid for given domain."""
    if domain not in VALID_SUBDOMAINS:
        return True  # Domain has no defined subdomains, accept any
    return subdomain in VALID_SUBDOMAINS[domain]

