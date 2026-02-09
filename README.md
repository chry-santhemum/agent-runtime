# Lightweight Agent Harness (Scaffold)

This repository contains a scaffold implementation of the **Lightweight Agent Harness v1** spec.
It focuses on directory layout, state tracking, config generation, basic CLI workflow, and initial
Docker container lifecycle management. The runner now executes engine commands inside containers,
writes session artifacts, and runs configured tests/judge prompts.

## Quick start

```bash
python -m harness.cli init
python -m harness.cli run --goal "Prototype" --mode closed --engine codex
python -m harness.cli status
```

## What is included

- `.harness/config.yaml` template aligned with the spec.
- SQLite state database for tasks and sessions.
- Bus directory structure for IPC.
- Memory index + skills mirror for Claude and Codex.
- A minimal TUI view using Rich (falls back to text).
- `scripts/harnessctl.py` for container-side IPC commands (spawn, wait, ask, steering).

## What is stubbed

- Full Docker orchestration (exec streams, teardown, retries).
- Rich TUI interaction (inbox, logs, event streaming).

## Next steps

- Expand the TUI to support inbox, task detail, and streaming logs.
- Add subtask contract enforcement and merge promotion workflows.
