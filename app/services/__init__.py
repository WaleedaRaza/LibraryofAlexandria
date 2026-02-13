"""
Services module — business logic.

Key services:
  agent_service   Orchestrates intent → router → companion
  artifact_loader Loads artifact JSON from taxonomy-pipeline (canon)
  canon_service   Book/chapter/text access (wraps artifact_loader)
  user_service    Highlights, annotations (SQLite)
  chat_service    Chat messages per highlight
"""
