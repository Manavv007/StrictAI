"""L1 fast deterministic guardrail checks (sub-ms regex/keyword). No LLM calls."""
import re
from collections import namedtuple

Match = namedtuple("Match", ["rule", "category"])

# Input: candidate trying to jailbreak / manipulate the interviewer.
_INPUT_PATTERNS = {
    "ignore_instructions": [r"ignore (?:all |previous |prior |your )*instructions", r"disregard .*instruction"],
    "reveal_prompt": [r"reveal your (system )?prompt", r"what (is|are) your (system )?(prompt|instructions)"],
    "end_interview": [r"(end|stop|finish) (the |this )?interview"],
    "force_hire": [r"you'?re hired", r"you are hired", r"mark me as (hired|selected|passed)"],
    "demand_answer": [r"(give|tell) me the (correct )?answer", r"what'?s the (correct )?answer", r"just answer"],
    "pretend": [r"pretend (you are|to be)", r"\bact as\b"],
}

# Output: interviewer leaking hints/solutions, praising, leaking evaluation.
_OUTPUT_PATTERNS = {
    "code_solution": ("hints", [r"```", r"\bdef \w+\(", r"\bclass \w+\s*[:\(]"]),
    "walkthrough": ("hints", [r"here'?s how", r"the (correct )?answer is", r"the solution is",
                              r"step \d", r"for example,? you (could|can|should)"]),
    "praise": ("praise", [r"\b(great|excellent|perfect|impressive)\b", r"well done", r"good job",
                          r"that'?s (correct|right)", r"you'?re (correct|right)"]),
    "eval_leak": ("eval_leak", [r"\byour score\b", r"\b\d+\s*/\s*10\b", r"you (passed|failed)",
                                r"your (evaluation|rating)"]),
}


def _search(text, patterns):
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def detect_input_jailbreak(text):
    """Return Match(rule, 'jailbreak') if the user input is a jailbreak attempt, else None."""
    for rule, patterns in _INPUT_PATTERNS.items():
        if _search(text, patterns):
            return Match(rule, "jailbreak")
    return None


def count_question_marks(text):
    return text.count("?")


def detect_output_violation(text):
    """Return Match(rule, category) if the bot reply violates interview policy, else None."""
    for rule, (category, patterns) in _OUTPUT_PATTERNS.items():
        if _search(text, patterns):
            return Match(rule, category)
    if count_question_marks(text) > 1:
        return Match("multi_question", "multi_question")
    return None
