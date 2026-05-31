"""NeMo @action detectors. Reuse L1 fast_checks; input adds a broader paraphrase set
so the NeMo layer catches softer attempts that the strict L1 regex lets through."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from nemoguardrails.actions import action

from app import fast_checks

# Softer/paraphrased answer-seeking that L1's strict regex does not match.
_EXTRA_INPUT = [
    r"walk me through (the |your )?(solution|answer|approach)",
    r"show me how (you|i|to) ?(would |could )?(solve|do|approach)",
    r"can you (help me|just) (solve|answer|figure)",
    r"what would you do here",
    r"give me a hint",
]


@action(name="detect_interview_jailbreak", is_system_action=True)
async def detect_interview_jailbreak(context=None):
    text = (context or {}).get("user_message", "") or ""
    if fast_checks.detect_input_jailbreak(text):
        return True
    return any(re.search(p, text, re.IGNORECASE) for p in _EXTRA_INPUT)


@action(name="detect_interview_output_violation", is_system_action=True)
async def detect_interview_output_violation(context=None):
    text = (context or {}).get("bot_message", "") or ""
    return fast_checks.detect_output_violation(text) is not None
