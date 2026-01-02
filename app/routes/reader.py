"""
Alexandria Library - Reader Route
The core reading experience. Fetch text + highlights, render reader.
"""

from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse

from .. import templates
from ..services.canon_service import CanonService
from ..services.user_service import UserService
from ..middleware.rate_limit import rate_limit
from .auth import get_current_user_optional, get_current_user_required

router = APIRouter()


@router.get("/{book_id}", response_class=HTMLResponse)
async def read_book(
    request: Request,
    book_id: str,
    chapter: int = 1,
    context: str = None,  # Routing context - why user was directed here
    user=Depends(get_current_user_optional)
):
    """
    Display the reader for a book.
    This is where reading happens.
    
    Args:
        book_id: The book to read
        chapter: Chapter number (default 1)
        context: Optional routing context explaining why user was sent here
    """
    canon = CanonService()
    
    # Get book metadata
    book = canon.get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Get chapters for navigation
    chapters = canon.get_chapters(book_id)
    if not chapters:
        raise HTTPException(status_code=404, detail="No chapters found")
    
    # Get current chapter
    current_chapter = canon.get_chapter_by_number(book_id, chapter)
    if not current_chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    # Get chapter text (extracted from book_text using offsets)
    chapter_text = canon.get_chapter_text(book_id, current_chapter["id"])
    
    # Get user's highlights + annotations for this chapter
    annotations = []
    user_service = UserService()
    
    # Use logged-in user or anonymous test user
    user_id = user["id"] if user else "anon_test_user"
    raw_highlights = user_service.get_highlights(user_id, current_chapter["id"])
    
    # Enrich highlights with text snippets and annotations
    for hl in raw_highlights:
        start = hl["start_offset"]
        end = hl["end_offset"]
        snippet = chapter_text[start:end][:80]  # First 80 chars
        if len(chapter_text[start:end]) > 80:
            snippet += "..."
        
        # Get annotation for this highlight
        annotation = user_service.get_annotation(hl["id"])
        
        annotations.append({
            "id": hl["id"],
            "type": "user",
            "quoted_text": snippet,
            "text": annotation["text"] if annotation else None,
            "annotation_id": annotation["id"] if annotation else None,
            "color": hl["color"],
            "created_at": hl["created_at"],
            "start_offset": start,
            "end_offset": end,
        })
    
    return templates.TemplateResponse(
        "reader.html",
        {
            "request": request,
            "user": user,
            "book": book,
            "chapters": chapters,
            "current_chapter": current_chapter,
            "chapter_text": chapter_text,
            "annotations": annotations,
            "routing_context": context,  # Pass to template for display
        }
    )


@router.post("/{book_id}/highlight", response_class=JSONResponse)
async def create_highlight(
    request: Request,
    book_id: str,
    chapter_id: str = Form(...),
    start_offset: int = Form(...),
    end_offset: int = Form(...),
    color: str = Form("yellow"),
    user=Depends(get_current_user_optional)
):
    """
    Create a highlight.
    
    Offsets are relative to chapter text (not book text).
    Highlights are private - no sharing, no reactions.
    
    NOTE: Auth temporarily optional for testing. Uses anonymous user if not logged in.
    """
    user_service = UserService()
    
    # Use anonymous user ID if not logged in (for testing)
    user_id = user["id"] if user else "anon_test_user"
    
    highlight = user_service.create_highlight(
        user_id=user_id,
        chapter_id=chapter_id,
        start_offset=start_offset,
        end_offset=end_offset,
        color=color
    )
    
    return {"success": True, "highlight_id": highlight["id"]}


@router.delete("/{book_id}/highlight/{highlight_id}", response_class=JSONResponse)
async def delete_highlight(
    request: Request,
    book_id: str,
    highlight_id: str,
    user=Depends(get_current_user_optional)
):
    """Delete a highlight. Only owner can delete."""
    user_service = UserService()
    
    user_id = user["id"] if user else "anon_test_user"
    deleted = user_service.delete_highlight(highlight_id, user_id)
    
    if not deleted:
        raise HTTPException(status_code=404, detail="Highlight not found or not owned by you")
    
    return {"success": True}


@router.post("/{book_id}/annotation", response_class=JSONResponse)
async def create_annotation(
    request: Request,
    book_id: str,
    highlight_id: str = Form(...),
    text: str = Form(...),
    user=Depends(get_current_user_optional)
):
    """
    Create or update annotation for a highlight.
    
    Annotations are private notes attached to highlights.
    One annotation per highlight (upsert behavior).
    
    NOTE: Auth temporarily optional for testing.
    """
    user_service = UserService()
    
    annotation = user_service.create_annotation(highlight_id, text)
    
    return {"success": True, "annotation_id": annotation["id"]}


@router.delete("/{book_id}/annotation/{annotation_id}", response_class=JSONResponse)
async def delete_annotation(
    request: Request,
    book_id: str,
    annotation_id: str,
    user=Depends(get_current_user_optional)
):
    """Delete an annotation. NOTE: Auth temporarily optional for testing."""
    user_service = UserService()
    
    deleted = user_service.delete_annotation(annotation_id)
    
    if not deleted:
        raise HTTPException(status_code=404, detail="Annotation not found")
    
    return {"success": True}


@router.post("/{book_id}/chat", response_class=HTMLResponse)
@rate_limit(requests=30, window=60, endpoint_type="chat")
async def section_chat(
    request: Request,
    book_id: str,
    chapter_id: str = Form(...),
    start_offset: int = Form(0),
    end_offset: int = Form(0),
    selected_text: str = Form(...),
    question: str = Form(...),
    routing_context: str = Form(None),  # Optional context from routing
    user=Depends(get_current_user_optional)
):
    """
    Chat about selected text. The Text Companion answers questions
    about meaning, context, implications - grounded in the passage.
    """
    from ..services.agent_service import AgentService
    import logging
    
    agent_service = AgentService()
    canon = CanonService()
    
    # Get context
    book = canon.get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    chapter = canon.get_chapter(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    # Validate we have some text
    if not selected_text or not selected_text.strip():
        raise HTTPException(status_code=400, detail="No text selected")
    
    if not question or not question.strip():
        raise HTTPException(status_code=400, detail="No question provided")
    
    logging.info(f"Chat request: book={book_id}, chapter={chapter_id}, question={question[:50]}...")
    
    # Ask the Text Companion
    response = agent_service.ask_text_companion(
        book_title=book["title"],
        chapter_title=chapter["title"],
        selected_text=selected_text.strip(),
        question=question.strip(),
        routing_context=routing_context
    )
    
    logging.info(f"Chat response: is_valid={response.is_valid}, explanation_len={len(response.explanation or '')}")
    
    return templates.TemplateResponse(
        "partials/chat_response.html",
        {
            "request": request,
            "response": response,
            "book": book,
            "chapter": chapter,
        }
    )

