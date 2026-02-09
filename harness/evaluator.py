from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List


@dataclass(frozen=True)
class EvaluationResult:
    status: str
    notes: str
    test_exit_code: int


@dataclass(frozen=True)
class JudgeResult:
    status: str
    notes: str
    raw_output: str


def write_test_output(path: Path, lines: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def run_stub_evaluation(test_log: Path) -> EvaluationResult:
    write_test_output(test_log, ["Stub evaluation: no tests executed."])
    return EvaluationResult(status="stubbed", notes="No tests run; evaluator not implemented yet.", test_exit_code=0)


def run_tests(
    commands: List[str],
    test_log: Path,
    executor: Callable[[List[str], str], object],
    workdir: str,
) -> EvaluationResult:
    output_lines: List[str] = []
    last_code = 0
    for command in commands:
        output_lines.append(f"$ {command}")
        result = executor(["bash", "-lc", command], workdir)
        output_lines.append(result.stdout)
        if result.stderr:
            output_lines.append(result.stderr)
        last_code = result.returncode
        if result.returncode != 0:
            output_lines.append(f"Command failed with exit code {result.returncode}.")
            break
    write_test_output(test_log, output_lines)
    status = "passed" if last_code == 0 else "failed"
    return EvaluationResult(status=status, notes="Tests executed.", test_exit_code=last_code)


def run_judge(
    executor: Callable[[List[str]], object],
    command: List[str],
    prompt: str,
    output_path: Path,
) -> JudgeResult:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = executor([*command, prompt])
    output_path.write_text(result.stdout)
    status = "passed" if result.returncode == 0 else "failed"
    return JudgeResult(status=status, notes="Judge executed.", raw_output=result.stdout)
