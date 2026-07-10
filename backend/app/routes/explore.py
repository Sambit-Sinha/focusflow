# =============================================================================
# routes/explore.py — The AI Coach chat endpoint.
#
# One endpoint: POST /explore/chat
# Receives the conversation history from the frontend, calls the Gemini API,
# and returns the AI's reply. The server acts as a proxy here — the frontend
# never talks to Gemini directly, because:
#   1. The API key must stay secret (not in frontend code)
#   2. We can inject the system prompt and task context server-side
# =============================================================================

from fastapi import APIRouter, HTTPException
from app.schemas.schemas import ExploreRequest
from app.services.ai_service import get_ai_response

router = APIRouter(prefix="/explore", tags=["explore"])


@router.post("/chat")
async def chat(payload: ExploreRequest):
    """
    Send conversation history to Gemini and return the AI's reply.

    async def (instead of plain def) is used here because get_ai_response
    makes an HTTP call to the Gemini API. "async" lets the server handle
    other requests while waiting for Gemini's response — it doesn't block
    the entire server during the network round-trip (typically 1–3 seconds).

    We only send the last 12 messages (payload.messages[-12:]) to keep the
    request small. Gemini has a token limit — sending an infinite history
    would eventually fail or become expensive.

    status_code=502 means "Bad Gateway" — our server received an error
    from an upstream service (Gemini). This is the correct HTTP code when
    YOUR server is fine but a third-party it depends on failed.
    """
    if not payload.messages:
        raise HTTPException(status_code=400, detail="messages array cannot be empty")

    # Trim to last 12 messages to stay within token limits
    messages = [{"role": m.role, "content": m.content} for m in payload.messages[-12:]]

    try:
        reply = await get_ai_response(messages, payload.task_summary)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")

    return {"reply": reply}
