"""Groq-backed AI technical interviewer. Behavior/flow only; safety is enforced by guardrails."""
import os

from groq import Groq

SYSTEM_PROMPT = (
    "You are a professional technical interviewer for a software engineering role. "
    "Conduct the interview one question at a time in a warm, professional tone. "
    "Ask exactly one question per turn and wait for the candidate's answer before continuing. "
    "Build naturally on the candidate's previous answers. "
    "If you have no prior context, open by briefly introducing yourself and asking your first question."
)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    return _client


def reply(history):
    """history: list of {"role": "user"|"assistant", "content": str}. Returns assistant text."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + list(history)
    resp = _get_client().chat.completions.create(
        model=os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant"),
        messages=messages,
        temperature=0.5,
        max_tokens=300,
    )
    return resp.choices[0].message.content
