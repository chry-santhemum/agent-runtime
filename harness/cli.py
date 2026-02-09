from __future__ import annotations

import argparse
import importlib.util
import sqlite3
from pathlib import Path
from typing import Optional

from .bus import BusPaths
from .config import CONFIG_TEMPLATE, ConfigPaths, DEFAULT_GITIGNORE_LINES, load_config
from .runner import HarnessRunner
from .state import init_db, list_tasks


def _write_if_missing(path: Path, content: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _ensure_gitignore(root: Path) -> None:
    gitignore = root / ".gitignore"
    existing = []
    if gitignore.exists():
        existing = gitignore.read_text().splitlines()
    additions = [line for line in DEFAULT_GITIGNORE_LINES if line not in existing]
    if additions:
        with gitignore.open("a", encoding="utf-8") as handle:
            if existing and existing[-1].strip():
                handle.write("\n")
            handle.write("\n".join(additions) + "\n")


def init_command(root: Path) -> None:
    paths = ConfigPaths(root)
    paths.harness_dir.mkdir(parents=True, exist_ok=True)
    _write_if_missing(paths.config_file, CONFIG_TEMPLATE)
    init_db(paths.state_db)

    bus_paths = BusPaths(paths.harness_dir / "bus")
    bus_paths.ensure()

    for subdir in ["runs", "workspaces", "auth", "caches"]:
        (paths.harness_dir / subdir).mkdir(parents=True, exist_ok=True)

    paths.memory_dir.mkdir(parents=True, exist_ok=True)
    _write_if_missing(paths.memory_dir / "index.md", "# Memory Index\n")

    _write_if_missing(
        paths.claude_skills_dir / "memory-index" / "SKILL.md",
        """---
name: memory-index
description: Use when you need the shared memory index for context.
---

Read `memory/index.md` and apply it. If you learn something new and important, propose an update via harness memory workflow.
""",
    )
    _write_if_missing(
        paths.codex_skills_dir / "memory-index" / "SKILL.md",
        """---
name: memory-index
description: Use when you need the shared memory index for context.
---

Read `memory/index.md` and apply it. If you learn something new and important, propose an update via harness memory workflow.
""",
    )

    _ensure_gitignore(root)


def run_command(root: Path, goal: Optional[str], mode: str, engine: str) -> None:
    paths = ConfigPaths(root)
    init_command(root)
    config = load_config(paths.config_file)
    runner = HarnessRunner(root, config)
    runner.run_root(goal=goal, mode=mode, engine=engine)


def status_command(root: Path) -> None:
    paths = ConfigPaths(root)
    if not paths.state_db.exists():
        print("No harness state found. Run `harness init` first.")
        return
    with sqlite3.connect(paths.state_db) as conn:
        rows = list(list_tasks(conn))
    if not rows:
        print("No tasks recorded.")
        return
    for row in rows:
        print(f"{row.task_id} {row.status} engine={row.engine} depth={row.depth}")


def doctor_command(root: Path) -> None:
    paths = ConfigPaths(root)
    print(f"Repo: {root}")
    print(f"Harness dir: {paths.harness_dir} ({'exists' if paths.harness_dir.exists() else 'missing'})")
    print(f"Config: {paths.config_file} ({'exists' if paths.config_file.exists() else 'missing'})")
    print(f"State DB: {paths.state_db} ({'exists' if paths.state_db.exists() else 'missing'})")


def tui_command(root: Path) -> None:
    paths = ConfigPaths(root)
    if not paths.state_db.exists():
        print("No harness state found. Run `harness init` first.")
        return
    if importlib.util.find_spec("rich") is None:
        print("Rich not installed; falling back to text status.")
        status_command(root)
        return
    from rich.console import Console
    from rich.table import Table
    with sqlite3.connect(paths.state_db) as conn:
        rows = list(list_tasks(conn))
    table = Table(title="Harness Tasks")
    table.add_column("Task ID")
    table.add_column("Status")
    table.add_column("Engine")
    table.add_column("Depth")
    for row in rows:
        table.add_row(row.task_id, row.status, row.engine, str(row.depth))
    console = Console()
    console.print(table)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness", description="Lightweight agent harness scaffold")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Initialize harness directories and config")

    run = sub.add_parser("run", help="Run the harness root task")
    run.add_argument("--goal", default=None)
    run.add_argument("--mode", default="closed", choices=["closed", "open"])
    run.add_argument("--engine", default="codex", choices=["codex", "claude", "hybrid"])

    sub.add_parser("status", help="Show task status")
    sub.add_parser("doctor", help="Check harness environment")
    sub.add_parser("tui", help="Launch lightweight TUI view")

    auth = sub.add_parser("auth", help="Bootstrap auth for an engine")
    auth.add_argument("engine", choices=["codex", "claude"])

    return parser


def auth_command(root: Path, engine: str) -> None:
    paths = ConfigPaths(root)
    init_command(root)
    auth_dir = paths.harness_dir / "auth" / engine
    auth_dir.mkdir(parents=True, exist_ok=True)
    print(f"Auth directory prepared at {auth_dir}. Run the login flow in a container.")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    root = Path.cwd()

    if args.command == "init":
        init_command(root)
    elif args.command == "run":
        run_command(root, args.goal, args.mode, args.engine)
    elif args.command == "status":
        status_command(root)
    elif args.command == "doctor":
        doctor_command(root)
    elif args.command == "tui":
        tui_command(root)
    elif args.command == "auth":
        auth_command(root, args.engine)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
