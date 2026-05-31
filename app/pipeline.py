"""Orchestrates one interview turn through the guardrail layers. Returns the safe reply."""
from app import fast_checks, interviewer
from app.violation_logger import LOG_FILE, log_violation

INPUT_REDIRECT = "Let's keep the focus on the interview. Please answer the current question."
OUTPUT_REDIRECT = (
    "I can't share hints, solutions, or feedback during the interview. "
    "Please continue with your own approach."
)


def process_turn(history, user_text, records, reply_fn=None, log_file=LOG_FILE):
    """L1 input check -> interview LLM -> L1 output check. Appends violations to `records`.
    Returns the assistant reply to display. Caller owns `history`."""
    reply_fn = reply_fn or interviewer.reply

    m = fast_checks.detect_input_jailbreak(user_text)
    if m:
        log_violation(records, "fast", m.rule, "block", m.category, user_text, log_file)
        return INPUT_REDIRECT

    answer = reply_fn(history + [{"role": "user", "content": user_text}])

    m = fast_checks.detect_output_violation(answer)
    if m:
        log_violation(records, "fast", m.rule, "replace", m.category, answer, log_file)
        return OUTPUT_REDIRECT

    return answer
