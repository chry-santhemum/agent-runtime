from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class BusPaths:
    root: Path

    @property
    def requests(self) -> Path:
        return self.root / "requests"

    @property
    def responses(self) -> Path:
        return self.root / "responses"

    @property
    def questions(self) -> Path:
        return self.root / "questions"

    @property
    def answers(self) -> Path:
        return self.root / "answers"

    @property
    def steering(self) -> Path:
        return self.root / "steering"

    def ensure(self) -> None:
        for path in (self.requests, self.responses, self.questions, self.answers, self.steering):
            path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def write_question(bus: BusPaths, payload: Dict[str, Any]) -> Path:
    question_id = payload.get("id", "QUNKNOWN")
    path = bus.questions / f"{question_id}.json"
    write_json(path, payload)
    return path


def wait_for_answer(bus: BusPaths, question_id: str, timeout_s: Optional[int] = None) -> Optional[Dict[str, Any]]:
    answer_path = bus.answers / f"{question_id}.json"
    waited = 0
    while not answer_path.exists():
        if timeout_s is not None and waited >= timeout_s:
            return None
        time.sleep(1)
        waited += 1
    return json.loads(answer_path.read_text())
