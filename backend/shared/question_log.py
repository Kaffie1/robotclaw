from __future__ import annotations

import json

from backend.shared.config import RUNTIME_DIR
from backend.shared.time import now_iso


QUESTION_LOG_FILE = RUNTIME_DIR / "questions.log"


def append_question(session_id: str, content: str) -> None:
    question = str(content or "").strip()
    if not question:
        return
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": now_iso(),
        "session_id": session_id,
        "question": question,
    }
    with QUESTION_LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")
