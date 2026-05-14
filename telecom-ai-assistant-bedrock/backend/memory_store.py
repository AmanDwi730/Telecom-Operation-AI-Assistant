from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from config import LONG_TERM_MEMORY_PATH, SESSION_MEMORY_PATH, MAX_CHAT_HISTORY

_FILE_LOCK = Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def extract_memory_facts(user_text: str, assistant_text: str | None = None) -> dict:
    """Heuristic long-term memory extraction for an operations assistant."""
    text = _normalize_text(user_text)
    assistant = _normalize_text(assistant_text or "")

    preferences = []
    if re.search(r"\b(concise|brief|short)\b", text, re.I):
        preferences.append("prefers concise responses")
    if re.search(r"\b(detailed|full)\b", text, re.I):
        preferences.append("prefers detailed responses")
    if re.search(r"\b(step[- ]?by[- ]?step|steps)\b", text, re.I):
        preferences.append("likes step-by-step troubleshooting")
    if re.search(r"\b(ui|frontend|dashboard)\b", text, re.I):
        preferences.append("interested in the UI experience")

    domain_hits = []
    for term in ["5G", "4G", "LTE", "IMS", "VoLTE", "RAN", "UPF", "AMF", "SMF", "SIP", "OSS", "BSS", "MPLS", "fiber"]:
        if re.search(rf"\b{re.escape(term)}\b", text, re.I) or re.search(rf"\b{re.escape(term)}\b", assistant, re.I):
            domain_hits.append(term.upper())

    topics = []
    # a light topic extractor based on telecom issue phrases
    for phrase in [
        "cell down", "handover failure", "registration failure", "call drop", "packet loss",
        "high prb", "alarm", "latency", "sctp", "dns", "fiber cut", "congestion"
    ]:
        if phrase in text.lower() or phrase in assistant.lower():
            topics.append(phrase)

    summary_parts = []
    if preferences:
        summary_parts.append("Preferences: " + ", ".join(sorted(set(preferences))))
    if domain_hits:
        summary_parts.append("Domains: " + ", ".join(sorted(set(domain_hits))))
    if topics:
        summary_parts.append("Recent topics: " + ", ".join(sorted(set(topics))))

    return {
        "preferences": sorted(set(preferences)),
        "domains": sorted(set(domain_hits)),
        "topics": sorted(set(topics)),
        "summary": " | ".join(summary_parts) if summary_parts else "",
    }


@dataclass
class Message:
    role: str
    content: str
    timestamp: str


class SessionMemoryStore:
    """Short-term memory: per-session conversation history."""

    def __init__(self, path: Path = SESSION_MEMORY_PATH) -> None:
        self.path = path

    def _load(self) -> dict:
        return _read_json(self.path, default={"sessions": {}})

    def _save(self, data: dict) -> None:
        _atomic_write(self.path, data)

    def get_history(self, session_id: str) -> List[dict]:
        data = self._load()
        return data.get("sessions", {}).get(session_id, [])

    def append(self, session_id: str, role: str, content: str) -> None:
        with _FILE_LOCK:
            data = self._load()
            sessions = data.setdefault("sessions", {})
            history = sessions.setdefault(session_id, [])
            history.append(asdict(Message(role=role, content=content, timestamp=_now())))
            history[:] = history[-(MAX_CHAT_HISTORY * 2):]
            self._save(data)

    def clear(self, session_id: str) -> None:
        with _FILE_LOCK:
            data = self._load()
            data.setdefault("sessions", {}).pop(session_id, None)
            self._save(data)


class LongTermMemoryStore:
    """Persistent memory: user facts/preferences across conversations."""

    def __init__(self, path: Path = LONG_TERM_MEMORY_PATH) -> None:
        self.path = path

    def _load(self) -> dict:
        return _read_json(self.path, default={"users": {}})

    def _save(self, data: dict) -> None:
        _atomic_write(self.path, data)

    def get(self, user_id: str) -> dict:
        data = self._load()
        users = data.get("users", {})
        return users.get(user_id, {
            "user_id": user_id,
            "summary": "",
            "preferences": [],
            "domains": [],
            "topics": [],
            "updated_at": None,
        })

    def update(self, user_id: str, user_text: str, assistant_text: str | None = None) -> dict:
        with _FILE_LOCK:
            data = self._load()
            users = data.setdefault("users", {})
            existing = users.get(user_id, {
                "user_id": user_id,
                "summary": "",
                "preferences": [],
                "domains": [],
                "topics": [],
                "updated_at": None,
            })
            extracted = extract_memory_facts(user_text, assistant_text)

            existing["preferences"] = sorted(set(existing.get("preferences", [])) | set(extracted["preferences"]))
            existing["domains"] = sorted(set(existing.get("domains", [])) | set(extracted["domains"]))
            existing["topics"] = sorted(set(existing.get("topics", [])) | set(extracted["topics"]))

            if extracted["summary"]:
                if existing.get("summary"):
                    # Keep it compact and readable.
                    existing["summary"] = f"{existing['summary']} || {extracted['summary']}"
                else:
                    existing["summary"] = extracted["summary"]

            existing["updated_at"] = _now()
            users[user_id] = existing
            self._save(data)
            return existing


session_memory_store = SessionMemoryStore()
long_term_memory_store = LongTermMemoryStore()
