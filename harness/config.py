from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml

CONFIG_TEMPLATE = """engine_default: codex   # codex | claude | hybrid

independence_level: 1   # 1 = auto-answer, 2 = human answers + plan gate

loop:
  main_iteration_timeout_s: 1200
  max_parallel_tasks: 6
  max_depth: 12

git:
  default_branch: main
  share_git_objects: false     # you said optional; default OFF
  preserve_child_commits: true # REQUIRED
  sync_strategy: merge         # merge | rebase (v1 default merge)
  promotion:
    fast_forward_if_possible: true
    conflict_policy: spawn_merge_fixer

docker:
  image: harness-agent:latest
  workdir_in_container: /workspace
  network_mode: bridge         # configurable (none|bridge)
  cpus: "2"
  memory: "6g"

auth:
  codex:
    host_dir: .harness/auth/codex
    container_home_subdir: .codex
    env:
      CODEX_HOME: /home/agent/.codex
  claude:
    host_dir: .harness/auth/claude
    # mounted into /home/agent to persist ~/.claude, ~/.claude.json, etc.

caches:
  enabled: true
  mounts:
    npm:   .harness/caches/npm
    pnpm:  .harness/caches/pnpm
    yarn:  .harness/caches/yarn
    pip:   .harness/caches/pip
    uv:    .harness/caches/uv
    cargo: .harness/caches/cargo
    go:    .harness/caches/go
    maven: .harness/caches/maven
    gradle:.harness/caches/gradle

contracts:
  default_attempt_limit: 5
  temp_dir_name: .harness_tmp_contracts

evaluation:
  require_tests: true
  require_judge: true
  judge_engine: codex         # codex | claude
  judge_model: ""             # optional

goals:
  closed:
    test_commands: []         # user fills (or default)
  open:
    loss_commands: []         # user fills
    loss_interval_s: 600

observability:
  tui_refresh_ms: 250
  keep_last_sessions: 50

engines:
  codex:
    cmd: codex
    exec_args:
      - exec
      - --json
      - --ask-for-approval
      - never
      - --sandbox
      - workspace-write
    planner_args:
      - exec
      - --json
      - --ask-for-approval
      - never
      - --sandbox
      - read-only
    judge_args:
      - exec
      - --json
      - --ask-for-approval
      - never
      - --sandbox
      - read-only
    structured_output:
      schema_flag: --output-schema
      last_message_flag: --output-last-message

  claude:
    cmd: claude
    exec_args:
      - -p
      - --output-format
      - stream-json
      - --verbose
      - --include-partial-messages
    judge_args:
      - -p
      - --output-format
      - json
      # judge uses --json-schema (see prompts)
"""


@dataclass(frozen=True)
class ConfigPaths:
    root: Path

    @property
    def harness_dir(self) -> Path:
        return self.root / ".harness"

    @property
    def config_file(self) -> Path:
        return self.harness_dir / "config.yaml"

    @property
    def state_db(self) -> Path:
        return self.harness_dir / "state.sqlite"

    @property
    def memory_dir(self) -> Path:
        return self.root / "memory"

    @property
    def claude_skills_dir(self) -> Path:
        return self.root / ".claude" / "skills"

    @property
    def codex_skills_dir(self) -> Path:
        return self.root / ".agents" / "skills"


DEFAULT_GITIGNORE_LINES = [
    ".harness/workspaces/**",
    ".harness/runs/**",
    ".harness/bus/**",
    ".harness/auth/**",
    ".harness/caches/**",
    "CLAUDE.local.md",
    "AGENTS.override.md",
    ".harness_tmp_contracts/**",
]


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}
