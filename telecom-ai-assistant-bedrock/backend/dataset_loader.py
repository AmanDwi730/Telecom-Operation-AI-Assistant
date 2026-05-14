from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from config import DATASET_PATH, MAX_CONTEXT_ROWS, SUPPLEMENTAL_DIR

KEY_FIELDS = [
    "Incident_ID",
    "Technology_Domain",
    "Issue_Type",
    "Region",
    "Severity",
    "KPI_Impact",
    "Question",
    "Root_Cause",
    "Resolution",
    "Recommended_Action",
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).strip().lower())


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9+/.:-]+", _normalize(text))


def _weighted_score(query: str, candidate_text: str, row: dict | None = None) -> float:
    q_tokens = set(_tokenize(query))
    c_tokens = set(_tokenize(candidate_text))
    if not q_tokens or not c_tokens:
        return 0.0

    overlap = q_tokens & c_tokens
    score = len(overlap) / math.sqrt(len(q_tokens) * len(c_tokens))

    query_lower = query.lower()
    candidate_lower = candidate_text.lower()

    # Telecom-specific boosts
    boosts = [
        "5g", "4g", "lte", "ran", "core", "ims", "volte", "voip", "fiber",
        "mpls", "packet loss", "call drop", "registration failure", "handover",
        "cell down", "upf", "amf", "smf", "sctp", "dns", "alarm"
    ]
    for phrase in boosts:
        if phrase in query_lower and phrase in candidate_lower:
            score += 0.35

    if row:
        if row.get("Technology_Domain") and row["Technology_Domain"].lower().replace("_", " ") in query_lower:
            score += 0.45
        if row.get("Issue_Type") and _normalize(row["Issue_Type"]) in query_lower:
            score += 0.65
        if row.get("Severity") and row["Severity"].lower() in query_lower:
            score += 0.1

    return score


@lru_cache(maxsize=1)
def _load_all_sheets() -> pd.DataFrame:
    """Load every row from every sheet (no truncation). Cached once."""
    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found at {DATASET_PATH}. "
            "Place the 3gpp_standard_telecom_dataset_updated.xlsx in data/."
        )

    xls = pd.ExcelFile(DATASET_PATH)
    frames = []
    for sheet_name in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet_name)
        df = df.copy()
        df["source_sheet"] = sheet_name
        frames.append(df)

    dataset = pd.concat(frames, ignore_index=True)
    dataset = dataset.drop_duplicates()
    return dataset


@lru_cache(maxsize=1)
def load_dataset() -> pd.DataFrame:
    dataset = _load_all_sheets()
    num_sheets = dataset["source_sheet"].nunique() or 1
    return dataset.head(MAX_CONTEXT_ROWS * num_sheets)


@lru_cache(maxsize=1)
def load_supplemental_texts() -> List[Dict[str, str]]:
    docs: List[Dict[str, str]] = []
    if SUPPLEMENTAL_DIR.exists():
        for path in sorted(SUPPLEMENTAL_DIR.glob("*.txt")):
            text = path.read_text(encoding="utf-8").strip()
            if text:
                docs.append({
                    "source": path.name,
                    "title": path.stem.replace("_", " ").title(),
                    "text": text,
                })
    return docs


def row_to_record(row: pd.Series) -> Dict[str, str]:
    return {
        "Incident_ID": str(row.get("Incident_ID", "")),
        "Technology_Domain": str(row.get("Technology_Domain", "")),
        "Issue_Type": str(row.get("Issue_Type", "")),
        "Region": str(row.get("Region", "")),
        "Severity": str(row.get("Severity", "")),
        "KPI_Impact": str(row.get("KPI_Impact", "")),
        "Question": str(row.get("Question", "")),
        "Root_Cause": str(row.get("Root_Cause", "")),
        "Resolution": str(row.get("Resolution", "")),
        "Recommended_Action": str(row.get("Recommended_Action", "")),
        "source_sheet": str(row.get("source_sheet", "")),
    }


def format_record(record: Dict[str, str]) -> str:
    return (
        f"Incident ID: {record['Incident_ID']}\n"
        f"Technology Domain: {record['Technology_Domain']}\n"
        f"Issue Type: {record['Issue_Type']}\n"
        f"Region: {record['Region']}\n"
        f"Severity: {record['Severity']}\n"
        f"KPI Impact: {record['KPI_Impact']}\n"
        f"Question: {record['Question']}\n"
        f"Root Cause: {record['Root_Cause']}\n"
        f"Resolution: {record['Resolution']}\n"
        f"Recommended Action: {record['Recommended_Action']}\n"
        f"Source Sheet: {record['source_sheet']}"
    )


def _dataset_candidates(query: str, top_k: int = 5) -> List[Tuple[float, Dict[str, str]]]:
    df = load_dataset()
    scored: List[Tuple[float, Dict[str, str]]] = []
    for _, row in df.iterrows():
        record = row_to_record(row)
        candidate_text = " ".join([record.get(f, "") for f in KEY_FIELDS])
        score = _weighted_score(query, candidate_text, record)
        if score > 0:
            scored.append((score, record))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]


def _supplemental_candidates(query: str, top_k: int = 3) -> List[Tuple[float, Dict[str, str]]]:
    docs = load_supplemental_texts()
    scored: List[Tuple[float, Dict[str, str]]] = []
    for doc in docs:
        score = _weighted_score(query, doc["text"], None)
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]


def retrieve_context(query: str, top_k: int = 5) -> Dict[str, list]:
    dataset_hits = _dataset_candidates(query, top_k=top_k)
    supplemental_hits = _supplemental_candidates(query, top_k=3)

    dataset_context = []
    for score, record in dataset_hits:
        dataset_context.append({
            "score": round(score, 4),
            "source_type": "dataset",
            "source": record["Incident_ID"],
            "title": f"{record['Technology_Domain']} | {record['Issue_Type']}",
            "text": format_record(record),
            "metadata": record,
        })

    supplemental_context = []
    for score, doc in supplemental_hits:
        supplemental_context.append({
            "score": round(score, 4),
            "source_type": "supplemental",
            "source": doc["source"],
            "title": doc["title"],
            "text": doc["text"],
            "metadata": {"source": doc["source"], "title": doc["title"]},
        })

    return {"dataset_hits": dataset_context, "supplemental_hits": supplemental_context}


def get_severity_counts() -> Dict[str, int]:
    """Return incident counts grouped by severity from the full dataset."""
    df = _load_all_sheets()
    canonical = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"}
    counts: Dict[str, int] = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}

    if "Severity" not in df.columns:
        return counts

    for raw_value, cnt in df["Severity"].value_counts().items():
        key = canonical.get(str(raw_value).strip().lower())
        if key:
            counts[key] += int(cnt)

    return counts


def search_incident_by_id(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """Search incidents by full or partial (last-N-digit) incident ID."""
    df = _load_all_sheets()
    if "Incident_ID" not in df.columns:
        return []

    query = query.strip()
    ids = df["Incident_ID"].astype(str)

    if re.search(r"(?i)3gpp_inc", query):
        mask = ids.str.lower() == query.lower()
    else:
        pattern = re.escape(query) + r"$"
        mask = ids.str.contains(pattern, case=False, na=False)

    matches = df[mask].head(max_results)
    return [row_to_record(row) for _, row in matches.iterrows()]


def build_retrieved_context_block(query: str, top_k: int = 5) -> tuple[str, list]:
    hits = retrieve_context(query, top_k=top_k)
    lines = []
    sources = []

    if hits["dataset_hits"]:
        lines.append("### Retrieved Telecom Incident Matches")
        for idx, hit in enumerate(hits["dataset_hits"], start=1):
            lines.append(f"[D{idx}] {hit['text']}")
            lines.append("")
            sources.append(hit)

    if hits["supplemental_hits"]:
        lines.append("### Retrieved Supplemental Knowledge")
        for idx, hit in enumerate(hits["supplemental_hits"], start=1):
            lines.append(f"[S{idx}] {hit['title']}: {hit['text']}")
            lines.append("")
            sources.append(hit)

    if not lines:
        lines.append("No direct context was retrieved. Rely on telecom best practice only if explicitly necessary.")

    return "\n".join(lines).strip(), sources
