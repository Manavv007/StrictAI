"""Streamlit AI interviewer with a live guardrail violation side panel."""
import os
import sys

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
    st.session_state.history = []
if "violations" not in st.session_state:
    st.session_state.violations = []

_COLORS = {"block": "#d33", "replace": "#d33", "redirect": "#e69500", "mask": "#2a7"}

prompt = st.chat_input("Type your answer...")
if prompt:
    reply = pipeline.process_turn(
        st.session_state.history, prompt, st.session_state.violations
    )
    st.session_state.history.append({"role": "user", "content": prompt})
    st.session_state.history.append({"role": "assistant", "content": reply})

col_chat, col_log = st.columns([2, 1])

with col_chat:
    for msg in st.session_state.history:
        st.chat_message(msg["role"]).write(msg["content"])

with col_log:
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
