"""Streamlit AI interviewer chat UI (Task 1: bare chatbot, no guardrails yet)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from dotenv import load_dotenv

from app import interviewer

load_dotenv()

st.set_page_config(page_title="AI Interviewer — Guardrails Demo", layout="wide")
st.title("AI Interviewer — Guardrails Demo")

if "history" not in st.session_state:
    st.session_state.history = []

for msg in st.session_state.history:
    st.chat_message(msg["role"]).write(msg["content"])

if prompt := st.chat_input("Type your answer..."):
    st.session_state.history.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)
    answer = interviewer.reply(st.session_state.history)
    st.session_state.history.append({"role": "assistant", "content": answer})
    st.chat_message("assistant").write(answer)
