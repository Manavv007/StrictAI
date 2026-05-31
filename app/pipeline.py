"""Orchestrates one interview turn: L1 fast checks -> L2 NeMo rails -> LLM -> L1 -> L2.
Returns the safe reply. NeMo checks are injectable so the pipeline stays unit-testable."""
import asyncio

from app import fast_checks, interviewer
from app.violation_logger import LOG_FILE, log_violation

INPUT_REDIRECT = "Let's keep the focus on the interview. Please answer the current question."
OUTPUT_REDIRECT = (
    "I can't share hints, solutions, or feedback during the interview. "
    "Please continue with your own approach."
)


def _default_input_check(text):
    from app import guardrails_client

    return asyncio.run(guardrails_client.check_input(text))


def _default_output_check(user_text, bot_text):
    from app import guardrails_client

    return asyncio.run(guardrails_client.check_output(user_text, bot_text))


def process_turn(history, user_text, records, reply_fn=None, log_file=LOG_FILE,
                 use_nemo=True, input_check=None, output_check=None):
    reply_fn = reply_fn or interviewer.reply
    if use_nemo:
        input_check = input_check or _default_input_check
        output_check = output_check or _default_output_check

    # L1 input (sub-ms regex)
    m = fast_checks.detect_input_jailbreak(user_text)
    if m:
        log_violation(records, "fast", m.rule, "block", m.category, user_text, log_file)
        return INPUT_REDIRECT

    # L2 NeMo input (catches paraphrases L1 misses; also masks PII before the LLM)
    if use_nemo:
        blocked, msg, masked = input_check(user_text)
        if blocked:
            log_violation(records, "nemo_input", "interview jailbreak check", "redirect",
                          "jailbreak", user_text, log_file)
            return msg or INPUT_REDIRECT
        if masked and masked != user_text:
            log_violation(records, "nemo_input", "mask sensitive data on input", "mask",
                          "pii", user_text, log_file)
            user_text = masked

    answer = reply_fn(history + [{"role": "user", "content": user_text}])

    # L1 output
    m = fast_checks.detect_output_violation(answer)
    if m:
        log_violation(records, "fast", m.rule, "replace", m.category, answer, log_file)
        return OUTPUT_REDIRECT

    # L2 NeMo output (fail-closed)
    if use_nemo:
        blocked, msg = output_check(user_text, answer)
        if blocked:
            log_violation(records, "nemo_output", "interview output policy check", "redirect",
                          "policy", answer, log_file)
            return msg or OUTPUT_REDIRECT

    return answer
