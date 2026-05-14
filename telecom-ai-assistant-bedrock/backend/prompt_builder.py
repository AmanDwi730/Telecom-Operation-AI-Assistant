from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Dict

from config import MAX_CHAT_HISTORY

SYSTEM_PROMPT = """You are the Telecom Operations Assistant for NOC / SOC / Field Engineering teams.

Behavior:
- Be friendly, professional, and concise.
- Think like a senior telecom operations engineer.
- Use only the retrieved telecom context plus the conversation memory.
- If the answer is not fully supported by the context, say what is known and clearly mark assumptions.
- Prefer practical troubleshooting steps, root cause candidates, and recovery actions.
- Always structure the answer with these sections:
  1. Summary
  2. Likely Root Cause
  3. Troubleshooting Steps
  4. KPI / Service Impact
  5. Recommended Action
  6. Memory Notes
  7. Sources

Telecom domains in scope:
- 5G Core
- LTE / RAN
- IMS / VoLTE
- Transport / IP / MPLS
- Fiber / Optical
- OSS / BSS

Memory rules:
- Short-term memory = recent conversation turns in this session.
- Long-term memory = persistent preferences, recurring topics, and useful operator notes across sessions.
- Use long-term memory only when it is relevant and safe.
- Never invent memory that is not present.

Formatting:
- Use bullet points for troubleshooting.
- Keep technical wording precise.
- End with a short next-best-action if the issue is operationally urgent.
"""


def _format_memory_block(short_term_history: List[dict], long_term_memory: dict) -> str:
    stm = short_term_history[-MAX_CHAT_HISTORY * 2:]
    stm_lines = []
    for item in stm:
        role = item.get("role", "user").capitalize()
        content = item.get("content", "")
        if content:
            stm_lines.append(f"{role}: {content}")

    ltm_lines = []
    if long_term_memory:
        summary = long_term_memory.get("summary")
        preferences = long_term_memory.get("preferences", [])
        domains = long_term_memory.get("domains", [])
        topics = long_term_memory.get("topics", [])
        if summary:
            ltm_lines.append(f"Summary: {summary}")
        if preferences:
            ltm_lines.append("Preferences: " + ", ".join(preferences))
        if domains:
            ltm_lines.append("Domains: " + ", ".join(domains))
        if topics:
            ltm_lines.append("Topics: " + ", ".join(topics))

    return (
        "### Short-Term Memory\n"
        + ("\n".join(stm_lines) if stm_lines else "No previous turns in this session.")
        + "\n\n### Long-Term Memory\n"
        + ("\n".join(ltm_lines) if ltm_lines else "No persistent user memory saved yet.")
    )


def _format_sources(sources: List[dict]) -> str:
    source_lines = []
    for idx, src in enumerate(sources, start=1):
        if src["source_type"] == "dataset":
            meta = src["metadata"]
            source_lines.append(
                f"- [D{idx}] {src['title']} | "
                f"Incident={meta.get('Incident_ID')} | "
                f"Domain={meta.get('Technology_Domain')} | "
                f"Severity={meta.get('Severity')}"
            )
        else:
            source_lines.append(f"- [S{idx}] {src['title']} | Source={src['source']}")
    return "\n".join(source_lines) if source_lines else "- No sources found"


def build_user_prompt(
    query: str,
    short_term_history: List[dict],
    long_term_memory: dict,
    retrieved_context_block: str,
    sources: List[dict],
) -> str:
    now = datetime.now(timezone.utc).isoformat()

    memory_block = _format_memory_block(short_term_history, long_term_memory)
    source_block = _format_sources(sources)

    return f"""Current UTC Time: {now}

{memory_block}

### Retrieved Context
{retrieved_context_block}

### Source Index
{source_block}

### User Query
{query}

### Response Requirements
Return the response in this exact format:

Summary:
Likely Root Cause:
Troubleshooting Steps:
- ...
KPI / Service Impact:
Recommended Action:
Memory Notes:
Sources:
- ...
"""
