import os
import httpx
from dotenv import load_dotenv
from typing import List

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Google exposes an OpenAI-compatible endpoint — same request format, no SDK needed
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT = """You are FocusFlow's ADHD coach — warm, direct, and evidence-based.
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
    """Call Gemini 2.5 Flash via Google's OpenAI-compatible endpoint."""
    if not GEMINI_API_KEY:
        return "Gemini API key not configured. Add GEMINI_API_KEY to your .env file."

    system = SYSTEM_PROMPT
    if task_summary:
        system += f"\n\nUser's current task context: {task_summary}"

    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}] + messages,
        "max_tokens": 600,
        "temperature": 0.7,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            GEMINI_URL,
            headers={
                "Authorization": f"Bearer {GEMINI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if response.status_code != 200:
        raise Exception(f"Gemini API error {response.status_code}: {response.text}")

    data = response.json()
    return data["choices"][0]["message"]["content"]
