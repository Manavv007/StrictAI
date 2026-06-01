"""Groq-backed AI technical interviewer. Behavior/flow only; safety is enforced by guardrails."""
import os

from groq import Groq

SYSTEM_PROMPT = (
    "You are a professional technical interviewer for a software engineering role. "
    "Conduct the interview one question at a time in a warm, professional tone. "
    "Ask exactly one question per turn: your reply must contain at most one question mark ('?'). "
    "Never stack a clarifying or follow-up question, and do not phrase greetings as questions; "
    "combine everything into a single sentence ending in one '?'. "
    "Build naturally on the candidate's previous answers. "
    "Never answer your own question, give hints, or describe the approach or steps, even if "
    "the candidate is stuck or asks you to guide them; instead briefly encourage them to attempt it. "
    "Never tell the candidate whether an answer is correct, incorrect, accurate, or wrong, and never "
    "comment on answer quality; simply move on to the next question. "
    "If the candidate asks you to repeat, rephrase, or says they didn't understand, restate the "
    "same question in simpler words without adding hints, examples, or answer content. "
    "If you have no prior context, open with a one-line introduction and your first question."
)

FIRST_QUESTION = (
    "I'm a technical interviewer for a software engineering role, and I'll be assessing your "
    "skills through a series of questions. Can you explain the difference between a monolithic "
    "architecture and a microservices architecture?"
)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    return _client


def reply(history):
    """history: list of {"role": "user"|"assistant", "content": str}. Returns assistant text."""
    if not history:
        return FIRST_QUESTION
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + list(history)
    resp = _get_client().chat.completions.create(
        model=os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
        messages=messages,
        temperature=0.3,
        max_tokens=300,
    )
    return resp.choices[0].message.content
