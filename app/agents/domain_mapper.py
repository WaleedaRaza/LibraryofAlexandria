"""
Alexandria Library - Domain Mapper
Maps between human-readable domain names and stable domain IDs.

This allows the IntentClassifier to continue returning human-readable strings
while the taxonomy gate operates on stable IDs.
"""

from typing import Optional, Tuple


# Bidirectional mapping between display names and IDs
DOMAIN_NAME_TO_ID = {
    # Core Knowledge
    "Philosophy": "philosophy",
    "Strategy": "strategy",
    "Psychology": "psychology",
    "Technology": "technology",
    "Economics": "economics",
    "Business": "business",
    
    # Humanities
    "History": "history",
    "Literature": "literature",
    "Politics": "politics",
    "Religion": "religion",
    "Art": "art",
    "Sociology": "sociology",
    
    # Sciences
    "Science": "science",
    "Mathematics": "mathematics",
    "Medicine": "medicine",
    
    # Applied
    "Law": "law",
    "Education": "education",
    "Communication": "communication",
    
    # Legacy mappings
    "Security": "technology",  # Map to technology
    "Self-Improvement": "psychology",  # Map to psychology
}

DOMAIN_ID_TO_NAME = {
    # Core Knowledge
    "philosophy": "Philosophy",
    "strategy": "Strategy",
    "psychology": "Psychology",
    "technology": "Technology",
    "economics": "Economics",
    "business": "Business",
    
    # Humanities
    "history": "History",
    "literature": "Literature",
    "politics": "Politics",
    "religion": "Religion",
    "art": "Art",
    "sociology": "Sociology",
    
    # Sciences
    "science": "Science",
    "mathematics": "Mathematics",
    "medicine": "Medicine",
    
    # Applied
    "law": "Law",
    "education": "Education",
    "communication": "Communication",
}

SUBDOMAIN_NAME_TO_ID = {
    # Philosophy
    "Stoicism": "stoicism",
    "Ethics": "ethics",
    "Epistemology": "epistemology",
    "Metaphysics": "metaphysics",
    "Political Philosophy": "political_philosophy",
    "Existentialism": "existentialism",
    "Eastern Philosophy": "eastern",
    "Logic": "logic",
    
    # Strategy
    "Military Strategy": "military",
    "Power Dynamics": "power",
    "Game Theory": "game_theory",
    "Negotiation": "negotiation",
    "Geopolitics": "geopolitics",
    "Competitive Strategy": "competitive",
    "Decision Theory": "decision",
    
    # Psychology
    "Cognitive Science": "cognitive",
    "Social Psychology": "social",
    "Behavioral Economics": "behavioral",
    "Organizational Psychology": "organizational",
    "Developmental Psychology": "developmental",
    "Clinical Psychology": "clinical",
    "Evolutionary Psychology": "evolutionary",
    "Neuroscience": "neuroscience",
    "Mindfulness": "mindfulness",
    
    # Economics
    "Microeconomics": "micro",
    "Macroeconomics": "macro",
    "Political Economy": "political_economy",
    "Finance": "finance",
    "Development Economics": "development",
    "Economic History": "economic_history",
    "Monetary Theory": "monetary",
    
    # Business
    "Management": "management",
    "Leadership": "leadership",
    "Entrepreneurship": "entrepreneurship",
    "Marketing": "marketing",
    "Operations": "operations",
    "Organizational Behavior": "org_behavior",
    "Innovation": "innovation",
    
    # Technology
    "Software Engineering": "software",
    "Systems Design": "systems",
    "Security": "security",
    "Databases": "databases",
    "Artificial Intelligence": "ai",
    "Networks": "networks",
    "Cryptography": "cryptography",
    "Architecture": "architecture",
    
    # History
    "Ancient History": "ancient",
    "Medieval History": "medieval",
    "Modern History": "modern",
    "Military History": "military_history",
    "Cultural History": "cultural",
    "Historiography": "historiography",
    
    # Politics
    "Political Theory": "political_theory",
    "Governance": "governance",
    "International Relations": "international",
    "Democracy": "democracy",
    "Authoritarianism": "authoritarianism",
    "Revolutions": "revolutions",
    "Policy": "policy",
    
    # Religion
    "Theology": "theology",
    "Spirituality": "spirituality",
    "Comparative Religion": "comparative",
    "Mysticism": "mysticism",
    "Religious History": "religious_history",
    "Sacred Texts": "sacred",
    "Eastern Religion": "eastern_religion",
    
    # Sociology
    "Social Theory": "social_theory",
    "Culture": "culture",
    "Institutions": "institutions",
    "Class": "class",
    "Race": "race",
    "Gender": "gender",
    "Social Movements": "movements",
    
    # Science
    "Physics": "physics",
    "Biology": "biology",
    "Chemistry": "chemistry",
    "Complexity": "complexity",
    "Evolution": "evolution",
    "Ecology": "ecology",
    "Scientific Method": "method",
    
    # Literature
    "Fiction": "fiction",
    "Poetry": "poetry",
    "Classics": "classics",
    "Literary Criticism": "criticism",
    "Mythology": "mythology",
    "Rhetoric": "rhetoric",
    "Drama": "drama",
    
    # Law
    "Legal Theory": "legal_theory",
    "Constitutional Law": "constitutional",
    "International Law": "international_law",
    "Criminal Law": "criminal",
    "Justice": "justice",
    "Rights": "rights",
    
    # Art
    "Aesthetics": "aesthetics",
    "Art History": "art_history",
    "Design": "design",
    "Creativity": "creativity",
    "Visual Arts": "visual",
    "Music": "music",
    
    # Mathematics
    "Statistics": "statistics",
    "Probability": "probability",
    "Applied Mathematics": "applied",
    
    # Communication
    "Persuasion": "persuasion",
    "Media": "media",
    "Writing": "writing",
    "Public Speaking": "speaking",
    "Journalism": "journalism",
    "Propaganda": "propaganda",
    
    # Education
    "Pedagogy": "pedagogy",
    "Learning Theory": "learning",
    "Self-Education": "self_education",
    
    # Medicine
    "Anatomy": "anatomy",
    "Public Health": "public_health",
    "Nutrition": "nutrition",
    "Mental Health": "mental_health",
    "Longevity": "longevity",
}

SUBDOMAIN_ID_TO_NAME = {v: k for k, v in SUBDOMAIN_NAME_TO_ID.items()}


def domain_name_to_id(domain_name: str) -> str:
    """
    Convert human-readable domain name to stable ID.
    
    Args:
        domain_name: "Philosophy", "Strategy", etc.
        
    Returns:
        domain_id: "philosophy", "strategy", etc.
    """
    return DOMAIN_NAME_TO_ID.get(domain_name, domain_name.lower())


def domain_id_to_name(domain_id: str) -> str:
    """
    Convert domain ID to human-readable name.
    
    Args:
        domain_id: "philosophy", "strategy", etc.
        
    Returns:
        domain_name: "Philosophy", "Strategy", etc.
    """
    return DOMAIN_ID_TO_NAME.get(domain_id, domain_id.title())


def subdomain_name_to_id(subdomain_name: Optional[str]) -> Optional[str]:
    """
    Convert human-readable subdomain name to stable ID.
    
    Args:
        subdomain_name: "Stoicism", "Military Strategy", etc.
        
    Returns:
        subdomain_id: "stoicism", "military", etc.
    """
    if not subdomain_name:
        return None
    return SUBDOMAIN_NAME_TO_ID.get(subdomain_name, subdomain_name.lower())


def subdomain_id_to_name(subdomain_id: Optional[str]) -> Optional[str]:
    """
    Convert subdomain ID to human-readable name.
    
    Args:
        subdomain_id: "stoicism", "military", etc.
        
    Returns:
        subdomain_name: "Stoicism", "Military Strategy", etc.
    """
    if not subdomain_id:
        return None
    return SUBDOMAIN_ID_TO_NAME.get(subdomain_id, subdomain_id.title())


def map_to_ids(domain_name: str, subdomain_name: Optional[str]) -> Tuple[str, Optional[str]]:
    """
    Convert domain/subdomain names to IDs.
    
    Args:
        domain_name: Human-readable domain
        subdomain_name: Human-readable subdomain (or None)
        
    Returns:
        Tuple of (domain_id, subdomain_id)
    """
    domain_id = domain_name_to_id(domain_name)
    subdomain_id = subdomain_name_to_id(subdomain_name)
    return (domain_id, subdomain_id)


def map_to_names(domain_id: str, subdomain_id: Optional[str]) -> Tuple[str, Optional[str]]:
    """
    Convert domain/subdomain IDs to names.
    
    Args:
        domain_id: Stable domain ID
        subdomain_id: Stable subdomain ID (or None)
        
    Returns:
        Tuple of (domain_name, subdomain_name)
    """
    domain_name = domain_id_to_name(domain_id)
    subdomain_name = subdomain_id_to_name(subdomain_id)
    return (domain_name, subdomain_name)
