# =============================================================================
# ai_service.py — Calls the Gemini AI API to generate coaching responses.
#
# We use Google's Gemini 2.5 Flash model via their OpenAI-compatible endpoint.
# "OpenAI-compatible" means: the request/response format is identical to
# OpenAI's Chat Completions API. This is useful because:
#   - No SDK needed — a plain HTTP POST with JSON works
#   - If we ever switch models (OpenAI, Mistral, etc.), only the URL and
#     API key change; the rest of the code stays the same
#
# The flow: frontend sends messages → explore.py receives → this file
# formats and sends to Gemini → gets reply text → returns to explore.py
# → sends back to frontend.
# =============================================================================

import os
import httpx
from dotenv import load_dotenv
from typing import List

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Google's OpenAI-compatible chat endpoint — same JSON format as OpenAI,
# but hits Google's servers and uses a Gemini model.
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
MODEL = "gemini-2.5-flash"

# The system prompt is the AI's "personality briefing" — it's prepended to
# every conversation and sets the tone, constraints, and role the AI plays.
# This runs server-side so the user cannot see or modify it.
SYSTEM_PROMPT = """You are Un Poco Loco's ADHD coach — warm, direct, and evidence-based.
You help users with ADHD manage tasks, build focus habits, and live better lives.

Your responses should be:
- Concise but warm (2-4 short paragraphs max)
- Practical with specific, immediately actionable tips
- ADHD-aware: acknowledge executive dysfunction, time blindness, dopamine-seeking, rejection sensitivity
- Use plain text only — no markdown, no headers, no bullet asterisks
- When recommending tools/apps, name 2-3 specific ones with a one-line description each
- End every response with one tiny, doable action they can take in the next 5 minutes

Remember: shame and pressure don't work for ADHD brains. Kindness and small wins do."""


async def get_ai_response(messages: List[dict], task_summary: str = "") -> str:
    """
    Send the conversation to Gemini and return the reply text.

    Parameters:
        messages     — list of {"role": "user"/"assistant", "content": "..."} dicts
        task_summary — plain text description of user's tasks, injected into the
                       system prompt so the AI has context without needing to ask

    Why httpx instead of the requests library?
    httpx supports async (await), which lets the server handle other incoming
    requests while waiting for Gemini's HTTP response. The requests library
    is synchronous — it would freeze the entire server during the API call.
    """
    if not GEMINI_API_KEY:
        # Return a helpful message instead of crashing — the user will see this
        # in the Coach tab and know what to fix.
        return "Gemini API key not configured. Add GEMINI_API_KEY to your .env file."

    # Optionally append the user's task context to the system prompt
    system = SYSTEM_PROMPT
    if task_summary:
        system += f"\n\nUser's current task context: {task_summary}"

    # The payload format follows the OpenAI Chat Completions spec:
    # system message first, then the conversation history.
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}] + messages,
        "max_tokens": 600,    # cap response length — prevents runaway long replies
        "temperature": 0.7,   # 0 = deterministic, 1 = creative; 0.7 is a warm balance
    }

    # async with httpx.AsyncClient() opens a connection and closes it cleanly
    # when the block exits, even if an exception occurs.
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            GEMINI_URL,
            headers={
                "Authorization": f"Bearer {GEMINI_API_KEY}",  # API key auth
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if response.status_code != 200:
        # Raise an exception with the full error details so explore.py can
        # convert it into a 502 response with a readable message.
        raise Exception(f"Gemini API error {response.status_code}: {response.text}")

    # The response JSON looks like:
    # {"choices": [{"message": {"role": "assistant", "content": "..."}}]}
    # We extract just the text content.
    data = response.json()
    return data["choices"][0]["message"]["content"]
