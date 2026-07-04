from fastapi import APIRouter, HTTPException
from app.schemas.schemas import ExploreRequest
from app.services.ai_service import get_ai_response

router = APIRouter(prefix="/explore", tags=["explore"])


@router.post("/chat")
async def chat(payload: ExploreRequest):
    """Send conversation history to Groq Llama 3.3 70B and get ADHD coaching response."""
    if not payload.messages:
        raise HTTPException(status_code=400, detail="messages array cannot be empty")

    messages = [{"role": m.role, "content": m.content} for m in payload.messages[-12:]]

    try:
        reply = await get_ai_response(messages, payload.task_summary)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")

    return {"reply": reply}
