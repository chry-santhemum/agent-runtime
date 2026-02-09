from __future__ import annotations

import json
import datetime as dt
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class SessionArtifacts:
    session_dir: Path

    @property
    def events_raw(self) -> Path:
        return self.session_dir / "engine_events.jsonl"

    @property
    def events_normalized(self) -> Path:
        return self.session_dir / "normalized_events.jsonl"

    @property
    def stdout_log(self) -> Path:
        return self.session_dir / "stdout.log"

    @property
    def stderr_log(self) -> Path:
        return self.session_dir / "stderr.log"

    @property
    def summary(self) -> Path:
        return self.session_dir / "summary.md"

    @property
    def diff_stat(self) -> Path:
        return self.session_dir / "git_diff_stat.txt"

    @property
    def diff_patch(self) -> Path:
        return self.session_dir / "git_diff.patch"


@dataclass
class EngineResult:
    status: str
    summary_path: Optional[Path]
    detail: str


def write_summary(path: Path, note: str, changed: Iterable[str], tried: Iterable[str], failures: Iterable[str]) -> None:
    changed_block = "\n".join(f"- {item}" for item in changed) or "- _None_"
    tried_block = "\n".join(f"- {item}" for item in tried) or "- _None_"
    failure_block = "\n".join(f"- {item}" for item in failures) or "- _None_"
    path.write_text(
        f"""# Session Summary

## What I changed
{changed_block}

## Why
- {note}

## What I tried
{tried_block}

## Current failures
{failure_block}

## Next steps
- Review session artifacts and decide whether to iterate or evaluate.

## Subagents spawned
- None
""".strip()
    )


def run_stub_session(artifacts: SessionArtifacts, note: str) -> EngineResult:
    artifacts.session_dir.mkdir(parents=True, exist_ok=True)
    artifacts.events_raw.write_text("")
    artifacts.events_normalized.write_text("")
    artifacts.stdout_log.write_text("")
    artifacts.stderr_log.write_text("")
    write_summary(artifacts.summary, note, ["_Stub_: no code changes were made."], [], [])
    return EngineResult(status="stubbed", summary_path=artifacts.summary, detail="stubbed")


def _now_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def run_engine_session(
    executor,
    command: list[str],
    artifacts: SessionArtifacts,
    note: str,
    task_id: str,
    session_id: str,
    engine: str,
) -> EngineResult:
    artifacts.session_dir.mkdir(parents=True, exist_ok=True)
    result = executor(command)
    artifacts.stdout_log.write_text(result.stdout)
    artifacts.stderr_log.write_text(result.stderr)
    artifacts.events_raw.write_text(result.stdout)
    _normalize_events(result.stdout.splitlines(), artifacts.events_normalized, task_id, session_id, engine)
    changed = ["Engine run completed."]
    failures = []
    if result.returncode != 0:
        failures.append(f"Engine command failed with exit code {result.returncode}.")
    write_summary(artifacts.summary, note, changed, [f"{' '.join(command)}"], failures)
    return EngineResult(
        status="success" if result.returncode == 0 else "failed",
        summary_path=artifacts.summary,
        detail=f"exit_code={result.returncode}",
    )


def append_normalized_event(path: Path, payload: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _normalize_events(lines: Iterable[str], output: Path, task_id: str, session_id: str, engine: str) -> None:
    output.write_text("")
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            event_type = payload.get("type", "unknown") if isinstance(payload, dict) else "unknown"
        except json.JSONDecodeError:
            payload = {"message": line}
            event_type = "text"
        append_normalized_event(
            output,
            {
                "ts": _now_iso(),
                "task_id": task_id,
                "session_id": session_id,
                "engine": engine,
                "type": event_type,
                "payload": payload,
            },
        )
