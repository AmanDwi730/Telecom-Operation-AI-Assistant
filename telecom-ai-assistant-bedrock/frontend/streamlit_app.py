from __future__ import annotations

import os
import uuid
from typing import List

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

SEVERITY_COLORS = {
    "Critical": "#e74c3c",
    "High": "#e67e22",
    "Medium": "#f1c40f",
    "Low": "#2ecc71",
}


def _ensure_state():
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if "user_id" not in st.session_state:
        st.session_state.user_id = "telecom_user"
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "last_sources" not in st.session_state:
        st.session_state.last_sources = []
    if "last_memory" not in st.session_state:
        st.session_state.last_memory = {}


@st.cache_data(ttl=300)
def _fetch_severity_summary():
    try:
        resp = requests.get(f"{API_URL}/severity-summary", timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def _search_incidents(query: str):
    try:
        resp = requests.get(f"{API_URL}/incidents/search", params={"q": query}, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        return {"error": str(exc)}


st.set_page_config(page_title="Telecom Operations Assistant", page_icon="📡", layout="wide")
_ensure_state()

st.title("📡 Telecom Operations Assistant")
st.caption("Bedrock-powered support for 5G Core, LTE/RAN, IMS/VoLTE, Transport, Fiber, and OSS/BSS operations.")

# ---------------------------------------------------------------------------
# Severity Dashboard
# ---------------------------------------------------------------------------
severity_data = _fetch_severity_summary()
if severity_data and "error" not in severity_data:
    st.markdown(
        f"#### Incident Severity Overview &nbsp;&mdash;&nbsp; "
        f"**{severity_data.get('total', 0)}** total incidents"
    )
    cols = st.columns(4)
    for col, level in zip(cols, ["Critical", "High", "Medium", "Low"]):
        count = severity_data.get(level, 0)
        color = SEVERITY_COLORS[level]
        col.markdown(
            f"""
            <div style="
                background:{color}22;
                border-left:5px solid {color};
                border-radius:8px;
                padding:16px 20px;
                text-align:center;
            ">
                <div style="font-size:2rem;font-weight:700;color:{color};">{count}</div>
                <div style="font-size:0.95rem;font-weight:600;color:{color};">{level}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("---")

# ---------------------------------------------------------------------------
# Sidebar: session controls, incident search, memory notes
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Session & Memory")
    st.text_input("User ID", key="user_id")
    st.code(st.session_state.session_id)
    if st.button("Start New Session"):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.last_sources = []
        st.session_state.last_memory = {}
        st.rerun()
    if st.button("Clear Backend Session Memory"):
        try:
            requests.post(f"{API_URL}/memory/{st.session_state.session_id}/clear", timeout=20)
            st.toast("Session memory cleared.")
        except Exception as exc:
            st.error(f"Could not clear session memory: {exc}")

    st.markdown("---")

    # Smart Incident ID Search
    st.markdown("### Incident ID Search")
    search_query = st.text_input(
        "Search by full or last digits",
        placeholder="e.g. 0193 or 3GPP_INC_1_100193",
        key="incident_search_input",
    )
    if search_query:
        result = _search_incidents(search_query)
        if "error" in result:
            st.error(f"Search failed: {result['error']}")
        elif result.get("match_count", 0) == 0:
            st.warning("No incidents found matching your query.")
        elif result["match_count"] == 1:
            inc = result["incidents"][0]
            sev = inc.get("Severity", "")
            sev_color = SEVERITY_COLORS.get(sev, "#888")
            st.success(f"Found 1 match: **{inc['Incident_ID']}**")
            with st.expander(f"{inc['Incident_ID']} - {inc['Technology_Domain']}", expanded=True):
                if sev:
                    st.markdown(
                        f'**Severity:** <span style="color:{sev_color};font-weight:700">{sev}</span>',
                        unsafe_allow_html=True,
                    )
                for field in [
                    "Issue_Type", "Region", "KPI_Impact",
                    "Root_Cause", "Resolution", "Recommended_Action",
                ]:
                    val = inc.get(field, "")
                    if val:
                        st.markdown(f"**{field.replace('_', ' ')}:** {val}")
        else:
            st.info(f"Found {result['match_count']} matches. Select one:")
            for inc in result["incidents"]:
                sev = inc.get("Severity", "")
                label = f"{inc['Incident_ID']}  [{sev}]"
                with st.expander(label):
                    for field in [
                        "Technology_Domain", "Issue_Type", "Region", "Severity",
                        "KPI_Impact", "Root_Cause", "Resolution", "Recommended_Action",
                    ]:
                        val = inc.get(field, "")
                        if val:
                            st.markdown(f"**{field.replace('_', ' ')}:** {val}")

    st.markdown("---")
    st.markdown("### Memory Notes")
    if st.session_state.last_memory:
        st.write(st.session_state.last_memory.get("summary", ""))
        prefs = st.session_state.last_memory.get("preferences", [])
        if prefs:
            st.write("Preferences: " + ", ".join(prefs))
        domains = st.session_state.last_memory.get("domains", [])
        if domains:
            st.write("Domains: " + ", ".join(domains))

# ---------------------------------------------------------------------------
# Chat history + input
# ---------------------------------------------------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_query = st.chat_input("Ask about alarms, incidents, RCA, recovery, or telecom KPIs...")
if user_query:
    st.session_state.messages.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.markdown(user_query)

    payload = {
        "query": user_query,
        "user_id": st.session_state.user_id,
        "session_id": st.session_state.session_id,
        "history": st.session_state.messages[-16:],
    }

    with st.chat_message("assistant"):
        with st.spinner("Analyzing telecom context and generating response..."):
            try:
                response = requests.post(f"{API_URL}/chat", json=payload, timeout=180)
                response.raise_for_status()
                result = response.json()
                answer = result["answer"]
                sources = result.get("sources", [])
                memory = result.get("long_term_memory", {})
            except Exception as exc:
                answer = f"Error calling backend: {exc}"
                sources = []
                memory = {}

        st.markdown(answer)
        if sources:
            st.markdown("### Sources")
            for src in sources:
                with st.expander(f"{src.get('title', src.get('source', 'Source'))}"):
                    st.code(src.get("text", ""), language="text")
        if memory:
            st.markdown("### Long-Term Memory Snapshot")
            st.json(memory)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.session_state.last_sources = sources
    st.session_state.last_memory = memory
