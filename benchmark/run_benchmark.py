"""Benchmark runner: feeds 10 fixed candidate prompts through the full pipeline for the
current GROQ_MODEL and prints detailed per-turn + aggregate evaluation metrics."""
import json
import os
import sys
import time
import statistics

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app import fast_checks, interviewer, pipeline
from app.interviewer import FIRST_QUESTION

SCENARIOS_PATH = os.path.join(os.path.dirname(__file__), "scenarios.json")


def _count_questions(text):
    stripped = fast_checks._strip_courtesy_questions(text)
    return fast_checks.count_question_marks(stripped)


def _measure_reply(history):
    """Call interviewer.reply with timing and token capture."""
    start = time.perf_counter()
    resp = interviewer.reply(history)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return resp, elapsed_ms


def run():
    model = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
    print("=" * 70)
    print(f"  BENCHMARK — Response Model: {model}")
    print(f"  Guard Model (fixed): {os.environ.get('GUARD_MODEL', 'llama-3.3-70b-versatile (default)')}")
    print("=" * 70)

    with open(SCENARIOS_PATH, encoding="utf-8") as f:
        scenarios = json.load(f)

    # Metrics accumulators
    latencies = []
    reply_lengths = []
    token_counts = []
    guardrail_trips = []
    question_counts = []
    results = []

    # Start with the fixed first question as the opening assistant turn
    history = [{"role": "assistant", "content": FIRST_QUESTION}]

    print(f"\n  Fixed opening question:")
    print(f"  BOT: {FIRST_QUESTION}\n")
    print("-" * 70)

    for sc in scenarios:
        sid = sc["id"]
        user_text = sc["prompt"]
        category = sc["category"]

        print(f"\n  Turn {sid} [{category}]")
        print(f"  USER: {user_text}")

        # --- Full pipeline turn (includes guardrails) ---
        violations = []
        pipeline_start = time.perf_counter()
        pipeline_reply = pipeline.process_turn(
            history, user_text, violations,
            log_file=None  # don't pollute the main violations.jsonl
        )
        pipeline_ms = (time.perf_counter() - pipeline_start) * 1000

        # --- Isolated LLM latency (no guardrails, just the model) ---
        was_blocked = pipeline_reply in (pipeline.INPUT_REDIRECT, pipeline.OUTPUT_REDIRECT) or \
                      any(v["action"] in ("block", "redirect") for v in violations)

        if was_blocked:
            llm_ms = 0.0
            raw_reply = None
        else:
            # The pipeline already called the LLM; measure a second call for isolated timing
            llm_history = history + [{"role": "user", "content": user_text}]
            raw_reply, llm_ms = _measure_reply(llm_history)

        # --- Metrics extraction ---
        reply_text = pipeline_reply
        reply_len = len(reply_text)
        word_count = len(reply_text.split())
        char_count = len(reply_text)
        q_count = _count_questions(reply_text) if not was_blocked else 0

        # Token estimate (rough: 1 token ≈ 4 chars for English)
        est_tokens = max(1, char_count // 4)

        # Guardrail analysis
        input_blocked = any(v["action"] in ("block", "redirect") and "input" in v["layer"] for v in violations)
        output_blocked = any(v["action"] in ("replace", "redirect") and "output" in v["layer"] for v in violations)
        pii_masked = any(v["action"] == "mask" for v in violations)
        trip_categories = [v["category"] for v in violations]

        # Store
        latencies.append(pipeline_ms)
        reply_lengths.append(word_count)
        token_counts.append(est_tokens)
        guardrail_trips.append(len(violations))
        question_counts.append(q_count)

        result = {
            "turn": sid,
            "category": category,
            "pipeline_latency_ms": round(pipeline_ms, 1),
            "llm_latency_ms": round(llm_ms, 1),
            "reply_length_words": word_count,
            "reply_length_chars": char_count,
            "est_tokens": est_tokens,
            "question_marks": q_count,
            "input_blocked": input_blocked,
            "output_blocked": output_blocked,
            "pii_masked": pii_masked,
            "guardrail_trips": len(violations),
            "trip_categories": trip_categories,
            "was_blocked": was_blocked,
        }
        results.append(result)

        # Print per-turn metrics
        print(f"  BOT: {reply_text[:120]}{'...' if len(reply_text) > 120 else ''}")
        print(f"  |- Pipeline latency:  {pipeline_ms:>8.1f} ms")
        print(f"  |- LLM-only latency:  {llm_ms:>8.1f} ms")
        print(f"  |- Reply length:      {word_count} words / {char_count} chars / ~{est_tokens} tokens")
        print(f"  |- Question marks:    {q_count}")
        print(f"  |- Input blocked:     {input_blocked}")
        print(f"  |- Output blocked:    {output_blocked}")
        print(f"  |- PII masked:        {pii_masked}")
        if violations:
            for v in violations:
                print(f"  |   [!] {v['layer']} . {v['rail_name']} . {v['action']} . {v['category']}")
        print(f"  +- Guardrail trips:   {len(violations)}")

        # Update history for next turn (use pipeline reply so conversation stays coherent)
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": pipeline_reply})

    # --- Aggregate metrics ---
    clean_latencies = [r["pipeline_latency_ms"] for r in results if not r["was_blocked"]]
    clean_llm = [r["llm_latency_ms"] for r in results if not r["was_blocked"] and r["llm_latency_ms"] > 0]

    print("\n" + "=" * 70)
    print("  AGGREGATE METRICS")
    print("=" * 70)
    print(f"\n  Model: {model}")
    print(f"  Total turns: {len(results)}")
    print(f"  Turns blocked (input): {sum(1 for r in results if r['input_blocked'])}")
    print(f"  Turns blocked (output): {sum(1 for r in results if r['output_blocked'])}")
    print(f"  PII masked: {sum(1 for r in results if r['pii_masked'])}")
    print(f"  Total guardrail trips: {sum(r['guardrail_trips'] for r in results)}")

    if clean_latencies:
        print(f"\n  --- Pipeline Latency (non-blocked turns) ---")
        print(f"  Mean:   {statistics.mean(clean_latencies):>8.1f} ms")
        print(f"  Median: {statistics.median(clean_latencies):>8.1f} ms")
        print(f"  Stdev:  {statistics.stdev(clean_latencies):>8.1f} ms" if len(clean_latencies) > 1 else "")
        print(f"  Min:    {min(clean_latencies):>8.1f} ms")
        print(f"  Max:    {max(clean_latencies):>8.1f} ms")
        sorted_lat = sorted(clean_latencies)
        p95_idx = min(int(len(sorted_lat) * 0.95), len(sorted_lat) - 1)
        print(f"  p95:    {sorted_lat[p95_idx]:>8.1f} ms")

    if clean_llm:
        print(f"\n  --- LLM-Only Latency (non-blocked turns) ---")
        print(f"  Mean:   {statistics.mean(clean_llm):>8.1f} ms")
        print(f"  Median: {statistics.median(clean_llm):>8.1f} ms")
        print(f"  Min:    {min(clean_llm):>8.1f} ms")
        print(f"  Max:    {max(clean_llm):>8.1f} ms")

    non_blocked_results = [r for r in results if not r["was_blocked"]]
    if non_blocked_results:
        print(f"\n  --- Reply Quality (non-blocked turns) ---")
        avg_words = statistics.mean([r["reply_length_words"] for r in non_blocked_results])
        avg_tokens = statistics.mean([r["est_tokens"] for r in non_blocked_results])
        avg_q = statistics.mean([r["question_marks"] for r in non_blocked_results])
        multi_q = sum(1 for r in non_blocked_results if r["question_marks"] > 1)
        single_q = sum(1 for r in non_blocked_results if r["question_marks"] == 1)
        no_q = sum(1 for r in non_blocked_results if r["question_marks"] == 0)
        print(f"  Avg reply length:     {avg_words:.1f} words / ~{avg_tokens:.0f} tokens")
        print(f"  Avg question marks:   {avg_q:.2f}")
        print(f"  Turns with 1 question: {single_q}/{len(non_blocked_results)}")
        print(f"  Turns with 0 questions: {no_q}/{len(non_blocked_results)}")
        print(f"  Turns with 2+ questions (violation): {multi_q}/{len(non_blocked_results)}")

    # Guardrail trip breakdown
    all_trips = [cat for r in results for cat in r["trip_categories"]]
    if all_trips:
        print(f"\n  --- Guardrail Trip Breakdown ---")
        from collections import Counter
        for cat, count in Counter(all_trips).most_common():
            print(f"  {cat:20s}: {count}")

    # Per-turn summary table
    print(f"\n  --- Per-Turn Summary Table ---")
    print(f"  {'Turn':<5} {'Category':<25} {'Pipe ms':<10} {'LLM ms':<10} {'Words':<7} {'Q?':<4} {'Blocked':<8} {'Trips':<6}")
    print(f"  {'-'*5} {'-'*25} {'-'*10} {'-'*10} {'-'*7} {'-'*4} {'-'*8} {'-'*6}")
    for r in results:
        print(f"  {r['turn']:<5} {r['category']:<25} {r['pipeline_latency_ms']:<10.1f} "
              f"{r['llm_latency_ms']:<10.1f} {r['reply_length_words']:<7} {r['question_marks']:<4} "
              f"{'YES' if r['was_blocked'] else 'no':<8} {r['guardrail_trips']:<6}")

    print("\n" + "=" * 70)
    print("  Run complete. Change GROQ_MODEL in .env and re-run to compare models.")
    print("=" * 70)

    return results


if __name__ == "__main__":
    run()
