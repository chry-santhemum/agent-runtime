from __future__ import annotations

import datetime as dt
import sqlite3
import subprocess
import uuid
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .config import ConfigPaths
from .docker_manager import DockerManager, build_task_spec
from .bus import BusPaths, wait_for_answer, write_question
from .engine import SessionArtifacts, run_engine_session
from .evaluator import EvaluationResult, JudgeResult, run_judge, run_tests
from .state import (
    SessionRecord,
    TaskRecord,
    init_db,
    insert_session,
    insert_task,
    update_session_status,
    update_task_status,
)
from .workspace import WorkspacePaths, ensure_clone


class HarnessRunner:
    def __init__(self, root: Path, config: Dict[str, object]) -> None:
        self.root = root
        self.config = config
        self.paths = ConfigPaths(root)
        init_db(self.paths.state_db)

    def run_root(self, goal: Optional[str], mode: str, engine: str) -> None:
        task_id = f"T{uuid.uuid4().hex[:8]}"
        now = self._now_iso()
        workspaces = WorkspacePaths(self.paths.harness_dir / "workspaces")
        task_repo = workspaces.task_repo(task_id)
        ensure_clone(self.root, task_repo)

        task_spec = build_task_spec(self.root, task_id, self.config)
        docker_manager = DockerManager(task_spec)
        docker_manager.ensure_container()
        bus = BusPaths(self.paths.harness_dir / "bus")
        bus.ensure()

        with sqlite3.connect(self.paths.state_db) as conn:
            insert_task(
                conn,
                TaskRecord(
                    task_id=task_id,
                    parent_task_id=None,
                    depth=0,
                    engine=engine,
                    status="RUNNING",
                    goal=goal,
                    created_at=now,
                    updated_at=now,
                ),
            )
            conn.commit()

        iteration = 0
        while True:
            iteration += 1
            session_id = f"S{uuid.uuid4().hex[:8]}"
            session_dir = self._session_dir(task_id, session_id)
            artifacts = SessionArtifacts(session_dir)

            if self._independence_level() == 2:
                self._run_plan_gate(docker_manager, artifacts, task_id, session_id, engine, bus)

            with sqlite3.connect(self.paths.state_db) as conn:
                insert_session(
                    conn,
                    SessionRecord(
                        session_id=session_id,
                        task_id=task_id,
                        engine=engine,
                        status="RUNNING",
                        started_at=self._now_iso(),
                        ended_at=None,
                        summary_path=None,
                        artifacts_dir=str(session_dir),
                    ),
                )
                conn.commit()

            prompt = self._build_worker_prompt(goal, mode)
            command = self._engine_command(engine, prompt)
            note = f"Root iteration {iteration}"
            result = run_engine_session(
                docker_manager.exec,
                command,
                artifacts,
                note,
                task_id,
                session_id,
                engine,
            )

            self._write_git_diff(task_repo, artifacts)

            test_log = session_dir / "test_output.log"
            eval_result = self._evaluate(docker_manager, test_log, task_spec.docker.workdir_in_container)
            judge_result = self._judge_if_required(
                docker_manager,
                artifacts,
                eval_result,
                engine,
                task_spec.docker.workdir_in_container,
            )

            with sqlite3.connect(self.paths.state_db) as conn:
                update_session_status(
                    conn,
                    session_id,
                    "DONE" if result.status == "success" else "FAILED",
                    self._now_iso(),
                    str(result.summary_path) if result.summary_path else None,
                )
                update_task_status(conn, task_id, "RUNNING", self._now_iso())
                conn.commit()

            if mode == "closed" and eval_result.status == "passed" and judge_result.status != "failed":
                with sqlite3.connect(self.paths.state_db) as conn:
                    update_task_status(conn, task_id, "DONE", self._now_iso())
                    conn.commit()
                break
            if mode == "open":
                continue
            if mode == "closed" and eval_result.status != "passed":
                continue

    def _engine_command(self, engine: str, prompt: str) -> List[str]:
        engines = self.config.get("engines", {}) if isinstance(self.config.get("engines", {}), dict) else {}
        engine_conf = engines.get(engine, {}) if isinstance(engines, dict) else {}
        cmd = engine_conf.get("cmd", engine)
        args = engine_conf.get("exec_args", [])
        if not isinstance(args, list):
            args = []
        return [str(cmd), *[str(a) for a in args], prompt]

    def _evaluate(self, docker_manager: DockerManager, test_log: Path, workdir: str) -> EvaluationResult:
        evaluation = self.config.get("evaluation", {}) if isinstance(self.config.get("evaluation", {}), dict) else {}
        require_tests = bool(evaluation.get("require_tests", True))
        if not require_tests:
            return EvaluationResult(status="skipped", notes="Tests skipped", test_exit_code=0)
        goals = self.config.get("goals", {}) if isinstance(self.config.get("goals", {}), dict) else {}
        closed = goals.get("closed", {}) if isinstance(goals, dict) else {}
        commands = closed.get("test_commands", []) if isinstance(closed, dict) else []
        if not commands:
            return EvaluationResult(status="skipped", notes="No test commands configured", test_exit_code=0)
        return run_tests([str(c) for c in commands], test_log, docker_manager.exec, workdir)

    def _judge_if_required(
        self,
        docker_manager: DockerManager,
        artifacts: SessionArtifacts,
        eval_result: EvaluationResult,
        engine: str,
        workdir: str,
    ) -> JudgeResult:
        evaluation = self.config.get("evaluation", {}) if isinstance(self.config.get("evaluation", {}), dict) else {}
        require_judge = bool(evaluation.get("require_judge", True))
        if not require_judge:
            return JudgeResult(status="skipped", notes="Judge skipped", raw_output="")
        judge_engine = evaluation.get("judge_engine", engine)
        prompt = self._build_judge_prompt(artifacts, eval_result)
        command = self._judge_command(judge_engine)
        output_path = artifacts.session_dir / "judge_output.txt"
        return run_judge(lambda cmd: docker_manager.exec(cmd, workdir), command, prompt, output_path)

    def _build_judge_prompt(self, artifacts: SessionArtifacts, eval_result: EvaluationResult) -> str:
        diff_stat = artifacts.diff_stat.read_text() if artifacts.diff_stat.exists() else ""
        test_log = (artifacts.session_dir / "test_output.log").read_text() if (artifacts.session_dir / "test_output.log").exists() else ""
        summary = artifacts.summary.read_text() if artifacts.summary.exists() else ""
        return (
            "You are a judge. Decide PASS if the goal is complete; otherwise FAIL.\\n\\n"
            f"Summary:\\n{summary}\\n\\nDiffstat:\\n{diff_stat}\\n\\nTests:\\n{test_log}\\n\\n"
            f"Test status: {eval_result.status}\\n"
        )

    def _judge_command(self, engine: str) -> List[str]:
        engines = self.config.get("engines", {}) if isinstance(self.config.get("engines", {}), dict) else {}
        engine_conf = engines.get(engine, {}) if isinstance(engines, dict) else {}
        cmd = engine_conf.get("cmd", engine)
        args = engine_conf.get("judge_args", [])
        if not isinstance(args, list):
            args = []
        return [str(cmd), *[str(a) for a in args]]

    def _independence_level(self) -> int:
        level = self.config.get("independence_level", 1)
        try:
            return int(level)
        except (TypeError, ValueError):
            return 1

    def _run_plan_gate(
        self,
        docker_manager: DockerManager,
        artifacts: SessionArtifacts,
        task_id: str,
        session_id: str,
        engine: str,
        bus: BusPaths,
    ) -> None:
        plan_command = self._planner_command(engine, "Provide a brief plan for the next iteration.")
        note = "Planner session"
        run_engine_session(
            docker_manager.exec,
            plan_command,
            artifacts,
            note,
            task_id,
            session_id,
            engine,
        )
        question_id = f"Q{uuid.uuid4().hex[:6]}"
        write_question(
            bus,
            {
                "id": question_id,
                "task_id": task_id,
                "text": "Approve plan for next iteration?",
                "plan_path": str(artifacts.summary),
            },
        )
        wait_for_answer(bus, question_id)

    def _planner_command(self, engine: str, prompt: str) -> List[str]:
        engines = self.config.get("engines", {}) if isinstance(self.config.get("engines", {}), dict) else {}
        engine_conf = engines.get(engine, {}) if isinstance(engines, dict) else {}
        cmd = engine_conf.get("cmd", engine)
        args = engine_conf.get("planner_args", [])
        if not isinstance(args, list):
            args = []
        return [str(cmd), *[str(a) for a in args], prompt]

    def _build_worker_prompt(self, goal: Optional[str], mode: str) -> str:
        if goal:
            return f"Goal: {goal}\\nMode: {mode}\\nProvide progress toward the goal."
        return f"Mode: {mode}\\nContinue work on the repository."

    def _session_dir(self, task_id: str, session_id: str) -> Path:
        return self.paths.harness_dir / "runs" / task_id / "sessions" / session_id

    def _write_git_diff(self, repo: Path, artifacts: SessionArtifacts) -> None:
        diff_stat = self._run_git(repo, ["diff", "--stat"]).strip()
        diff_patch = self._run_git(repo, ["diff"]).strip()
        artifacts.diff_stat.write_text(diff_stat)
        artifacts.diff_patch.write_text(diff_patch)

    def _run_git(self, repo: Path, args: Iterable[str]) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.stdout

    @staticmethod
    def _now_iso() -> str:
        return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
