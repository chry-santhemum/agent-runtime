from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspacePaths:
    root: Path

    def task_repo(self, task_id: str) -> Path:
        return self.root / task_id / "repo"


def ensure_clone(source_repo: Path, dest_repo: Path) -> None:
    if dest_repo.exists():
        return
    dest_repo.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "git",
        "clone",
        str(source_repo),
        str(dest_repo),
    ], check=True)
