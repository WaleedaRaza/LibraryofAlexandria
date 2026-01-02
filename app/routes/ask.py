"""
Alexandria Library - Ask Route
Accepts user question, calls agent pipeline, returns routing results.
NO LOGIC HERE - delegates to agent_service.
"""

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import templates
from ..services.agent_service import AgentService
from ..middleware.rate_limit import rate_limit
from .auth import get_current_user_optional

router = APIRouter()


@router.post("/", response_class=HTMLResponse)
@rate_limit(requests=10, window=60, endpoint_type="ask")
async def ask(
    request: Request,
    question: str = Form(...),
    user=Depends(get_current_user_optional)
):
    """
    Process a user's question and route them to relevant text.
    
    Flow:
    1. Intent Classifier → domain/subdomain
    2. Reading Router → book + chapter recommendations
    3. Return routing results page
    """
    agent_service = AgentService()
    
    # Get routing results from agent pipeline
    results = agent_service.route_question(question)
    
    return templates.TemplateResponse(
        "routing_results.html",
        {
            "request": request,
            "user": user,
            "question": question,
            "results": results,
        }
    )

