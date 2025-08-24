import os
import google.generativeai as genai
from django.conf import settings

# Use the API key from Django settings
GEMINI_API_KEY = getattr(settings, "GEMINI_API_KEY", None)

# Configure once per process
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

MODEL_NAME = getattr(settings, "GEMINI_MODEL", "gemini-1.5-flash")  # configurable via settings


def summarize_email(text: str) -> str:
    """
    Produce a brief, helpful summary suitable for a reply assistant.
    """
    if not GEMINI_API_KEY:
        return "[Gemini API key not configured]"

    try:
        prompt = (
            "Summarize the following email in 3-4 concise bullet points, "
            "include the sender's main request and any deadlines:\n\n"
            f"{text}"
        )
        model = genai.GenerativeModel(MODEL_NAME)
        resp = model.generate_content(prompt)

        if hasattr(resp, "text") and resp.text:
            return resp.text.strip()
        elif getattr(resp, "candidates", None):
            # fallback if resp.text is missing
            return resp.candidates[0].content.parts[0].text.strip()

        return "No summary generated."
    except Exception as e:
        return f"[Gemini error: {e}]"


def generate_reply(email_text: str, summary: str | None = None) -> str:
    """
    Generate a polite, professional reply draft.
    """
    if not GEMINI_API_KEY:
        return "[Gemini API key not configured]"

    try:
        prompt = (
            "Write a concise, professional reply to the email below. "
            "Be helpful, keep it under 150 words, and use plain language. "
            "If a summary is provided, consider it.\n\n"
            f"Summary (optional): {summary or 'N/A'}\n\n"
            f"Email:\n{email_text}\n\n"
            "Reply:"
        )
        model = genai.GenerativeModel(MODEL_NAME)
        resp = model.generate_content(prompt)

        if hasattr(resp, "text") and resp.text:
            return resp.text.strip()
        elif getattr(resp, "candidates", None):
            return resp.candidates[0].content.parts[0].text.strip()

        return "No reply generated."
    except Exception as e:
        return f"[Gemini error: {e}]"
