"""
Agents module - pure, stateless LLM wrappers.

THE THREE AGENTS:
1. Intent Classifier - query → domain
2. Reading Router - domain → chapters  
3. Text Companion - selected text → clarification

RULES:
- Agents NEVER touch the database
- Agents return structured outputs
- Agents refuse when out of scope
- Agents fail closed, not creatively
"""

