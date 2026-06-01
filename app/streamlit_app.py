"""Streamlit AI interviewer with a live guardrail violation side panel."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

from app import guardrails_client, pipeline

st.set_page_config(page_title="AI Interviewer — Guardrails Demo", layout="wide")
st.title("AI Interviewer — Guardrails Demo")

with st.spinner("Warming up guardrails (first load only)..."):
    guardrails_client.get_rails()

if "history" not in st.session_state:
    from app.interviewer import FIRST_QUESTION
    st.session_state.history = [{"role": "assistant", "content": FIRST_QUESTION}]
if "violations" not in st.session_state:
    st.session_state.violations = []
if "metrics" not in st.session_state:
    st.session_state.metrics = []

_COLORS = {"block": "#d33", "replace": "#d33", "redirect": "#e69500", "mask": "#2a7"}

prompt = st.chat_input("Type your answer...")
if prompt:
    llm_latency = [0.0]
    
    def timed_reply(history):
        t_start = time.perf_counter()
        from app import interviewer
        res = interviewer.reply(history)
        llm_latency[0] = (time.perf_counter() - t_start) * 1000
        return res

    t_pipeline_start = time.perf_counter()
    reply = pipeline.process_turn(
        st.session_state.history, prompt, st.session_state.violations,
        reply_fn=timed_reply
    )
    pipeline_ms = (time.perf_counter() - t_pipeline_start) * 1000

    st.session_state.history.append({"role": "user", "content": prompt})
    st.session_state.history.append({"role": "assistant", "content": reply})

    # Extract quality metrics
    words = len(reply.split())
    questions = reply.count("?")
    st.session_state.metrics.append({
        "pipeline_ms": pipeline_ms,
        "llm_ms": llm_latency[0],
        "words": words,
        "questions": questions,
        "blocked": reply in (pipeline.INPUT_REDIRECT, pipeline.OUTPUT_REDIRECT)
    })

col_chat, col_log = st.columns([2, 1])

with col_chat:
    assistant_count = 0
    for msg in st.session_state.history:
        st.chat_message(msg["role"]).write(msg["content"])
        if msg["role"] == "assistant":
            if assistant_count < len(st.session_state.metrics):
                m = st.session_state.metrics[assistant_count]
                guard_ms = max(0.0, m["pipeline_ms"] - m["llm_ms"])
                st.caption(
                    f"⏱️ Turn: **{m['pipeline_ms']:.0f} ms** (LLM: {m['llm_ms']:.0f} ms, Guardrails: {guard_ms:.0f} ms) | "
                    f"📝 **{m['words']} words** | "
                    f"❓ **{m['questions']} question{'s' if m['questions'] != 1 else ''}**"
                )
            assistant_count += 1

with col_log:
    st.subheader("📊 Session Metrics")
    if not st.session_state.metrics:
        st.caption("No turns yet. Start chatting to see metrics.")
    else:
        metrics = st.session_state.metrics
        non_blocked_metrics = [m for m in metrics if not m["blocked"]]
        
        avg_pipeline = sum(m["pipeline_ms"] for m in metrics) / len(metrics)
        avg_llm = sum(m["llm_ms"] for m in non_blocked_metrics) / len(non_blocked_metrics) if non_blocked_metrics else 0.0
        avg_guard = sum(max(0.0, m["pipeline_ms"] - m["llm_ms"]) for m in metrics) / len(metrics)
        avg_words = sum(m["words"] for m in non_blocked_metrics) / len(non_blocked_metrics) if non_blocked_metrics else 0.0
        
        total_blocked = sum(1 for m in metrics if m["blocked"])
        total_violations = len(st.session_state.violations)
        
        c1, c2 = st.columns(2)
        c1.metric("Avg Pipeline", f"{avg_pipeline:.0f} ms")
        c2.metric("Avg LLM", f"{avg_llm:.0f} ms")
        
        c3, c4 = st.columns(2)
        c3.metric("Avg Guardrail Time", f"{avg_guard:.0f} ms")
        c4.metric("Avg Reply Length", f"{avg_words:.1f} words")
        
        c5, c6 = st.columns(2)
        c5.metric("Blocked Turns", f"{total_blocked}")
        c6.metric("Guardrail Trips", f"{total_violations}")

    st.markdown("---")
    st.subheader("🛡️ Guardrail activity")
    if not st.session_state.violations:
        st.caption("No violations yet. Try asking for a hint or the answer.")
    for r in st.session_state.violations:
        color = _COLORS.get(r["action"], "#888")
        st.markdown(
            f"<div style='border-left:4px solid {color};padding:4px 8px;margin-bottom:6px;'>"
            f"🚫 <b>{r['layer']}</b> · {r['rail_name']} · <i>{r['action']}</i><br>"
            f"<small>{r['ts']} · {r['category']}</small><br>"
            f"<small>{r['preview']}</small></div>",
            unsafe_allow_html=True,
        )
