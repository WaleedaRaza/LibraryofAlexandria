"""
Alexandria Library - Reader Route
Text reader for artifact-based books. No PDF. No Supabase.
"""

from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse

from .. import templates
from ..services.canon_service import CanonService
from ..services.user_service import UserService
from ..services.chat_service import ChatService, HIGHLIGHT_COLORS
from .auth import get_current_user_optional

router = APIRouter()


# =============================================================================
# READER VIEW
# =============================================================================

@router.get("/{book_id}", response_class=HTMLResponse)
async def read_book(
    request: Request,
    book_id: str,
    chapter: int = 1,
    context: str = None,
    user=Depends(get_current_user_optional)
):
    """Display the text reader for a book section."""
    return await read_book_text(request, book_id, chapter=chapter, context=context, user=user)


async def read_book_text(
    request: Request,
    book_id: str,
    chapter: int = 1,
    context: str = None,
    user=None
):
    """Render the text reader with highlights applied."""
    canon = CanonService()

    book = canon.get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    chapters = canon.get_chapters(book_id)
    if not chapters:
        raise HTTPException(status_code=404, detail="No sections found for this book")

    current_chapter = canon.get_chapter_by_number(book_id, chapter)
    if not current_chapter:
        raise HTTPException(status_code=404, detail="Section not found")

    chapter_text = canon.get_chapter_text(book_id, current_chapter["id"])

    # Get highlights for this section
    user_service = UserService()
    user_id = user["id"] if user else "anon_test_user"
    raw_highlights = user_service.get_highlights(user_id, current_chapter["id"])

    # Build highlights list (rendering happens client-side via JS)
    import html as html_mod
    highlights = []

    for hl in raw_highlights:
        selected_text = hl.get("selected_text", "")
        if not selected_text:
            continue

        annotation = user_service.get_annotation(hl["id"])
        color = hl.get("color", "yellow")
        color_info = HIGHLIGHT_COLORS.get(color, HIGHLIGHT_COLORS["yellow"])

        snippet = selected_text[:100]
        if len(selected_text) > 100:
            snippet += "..."

        highlights.append({
            "id": hl["id"],
            "selected_text": selected_text,
            "snippet": snippet,
            "note": annotation["text"] if annotation else None,
            "color": color,
            "color_label": color_info["label"],
            "color_hex": color_info["hex"],
            "created_at": hl["created_at"],
        })

    # Convert text to paragraphs (no highlight spans — JS applies those)
    escaped_text = html_mod.escape(chapter_text)
    paragraphs = escaped_text.split('\n\n')
    formatted_text = ''.join(f'<p>{p.strip()}</p>' for p in paragraphs if p.strip())

    return templates.TemplateResponse(
        "reader.html",
        {
            "request": request,
            "user": user,
            "book": book,
            "chapters": chapters,
            "current_chapter": current_chapter,
            "chapter_text": formatted_text,
            "highlights": highlights,
            "highlight_colors": HIGHLIGHT_COLORS,
            "routing_context": context,
        }
    )


# =============================================================================
# HIGHLIGHTS
# =============================================================================

@router.post("/{book_id}/highlight", response_class=JSONResponse)
async def create_highlight(
    request: Request,
    book_id: str,
    chapter_id: str = Form(...),
    selected_text: str = Form(...),
    color: str = Form("yellow"),
    user=Depends(get_current_user_optional)
):
    """Create a highlight on selected text."""
    if not selected_text or not selected_text.strip():
        raise HTTPException(status_code=400, detail="No text selected")

    user_service = UserService()
    user_id = user["id"] if user else "anon_test_user"

    highlight = user_service.create_highlight(
        user_id=user_id,
        book_id=book_id,
        section_id=chapter_id,
        selected_text=selected_text.strip(),
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
    """Delete a highlight."""
    user_service = UserService()
    user_id = user["id"] if user else "anon_test_user"
    deleted = user_service.delete_highlight(highlight_id, user_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Highlight not found or not owned by you")

    return {"success": True}


# =============================================================================
# ANNOTATIONS
# =============================================================================

@router.post("/{book_id}/annotation", response_class=JSONResponse)
async def create_annotation(
    request: Request,
    book_id: str,
    highlight_id: str = Form(...),
    text: str = Form(...),
    user=Depends(get_current_user_optional)
):
    """Create or update annotation for a highlight."""
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
    """Delete an annotation."""
    user_service = UserService()
    deleted = user_service.delete_annotation(annotation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"success": True}


# =============================================================================
# CHAT (Tied to highlights)
# =============================================================================

@router.get("/{book_id}/highlight/{highlight_id}/chat", response_class=JSONResponse)
async def get_chat_history(
    request: Request,
    book_id: str,
    highlight_id: str,
    user=Depends(get_current_user_optional)
):
    """Get chat history for a highlight thread."""
    chat_service = ChatService()
    messages = chat_service.get_messages(highlight_id)
    return {"success": True, "messages": messages, "highlight_id": highlight_id}


@router.post("/{book_id}/highlight/{highlight_id}/chat", response_class=HTMLResponse)
async def highlight_chat(
    request: Request,
    book_id: str,
    highlight_id: str,
    question: str = Form(...),
    user=Depends(get_current_user_optional)
):
    """Chat about a highlighted passage."""
    from ..services.agent_service import AgentService
    import logging

    user_service = UserService()
    chat_service = ChatService()
    canon = CanonService()

    book = canon.get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    user_id = user["id"] if user else "anon_test_user"

    # Find the highlight across all sections
    chapters = canon.get_chapters(book_id)
    highlight = None
    chapter = None

    for ch in chapters:
        hl_list = user_service.get_highlights(user_id, ch["id"])
        for hl in hl_list:
            if hl["id"] == highlight_id:
                highlight = hl
                chapter = ch
                break
        if highlight:
            break

    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")

    selected_text = highlight.get("selected_text", "")
    if not selected_text:
        raise HTTPException(status_code=400, detail="Highlight has no text")

    if not question or not question.strip():
        raise HTTPException(status_code=400, detail="No question provided")

    logging.info(f"Chat: book={book_id}, highlight={highlight_id}, q={question[:50]}...")

    # Save user message
    chat_service.add_message(highlight_id, "user", question.strip())

    # Build history context
    history = chat_service.get_messages(highlight_id)
    history_context = ""
    if len(history) > 1:
        prev = history[:-1][-5:]
        history_context = "\n".join([
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in prev
        ])

    # Ask Text Companion
    agent_service = AgentService()
    response = agent_service.ask_text_companion(
        book_title=book["title"],
        chapter_title=chapter["title"],
        selected_text=selected_text.strip(),
        question=question.strip(),
        routing_context=history_context if history_context else None
    )

    if response.is_valid and response.explanation:
        chat_service.add_message(highlight_id, "assistant", response.explanation)

    updated_history = chat_service.get_messages(highlight_id)

    return templates.TemplateResponse(
        "partials/chat_response.html",
        {
            "request": request,
            "response": response,
            "book": book,
            "chapter": chapter,
            "highlight_id": highlight_id,
            "chat_history": updated_history,
        }
    )


@router.post("/{book_id}/chat", response_class=HTMLResponse)
async def section_chat(
    request: Request,
    book_id: str,
    chapter_id: str = Form(...),
    start_offset: int = Form(0),
    end_offset: int = Form(0),
    selected_text: str = Form(...),
    question: str = Form(...),
    highlight_id: str = Form(None),
    routing_context: str = Form(None),
    user=Depends(get_current_user_optional)
):
    """Chat about selected text (ephemeral or tied to a highlight)."""
    from ..services.agent_service import AgentService
    import logging

    agent_service = AgentService()
    canon = CanonService()
    chat_service = ChatService()

    book = canon.get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    chapter = canon.get_chapter(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Section not found")

    if not selected_text or not selected_text.strip():
        raise HTTPException(status_code=400, detail="No text selected")

    if not question or not question.strip():
        raise HTTPException(status_code=400, detail="No question provided")

    logging.info(f"Section chat: book={book_id}, section={chapter_id}, q={question[:50]}...")

    if highlight_id:
        chat_service.add_message(highlight_id, "user", question.strip())

    response = agent_service.ask_text_companion(
        book_title=book["title"],
        chapter_title=chapter["title"],
        selected_text=selected_text.strip(),
        question=question.strip(),
        routing_context=routing_context
    )

    if highlight_id and response.is_valid and response.explanation:
        chat_service.add_message(highlight_id, "assistant", response.explanation)

    chat_history = None
    if highlight_id:
        chat_history = chat_service.get_messages(highlight_id)

    return templates.TemplateResponse(
        "partials/chat_response.html",
        {
            "request": request,
            "response": response,
            "book": book,
            "chapter": chapter,
            "highlight_id": highlight_id,
            "chat_history": chat_history,
        }
    )
