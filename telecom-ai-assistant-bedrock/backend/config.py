from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
DATA_DIR = ROOT_DIR / "data"
SUPPLEMENTAL_DIR = DATA_DIR / "supplemental"
MEMORY_DIR = DATA_DIR / "memory"

DATASET_PATH = Path(os.getenv("DATASET_PATH", str(DATA_DIR / "3gpp_standard_telecom_dataset_updated.xlsx")))
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.amazon.nova-lite-v1:0")
REGION = os.getenv("AWS_DEFAULT_REGION", os.getenv("AWS_REGION", "us-east-1"))
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_URL = os.getenv("API_URL", f"http://{API_HOST}:{API_PORT}")

MAX_CONTEXT_ROWS = int(os.getenv("MAX_CONTEXT_ROWS", "120"))
TOP_K = int(os.getenv("TOP_K", "5"))
MAX_CHAT_HISTORY = int(os.getenv("MAX_CHAT_HISTORY", "8"))

SESSION_MEMORY_PATH = MEMORY_DIR / "session_memory.json"
LONG_TERM_MEMORY_PATH = MEMORY_DIR / "long_term_memory.json"

for p in (DATA_DIR, SUPPLEMENTAL_DIR, MEMORY_DIR):
    p.mkdir(parents=True, exist_ok=True)
