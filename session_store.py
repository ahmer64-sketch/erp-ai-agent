"""
Session store — save and load conversation history to disk.
Sessions are stored as JSON files in the sessions/ folder.
"""

import json
import os
from datetime import datetime

SESSIONS_DIR = "sessions"


def save_session(history: list) -> str:
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(SESSIONS_DIR, f"session_{ts}.json")
    serializable = []
    for msg in history:
        if isinstance(msg, dict):
            serializable.append({
                "role":    msg.get("role", ""),
                "content": str(msg.get("content", "")),
            })
    with open(path, "w") as f:
        json.dump(serializable, f, indent=2)
    return path


def load_last_session() -> list:
    if not os.path.exists(SESSIONS_DIR):
        return []
    files = sorted(
        [f for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")],
        reverse=True,
    )
    if not files:
        return []
    try:
        with open(os.path.join(SESSIONS_DIR, files[0])) as f:
            return json.load(f)
    except Exception:
        return []


def list_sessions(n: int = 5) -> list[str]:
    if not os.path.exists(SESSIONS_DIR):
        return []
    files = sorted(
        [f for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")],
        reverse=True,
    )
    return files[:n]
