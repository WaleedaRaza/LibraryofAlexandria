"""
Alexandria Library - Intent Classifier Agent

PURPOSE: Map user input → 1-3 conceptual domains
FORBIDDEN: answers, book selection, analysis

This agent determines WHAT domains a question touches.
It returns MULTIPLE domains when questions span knowledge areas.
It does NOT select books or chapters.
It does NOT answer questions.
"""

from typing import List
from ..config import settings
from .contracts import IntentResult, DomainMatch, VALID_DOMAINS, VALID_SUBDOMAINS, validate_domain
from .llm_provider import get_llm_provider


class IntentClassifier:
    """
    Classifies user questions into 1-3 domains.
    
    Returns multiple domain matches when a question
    touches multiple areas of knowledge.
    
    Stateless. Pure. Replaceable.
    """
    
    def classify(self, question: str) -> IntentResult:
        """
        Classify a question into a domain.
        
        Returns IntentResult with domain and subdomain.
        Returns is_valid=False if we can't or shouldn't route.
        """
        if settings.USE_MOCK_AGENTS:
            return self._mock_classify(question)
        return self._llm_classify(question)
    
    def _mock_classify(self, question: str) -> IntentResult:
        """
        Mock classifier for development.
        Returns 1-3 domain matches using keyword detection.
        """
        question_lower = question.lower()
        matches: List[DomainMatch] = []
        
        # Check for off-topic / garbage
        off_topic_signals = ["fix my car", "weather", "recipe", "cook", "ignore previous", "asdf"]
        if any(signal in question_lower for signal in off_topic_signals):
            return IntentResult(
                matches=[],
                is_valid=False,
                refusal_reason="Question is not about books in our library domains"
            )
        
        # ═══════════════════════════════════════════════════════════════
        # DOMAIN DETECTION - Check all domains, collect matches
        # ═══════════════════════════════════════════════════════════════
        
        # PHILOSOPHY
        if any(w in question_lower for w in ["stoic", "marcus aurelius", "meditations", "control", "accept"]):
            matches.append(DomainMatch("Philosophy", "Stoicism", 0.90))
        elif any(w in question_lower for w in ["virtue", "ethics", "moral", "right", "wrong", "duty"]):
            matches.append(DomainMatch("Philosophy", "Ethics", 0.85))
        elif any(w in question_lower for w in ["meaning", "death", "existence", "purpose", "suffer"]):
            matches.append(DomainMatch("Philosophy", "Existentialism", 0.80))
        elif any(w in question_lower for w in [
            "philosophy", "wisdom", "truth", "knowledge",
            "substance", "being", "essence", "metaphysics", "aristotle",
            "cause", "causality", "form", "matter", "potentiality", "actuality",
        ]):
            matches.append(DomainMatch("Philosophy", "Metaphysics", 0.80))
        
        # STRATEGY
        if any(w in question_lower for w in ["war", "sun tzu", "battle", "military", "enemy", "defeat"]):
            matches.append(DomainMatch("Strategy", "Military Strategy", 0.90))
        elif any(w in question_lower for w in ["power", "machiavelli", "influence", "manipulation", "boss", "authority"]):
            matches.append(DomainMatch("Strategy", "Power Dynamics", 0.85))
        elif any(w in question_lower for w in ["negotiate", "deal", "bargain", "persuade", "convince"]):
            matches.append(DomainMatch("Strategy", "Negotiation", 0.85))
        elif any(w in question_lower for w in ["strategy", "tactics", "compete", "win"]):
            matches.append(DomainMatch("Strategy", None, 0.70))
        
        # PSYCHOLOGY
        if any(w in question_lower for w in ["bias", "decision", "cognitive", "rational", "irrational", "heuristic"]):
            matches.append(DomainMatch("Psychology", "Cognitive Science", 0.85))
        elif any(w in question_lower for w in ["group", "conform", "social", "crowd", "tribe", "peer"]):
            matches.append(DomainMatch("Psychology", "Social Psychology", 0.80))
        elif any(w in question_lower for w in ["organization", "workplace", "team dynamics"]):
            matches.append(DomainMatch("Psychology", "Organizational Psychology", 0.80))
        elif any(w in question_lower for w in ["mind", "behavior", "brain", "emotion", "habit", "think"]):
            matches.append(DomainMatch("Psychology", None, 0.70))
        
        # ECONOMICS
        if any(w in question_lower for w in ["market", "price", "supply", "demand", "trade"]):
            matches.append(DomainMatch("Economics", "Microeconomics", 0.85))
        elif any(w in question_lower for w in ["inflation", "gdp", "recession", "monetary"]):
            matches.append(DomainMatch("Economics", "Macroeconomics", 0.85))
        elif any(w in question_lower for w in ["economics", "economy", "money", "capitalism", "incentive"]):
            matches.append(DomainMatch("Economics", None, 0.75))
        
        # BUSINESS
        if any(w in question_lower for w in ["lead", "leader", "leadership", "manage", "ceo"]):
            matches.append(DomainMatch("Business", "Leadership", 0.85))
        elif any(w in question_lower for w in ["startup", "entrepreneur", "founder", "venture", "company"]):
            matches.append(DomainMatch("Business", "Entrepreneurship", 0.85))
        elif any(w in question_lower for w in ["business", "organization", "corporate"]):
            matches.append(DomainMatch("Business", None, 0.70))
        
        # TECHNOLOGY
        if any(w in question_lower for w in ["code", "software", "programming", "developer"]):
            matches.append(DomainMatch("Technology", "Software Engineering", 0.90))
        elif any(w in question_lower for w in ["system", "distributed", "scale", "architecture"]):
            matches.append(DomainMatch("Technology", "Systems Design", 0.85))
        elif any(w in question_lower for w in ["security", "hack", "cryptography", "vulnerability"]):
            matches.append(DomainMatch("Technology", "Security", 0.90))
        elif any(w in question_lower for w in ["technology", "computer", "digital", "ai"]):
            matches.append(DomainMatch("Technology", None, 0.70))
        
        # HISTORY
        if any(w in question_lower for w in ["history", "historical", "ancient", "medieval", "empire", "civilization"]):
            matches.append(DomainMatch("History", None, 0.80))
        elif any(w in question_lower for w in ["revolution", "war", "dynasty", "era"]):
            matches.append(DomainMatch("History", None, 0.70))
        
        # POLITICS
        if any(w in question_lower for w in ["government", "democracy", "authoritarian", "state", "policy"]):
            matches.append(DomainMatch("Politics", "Political Theory", 0.85))
        elif any(w in question_lower for w in ["politics", "political", "ideology", "revolution"]):
            matches.append(DomainMatch("Politics", None, 0.75))
        
        # RELIGION
        if any(w in question_lower for w in ["god", "spiritual", "religion", "faith", "soul", "divine", "pray", "worship", "sacred", "holy"]):
            matches.append(DomainMatch("Religion", "Spirituality", 0.85))
        elif any(w in question_lower for w in ["meditation", "enlightenment", "buddhism", "zen"]):
            matches.append(DomainMatch("Religion", "Eastern Philosophy", 0.80))
        
        # SOCIOLOGY
        if any(w in question_lower for w in ["society", "culture", "class", "inequality", "institution"]):
            matches.append(DomainMatch("Sociology", "Social Theory", 0.80))
        
        # SCIENCE
        if any(w in question_lower for w in ["physics", "biology", "chemistry", "evolution", "nature"]):
            matches.append(DomainMatch("Science", None, 0.80))
        elif any(w in question_lower for w in ["complex", "chaos", "emergence", "systems thinking"]):
            matches.append(DomainMatch("Science", "Complexity", 0.80))
        
        # MEDICINE
        if any(w in question_lower for w in ["health", "disease", "doctor", "medical", "longevity", "aging", "live longer", "diet", "nutrition", "exercise"]):
            matches.append(DomainMatch("Medicine", None, 0.85))
        elif any(w in question_lower for w in ["mental health", "therapy", "depression", "anxiety treatment"]):
            matches.append(DomainMatch("Medicine", "Mental Health", 0.85))
        
        # LITERATURE
        if any(w in question_lower for w in ["story", "narrative", "fiction", "novel", "myth", "hero", "journey", "archetype", "poem", "poetry"]):
            matches.append(DomainMatch("Literature", None, 0.80))
        elif any(w in question_lower for w in ["rhetoric", "writing", "persuasion"]):
            matches.append(DomainMatch("Communication", "Rhetoric", 0.80))
        
        # LAW
        if any(w in question_lower for w in ["law", "legal", "justice", "rights", "court"]):
            matches.append(DomainMatch("Law", None, 0.85))
        
        # ART
        if any(w in question_lower for w in ["art", "beauty", "aesthetic", "creativity", "design"]):
            matches.append(DomainMatch("Art", "Aesthetics", 0.75))
        
        # ═══════════════════════════════════════════════════════════════
        # MULTI-DOMAIN PATTERNS - Questions that naturally span domains
        # ═══════════════════════════════════════════════════════════════
        
        # "Why does my boss act like that?" → Strategy + Psychology + Sociology
        if "boss" in question_lower or "manager" in question_lower:
            if not any(m.domain == "Strategy" for m in matches):
                matches.append(DomainMatch("Strategy", "Power Dynamics", 0.85))
            if not any(m.domain == "Psychology" for m in matches):
                matches.append(DomainMatch("Psychology", "Organizational Psychology", 0.75))
        
        # Death/meaning → Philosophy + Religion + Psychology
        if "death" in question_lower or "die" in question_lower:
            if not any(m.domain == "Philosophy" for m in matches):
                matches.append(DomainMatch("Philosophy", "Existentialism", 0.85))
            if not any(m.domain == "Religion" for m in matches):
                matches.append(DomainMatch("Religion", "Spirituality", 0.70))
        
        # "How do markets work?" → Economics + Psychology + History
        if "market" in question_lower:
            if not any(m.domain == "Economics" for m in matches):
                matches.append(DomainMatch("Economics", None, 0.85))
            if not any(m.domain == "Psychology" for m in matches):
                matches.append(DomainMatch("Psychology", "Behavioral Economics", 0.65))
        
        # ═══════════════════════════════════════════════════════════════
        # FINALIZE
        # ═══════════════════════════════════════════════════════════════
        
        # Remove duplicates by domain, keep highest confidence
        seen_domains = {}
        for m in matches:
            if m.domain not in seen_domains or m.confidence > seen_domains[m.domain].confidence:
                seen_domains[m.domain] = m
        
        matches = list(seen_domains.values())
        
        # Sort by confidence descending
        matches.sort(key=lambda m: m.confidence, reverse=True)
        
        # Limit to top 3
        matches = matches[:3]
        
        # If no matches, default to Philosophy
        if not matches:
            matches = [DomainMatch("Philosophy", None, 0.50)]
        
        return IntentResult(matches=matches, is_valid=True)
    
    def _llm_classify(self, question: str) -> IntentResult:
        """
        Real LLM classification with structured output.
        
        Returns:
            IntentResult with 1-3 domain matches, or refusal if unclassifiable
        """
        try:
            provider = get_llm_provider()
            
            # Build domain list from contracts
            domain_descriptions = """
PHILOSOPHY - Meaning, ethics, virtue, how to live, death, existence, truth, wisdom
  Subdomains: Stoicism, Ethics, Existentialism, Epistemology, Metaphysics, Eastern Philosophy

STRATEGY - Conflict, competition, power, influence, tactics, winning, positioning
  Subdomains: Military Strategy, Power Dynamics, Negotiation, Game Theory, Geopolitics

PSYCHOLOGY - Mind, behavior, decisions, biases, emotions, cognition, development
  Subdomains: Cognitive Science, Social Psychology, Behavioral Economics, Organizational Psychology, Neuroscience

ECONOMICS - Markets, money, trade, incentives, policy, finance, growth
  Subdomains: Microeconomics, Macroeconomics, Political Economy, Finance, Development Economics

BUSINESS - Management, leadership, organizations, startups, operations, innovation
  Subdomains: Management, Leadership, Entrepreneurship, Marketing, Organizational Behavior

TECHNOLOGY - Systems, software, engineering, architecture, security, networks
  Subdomains: Software Engineering, Systems Design, Security, Databases, AI, Architecture

HISTORY - Past events, civilizations, eras, patterns, causes, consequences
  Subdomains: Ancient History, Medieval History, Modern History, Military History, Economic History

POLITICS - Government, power, ideology, policy, democracy, international relations
  Subdomains: Political Theory, Governance, International Relations, Democracy, Revolutions

RELIGION - Faith, spirituality, theology, sacred texts, meaning, transcendence
  Subdomains: Theology, Spirituality, Comparative Religion, Mysticism, Eastern Religion

SOCIOLOGY - Society, culture, institutions, class, identity, social movements
  Subdomains: Social Theory, Culture, Institutions, Class, Social Movements

SCIENCE - Physics, biology, chemistry, complexity, evolution, scientific method
  Subdomains: Physics, Biology, Complexity, Evolution, Ecology, Scientific Method

LITERATURE - Narrative, fiction, poetry, myth, rhetoric, classics
  Subdomains: Fiction, Poetry, Classics, Literary Criticism, Mythology, Rhetoric

LAW - Justice, rights, legal theory, constitutions, regulation
  Subdomains: Legal Theory, Constitutional Law, International Law, Justice, Rights

ART - Aesthetics, beauty, creativity, design, visual arts, music
  Subdomains: Aesthetics, Art History, Design, Creativity, Visual Arts

MATHEMATICS - Logic, statistics, probability, game theory, reasoning
  Subdomains: Logic, Statistics, Probability, Game Theory, Applied Mathematics

COMMUNICATION - Rhetoric, persuasion, media, writing, public speaking
  Subdomains: Rhetoric, Persuasion, Media, Writing, Public Speaking
"""
            
            system_prompt = f"""You classify questions into 1-3 knowledge domains for a curated book library.

YOUR JOB: Return 1-3 domains that this question touches. Most questions span multiple areas of knowledge.
YOU DO NOT: Answer questions, recommend books, or provide information.

VALID DOMAINS:
{domain_descriptions}

MULTI-DOMAIN EXAMPLES:

Q: "Why does my boss act like that?"
{{"matches": [
  {{"domain": "Strategy", "subdomain": "Power Dynamics", "confidence": 0.9}},
  {{"domain": "Psychology", "subdomain": "Organizational Psychology", "confidence": 0.75}},
  {{"domain": "Sociology", "subdomain": "Institutions", "confidence": 0.6}}
]}}

Q: "How do I deal with fear of death?"
{{"matches": [
  {{"domain": "Philosophy", "subdomain": "Existentialism", "confidence": 0.9}},
  {{"domain": "Religion", "subdomain": "Spirituality", "confidence": 0.8}},
  {{"domain": "Psychology", "subdomain": "Cognitive Science", "confidence": 0.65}}
]}}

Q: "Why do markets crash?"
{{"matches": [
  {{"domain": "Economics", "subdomain": "Macroeconomics", "confidence": 0.9}},
  {{"domain": "Psychology", "subdomain": "Behavioral Economics", "confidence": 0.75}},
  {{"domain": "History", "subdomain": "Economic History", "confidence": 0.6}}
]}}

Q: "How do I write clean code?"
{{"matches": [
  {{"domain": "Technology", "subdomain": "Software Engineering", "confidence": 0.95}}
]}}

Q: "What makes a good leader?"
{{"matches": [
  {{"domain": "Business", "subdomain": "Leadership", "confidence": 0.9}},
  {{"domain": "Strategy", "subdomain": "Power Dynamics", "confidence": 0.75}},
  {{"domain": "Psychology", "subdomain": "Social Psychology", "confidence": 0.6}}
]}}

Q: "How did Rome fall?"
{{"matches": [
  {{"domain": "History", "subdomain": "Ancient History", "confidence": 0.95}},
  {{"domain": "Politics", "subdomain": "Governance", "confidence": 0.7}}
]}}

SINGLE-DOMAIN EXAMPLES (when truly single-focus):

Q: "What is Stoicism?"
{{"matches": [{{"domain": "Philosophy", "subdomain": "Stoicism", "confidence": 0.95}}]}}

Q: "Explain SQL joins"
{{"matches": [{{"domain": "Technology", "subdomain": "Databases", "confidence": 0.95}}]}}

REFUSAL EXAMPLES:

Q: "How do I fix my car?"
{{"is_valid": false, "refusal_reason": "Automotive repair is not in our library"}}

Q: "What's the weather?"
{{"is_valid": false, "refusal_reason": "Real-time information, not books"}}

Q: "asdfasdf"
{{"is_valid": false, "refusal_reason": "Question not understood"}}

RULES:
1. Return 1-3 domain matches (most questions span 2-3 domains)
2. Only return 1 domain if the question is truly narrow and specific
3. Confidence: 0.9+ for primary match, descending for secondary
4. Only use domains from the list above
5. If off-topic, set is_valid: false

RESPOND WITH ONLY VALID JSON. No markdown."""

            result = provider.call(
                system_prompt=system_prompt,
                user_prompt=question,
                agent_name="IntentClassifier",
                temperature=0.3,
                max_tokens=300,
                response_format="json"
            )
            
            # Validate and construct response
            is_valid = result.get("is_valid", True)
            
            if not is_valid:
                return IntentResult(
                    matches=[],
                    is_valid=False,
                    refusal_reason=result.get("refusal_reason", "Unable to classify query")
                )
            
            # Parse matches array
            raw_matches = result.get("matches", [])
            
            # Handle legacy single-domain format (backward compat)
            if not raw_matches and result.get("domain"):
                raw_matches = [{
                    "domain": result.get("domain"),
                    "subdomain": result.get("subdomain"),
                    "confidence": result.get("confidence", 0.5)
                }]
            
            matches: List[DomainMatch] = []
            for m in raw_matches[:3]:  # Max 3 matches
                domain = m.get("domain", "Philosophy")
                subdomain = m.get("subdomain")
                confidence = float(m.get("confidence", 0.5))
                
                # Validate domain against whitelist
                if not validate_domain(domain):
                    # LLM hallucinated a domain - skip it
                    continue
                
                # Clamp confidence to [0, 1]
                confidence = max(0.0, min(1.0, confidence))
                
                matches.append(DomainMatch(
                    domain=domain,
                    subdomain=subdomain,
                    confidence=confidence
                ))
            
            # If no valid matches, default to Philosophy
            if not matches:
                matches = [DomainMatch("Philosophy", None, 0.5)]
            
            return IntentResult(matches=matches, is_valid=True)
            
        except ValueError as e:
            # JSON parsing error - LLM returned malformed response
            return IntentResult(
                matches=[DomainMatch("Philosophy", None, 0.3)],
                is_valid=True
            )
        except Exception as e:
            # Any other error (API timeout, etc.) - fail closed
            return IntentResult(
                matches=[DomainMatch("Philosophy", None, 0.3)],
                is_valid=True
            )
