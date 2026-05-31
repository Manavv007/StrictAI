"""Structured guardrail violation records: kept in a list (UI) + optional JSONL append."""
import hashlib
import json
from datetime import datetime

LOG_FILE = "violations.jsonl"


def make_record(layer, rail_name, action, category, text):
    text = text or ""
    return {
        "ts": datetime.now().strftime("%H:%M:%S"),
        "layer": layer,          # fast | nemo_input | nemo_output
        "rail_name": rail_name,
        "action": action,        # block | replace | redirect | mask
        "category": category,
        "preview": text[:120],
        "hash": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
    }


def log_violation(records, layer, rail_name, action, category, text, log_file=LOG_FILE):
    """Prepend a violation record (newest-first) and optionally append it to a JSONL file."""
    rec = make_record(layer, rail_name, action, category, text)
    records.insert(0, rec)
    if log_file:
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        except OSError:
            pass
    return rec
