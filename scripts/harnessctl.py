from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path


BUS_ROOT = Path("/harness-bus")


def _ensure_bus() -> None:
    if not BUS_ROOT.exists():
        raise SystemExit("/harness-bus not mounted; harnessctl must run in container.")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def cmd_spawn(args: argparse.Namespace) -> None:
    _ensure_bus()
    req_id = args.req_id or f"R{uuid.uuid4().hex[:6]}"
    payload = {
        "type": "spawn",
        "req_id": req_id,
        "parent_task_id": args.parent_task_id,
        "contract_relpath": args.contract,
        "engine_preference": args.engine,
        "timestamp": time.time(),
    }
    _write_json(BUS_ROOT / "requests" / f"{req_id}.json", payload)
    print(req_id)


def cmd_wait(args: argparse.Namespace) -> None:
    _ensure_bus()
    resp_path = BUS_ROOT / "responses" / f"{args.req_id}.json"
    while not resp_path.exists():
        time.sleep(0.5)
    print(resp_path.read_text())


def cmd_ask(args: argparse.Namespace) -> None:
    _ensure_bus()
    qid = f"Q{uuid.uuid4().hex[:6]}"
    payload = {
        "id": qid,
        "text": args.text,
        "choices": args.choices,
        "timestamp": time.time(),
    }
    _write_json(BUS_ROOT / "questions" / f"{qid}.json", payload)
    print(qid)


def cmd_steering(args: argparse.Namespace) -> None:
    _ensure_bus()
    steering_path = BUS_ROOT / "steering" / f"{args.task_id}.md"
    if args.action == "get":
        if steering_path.exists():
            print(steering_path.read_text())
        else:
            print("")
    elif args.action == "set":
        steering_path.write_text(args.text or "")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harnessctl")
    sub = parser.add_subparsers(dest="command", required=True)

    spawn = sub.add_parser("spawn")
    spawn.add_argument("--contract", required=True)
    spawn.add_argument("--parent-task-id", required=True)
    spawn.add_argument("--engine", default="codex")
    spawn.add_argument("--req-id", default=None)

    wait = sub.add_parser("wait")
    wait.add_argument("req_id")

    ask = sub.add_parser("ask")
    ask.add_argument("--text", required=True)
    ask.add_argument("--choices", nargs="*", default=[])

    steering = sub.add_parser("steering")
    steering.add_argument("action", choices=["get", "set"])
    steering.add_argument("--task-id", required=True)
    steering.add_argument("--text")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "spawn":
        cmd_spawn(args)
    elif args.command == "wait":
        cmd_wait(args)
    elif args.command == "ask":
        cmd_ask(args)
    elif args.command == "steering":
        cmd_steering(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
