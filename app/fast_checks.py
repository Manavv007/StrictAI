"""L1 fast deterministic guardrail checks (sub-ms regex/keyword). No LLM calls."""
import re
from collections import namedtuple

Match = namedtuple("Match", ["rule", "category"])

# Input: candidate trying to jailbreak / manipulate the interviewer.
_INPUT_PATTERNS = {
    "ignore_instructions": [
        r"(ignore|forget|disregard|override|bypass|drop)\b[\w\s,'-]{0,40}\b"
        r"(instructions?|system prompt|prompts?|guidelines?)",
        r"disregard .*instruction"],
    "override_prompt": [
        r"(this is |here is )?your new (system )?(prompt|instructions?)",
        r"(rewrite|replace|change|update|set|modify)\s+(your\s+)?(system\s+)?prompt",
        r"from now on,?\s+you\s+(?:have to|must|will|should|need to)\b",
        r"new (system )?(prompt|instructions?)"],
    "reveal_prompt": [r"reveal your (system )?prompt", r"what (is|are) your (system )?(prompt|instructions)"],
    "end_interview": [r"(end|stop|finish) (the |this )?interview"],
    "force_hire": [r"you'?re hired", r"you are hired", r"mark me as (hired|selected|passed)"],
    "demand_answer": [
        r"(give|tell|show|share|provide)\s+me\s+(the\s+)?(correct\s+)?answer",
        r"(can|could|would|will|please)\s*(you\s+)?(just\s+)?(give|tell|show|share|provide)\s+"
        r"(me\s+)?(the\s+|an?\s+|your\s+)?(correct\s+)?answer",
        r"what'?s the (correct )?answer", r"just answer",
        r"^\s*(please\s+)?(just\s+)?answer (that|it|this|the question)\b"],
    "pretend": [r"pretend (you are|to be)", r"\bact as\b"],
}

# Output: interviewer leaking hints/solutions, praising, leaking evaluation.
_OUTPUT_PATTERNS = {
    "code_solution": ("hints", [r"```", r"\bdef \w+\(", r"\bclass \w+\s*[:\(]"]),
    "walkthrough": ("hints", [r"here'?s how", r"the (correct )?answer is", r"the solution is",
                              r"step \d", r"for example,? you (could|can|should)"]),
    "praise": ("praise", [
        r"\b(great|excellent|perfect|impressive|fantastic|nice|good)\s+"
        r"(answer|work|job|response|explanation|solution|approach|point|reasoning)\b",
        r"well done", r"good job",
        r"that(?:'?s| is| was)\s+(?:not (?:quite |really )?|in)?(?:correct|right|accurate|true)",
        r"you'?re (?:correct|right|wrong|incorrect|mistaken)", r"\bnot quite\b"]),
    "eval_leak": ("eval_leak", [r"\byour score\b", r"\b\d+\s*/\s*10\b", r"you (passed|failed)",
                                r"your (evaluation|rating)"]),
}


def _search(text, patterns):
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


# Rhetorical/courtesy questions that should not count as an interview question.
_COURTESY_Q = [
    r"how are you(?: doing| today)?\?",
    r"(?:are you |you )?ready(?: to (?:begin|start|go))?\?",
    r"shall we (?:begin|start|get started|continue)\?",
    r"(?:does|do) that (?:make sense|sound good|work)\?",
    r"sound good\?", r"is that (?:ok|okay|alright|all right)\?",
    r"\b(?:ok|okay|right|alright)\?",
]


def _strip_courtesy_questions(text):
    for p in _COURTESY_Q:
        text = re.sub(p, "", text, flags=re.IGNORECASE)
    return text


# Declarative second-person guidance leaks the approach. Only flagged in non-question
# sentences, so inverted questions ("what would you use?") are never matched.
_LEAK_GUIDANCE = [
    r"\byou (?:would|could|can|might|should|'d)\s+"
    r"(?:use|start|begin|look|check|inspect|open|try|run|add|create|write|implement|"
    r"set|configure|select|click|navigate|debug|test|apply|modify|consider|ensure)\b",
    r"\b(?:start|begin) by\b",
    r"\b(?:first|then|next|after that|finally),?\s+you\s+\w+",
    r"\bwhat you (?:do|would do|could do) is\b",
    r"\bthe (?:first|next) (?:step|thing) (?:is|would be)\b",
]


def _non_question_sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if not s.rstrip().endswith("?")]


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
    if any(_search(s, _LEAK_GUIDANCE) for s in _non_question_sentences(text)):
        return Match("walkthrough", "hints")
    if count_question_marks(_strip_courtesy_questions(text)) > 1:
        return Match("multi_question", "multi_question")
    return None
