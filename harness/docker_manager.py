from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class DockerConfig:
    image: str
    workdir_in_container: str
    network_mode: str
    cpus: str
    memory: str


@dataclass(frozen=True)
class AuthConfig:
    codex_host_dir: Path
    claude_host_dir: Path
    codex_env: Dict[str, str]


@dataclass(frozen=True)
class CacheConfig:
    enabled: bool
    mounts: Dict[str, Path]


@dataclass(frozen=True)
class TaskContainerSpec:
    task_id: str
    workspace_dir: Path
    bus_dir: Path
    docker: DockerConfig
    auth: AuthConfig
    caches: CacheConfig


CACHE_MOUNT_TARGETS = {
    "npm": "/home/agent/.npm",
    "pnpm": "/home/agent/.pnpm-store",
    "yarn": "/home/agent/.cache/yarn",
    "pip": "/home/agent/.cache/pip",
    "uv": "/home/agent/.cache/uv",
    "cargo_registry": "/home/agent/.cargo/registry",
    "cargo_git": "/home/agent/.cargo/git",
    "go": "/home/agent/go/pkg/mod",
    "maven": "/home/agent/.m2",
    "gradle": "/home/agent/.gradle",
    "bun": "/home/agent/.bun/install/cache",
}


class DockerManager:
    def __init__(self, config: TaskContainerSpec) -> None:
        self.config = config

    @property
    def container_name(self) -> str:
        return f"harness-task-{self.config.task_id}"

    def ensure_container(self) -> None:
        if self._container_exists():
            self._start_container()
            return
        self._create_container()
        self._start_container()

    def exec(self, command: List[str], workdir: Optional[str] = None) -> subprocess.CompletedProcess:
        cmd = ["docker", "exec"]
        if workdir:
            cmd += ["-w", workdir]
        cmd.append(self.container_name)
        cmd.extend(command)
        return subprocess.run(cmd, check=False, capture_output=True, text=True)

    def _container_exists(self) -> bool:
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name=^{self.container_name}$", "--format", "{{.ID}}"],
            check=False,
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())

    def _create_container(self) -> None:
        mounts = self._build_mounts()
        cmd = [
            "docker",
            "create",
            "--name",
            self.container_name,
            "--label",
            f"harness.task_id={self.config.task_id}",
            "--workdir",
            self.config.docker.workdir_in_container,
            "--network",
            self.config.docker.network_mode,
            "--cpus",
            self.config.docker.cpus,
            "--memory",
            self.config.docker.memory,
        ]
        for mount in mounts:
            cmd += ["-v", mount]
        env_vars = self.config.auth.codex_env
        for key, value in env_vars.items():
            cmd += ["-e", f"{key}={value}"]
        cmd.append(self.config.docker.image)
        cmd.extend(["sleep", "infinity"])
        subprocess.run(cmd, check=True)

    def _start_container(self) -> None:
        subprocess.run(["docker", "start", self.container_name], check=True)

    def _build_mounts(self) -> Iterable[str]:
        mounts = [
            f"{self.config.workspace_dir}:/workspace",
            f"{self.config.bus_dir}:/harness-bus",
        ]
        if self.config.auth.codex_host_dir.exists():
            mounts.append(f"{self.config.auth.codex_host_dir}:/home/agent/.codex")
        if self.config.auth.claude_host_dir.exists():
            mounts.append(f"{self.config.auth.claude_host_dir}:/home/agent")
        if self.config.caches.enabled:
            mounts.extend(self._cache_mounts())
        return mounts

    def _cache_mounts(self) -> Iterable[str]:
        mounts: List[str] = []
        for key, host_path in self.config.caches.mounts.items():
            if key == "cargo":
                registry = host_path / "registry"
                git = host_path / "git"
                mounts.append(f"{registry}:{CACHE_MOUNT_TARGETS['cargo_registry']}")
                mounts.append(f"{git}:{CACHE_MOUNT_TARGETS['cargo_git']}")
                continue
            if key not in CACHE_MOUNT_TARGETS:
                continue
            mounts.append(f"{host_path}:{CACHE_MOUNT_TARGETS[key]}")
        return mounts


def parse_config(payload: Dict[str, object]) -> Dict[str, object]:
    return payload


def build_task_spec(root: Path, task_id: str, payload: Dict[str, object]) -> TaskContainerSpec:
    docker_payload = payload.get("docker", {})
    auth_payload = payload.get("auth", {})
    caches_payload = payload.get("caches", {})

    docker = DockerConfig(
        image=docker_payload.get("image", "harness-agent:latest"),
        workdir_in_container=docker_payload.get("workdir_in_container", "/workspace"),
        network_mode=docker_payload.get("network_mode", "bridge"),
        cpus=str(docker_payload.get("cpus", "2")),
        memory=str(docker_payload.get("memory", "6g")),
    )

    codex_payload = auth_payload.get("codex", {})
    claude_payload = auth_payload.get("claude", {})
    auth = AuthConfig(
        codex_host_dir=root / codex_payload.get("host_dir", ".harness/auth/codex"),
        claude_host_dir=root / claude_payload.get("host_dir", ".harness/auth/claude"),
        codex_env=codex_payload.get("env", {}) or {},
    )

    cache_mounts: Dict[str, Path] = {}
    cache_payload = caches_payload.get("mounts", {}) if isinstance(caches_payload, dict) else {}
    for key, value in cache_payload.items():
        cache_mounts[key] = root / str(value)

    caches = CacheConfig(
        enabled=bool(caches_payload.get("enabled", True)) if isinstance(caches_payload, dict) else True,
        mounts=cache_mounts,
    )

    workspace_dir = root / ".harness" / "workspaces" / task_id / "repo"
    bus_dir = root / ".harness" / "bus"

    return TaskContainerSpec(
        task_id=task_id,
        workspace_dir=workspace_dir,
        bus_dir=bus_dir,
        docker=docker,
        auth=auth,
        caches=caches,
    )
