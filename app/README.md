# App Package

FastAPI application. Entry: `app.main`.

---

## Layout

```
app/
├── main.py         Entry, routes, startup
├── config.py       Settings
├── agents/         LLM agents (intent, router, companion)
├── services/       Business logic
├── routes/         HTTP handlers
├── db/             Database (SQLite)
└── domain/         Entity models
```

## Request Flow

```
POST /ask  →  AgentService.route_question()
           →  IntentClassifier + ReadingRouter
           →  routing_results.html

GET /read/<book_id>  →  canon_service.get_chapter_text()
                     →  reader.html + highlights from user_service

POST /read/<book_id>/highlight  →  user_service.create_highlight()
```

## Canon vs User Data

- **Canon:** Artifact JSON files (`taxonomy-pipeline/data/artifacts/`). Immutable. Loaded by `artifact_loader` → `canon_service`.
- **User:** SQLite (`data/alexandria.db`). Highlights, annotations, chat_messages. Managed by `user_service`, `chat_service`.
