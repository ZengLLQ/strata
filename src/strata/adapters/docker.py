"""Docker Environment Manager for local containerized integration testing."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from typing import Any, Callable

from strata.core.errors import (
    DestructiveActionRefusalError,
    EnvironmentSetupError,
    FaultApplicationError,
)


class DockerEnvironmentManager:
    """Manages local container cluster lifecycle and failure injection via Docker.
    
    Provides isolated multi-container topologies for testing real distributed
    services without external cloud dependencies or complex orchestrators.
    All destructive actions (e.g. killing containers, volume deletion) are disabled
    by default and require explicit authorization.
    """

    def __init__(
        self,
        allow_destructive: bool = False,
        command_runner: Callable[[list[str], float], subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        self.allow_destructive = allow_destructive
        self._runner = command_runner or self._default_runner
        self._active_compose_files: list[Path] = []

    @staticmethod
    def _default_runner(cmd: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def is_docker_available(self) -> bool:
        """Check if Docker CLI is installed and responsive on the host."""
        if shutil.which("docker") is None:
            return False
        try:
            res = self._runner(["docker", "version", "--format", "{{.Client.Version}}"], 5.0)
            return res.returncode == 0
        except Exception:
            return False

    def verify_destructive_allowed(self, action_name: str) -> None:
        """Enforce strict safety guardrails for destructive container operations."""
        if not self.allow_destructive:
            raise DestructiveActionRefusalError(
                f"Destructive Docker operation '{action_name}' refused: "
                "destructive actions are disabled by default. "
                "Set 'allow_destructive: true' in execution configuration to authorize."
            )

    def compose_up(self, compose_file: Path | str, timeout_seconds: float = 60.0) -> None:
        """Start a multi-container cluster using Docker Compose."""
        path = Path(compose_file)
        if not path.exists():
            raise EnvironmentSetupError(f"Docker Compose file not found at: {path}")

        cmd = ["docker", "compose", "-f", str(path), "up", "-d"]
        try:
            res = self._runner(cmd, timeout_seconds)
            if res.returncode != 0:
                raise EnvironmentSetupError(
                    f"Docker Compose up failed (code {res.returncode}): {res.stderr or res.stdout}"
                )
            if path not in self._active_compose_files:
                self._active_compose_files.append(path)
        except subprocess.TimeoutExpired as exc:
            raise EnvironmentSetupError(f"Docker Compose up timed out after {timeout_seconds}s") from exc

    def compose_down(
        self,
        compose_file: Path | str,
        timeout_seconds: float = 30.0,
        remove_volumes: bool = False,
    ) -> None:
        """Stop and remove containers defined in Docker Compose."""
        path = Path(compose_file)
        if remove_volumes:
            self.verify_destructive_allowed("compose_down with volume removal")

        cmd = ["docker", "compose", "-f", str(path), "down"]
        if remove_volumes:
            cmd.append("-v")

        try:
            res = self._runner(cmd, timeout_seconds)
            if res.returncode != 0:
                # Log or warn, but do not necessarily raise during cleanup
                pass
            if path in self._active_compose_files:
                self._active_compose_files.remove(path)
        except Exception:
            pass

    def pause_container(self, container_name: str, timeout_seconds: float = 10.0) -> None:
        """Pause execution of a container (simulating process freeze / hang)."""
        cmd = ["docker", "pause", container_name]
        res = self._runner(cmd, timeout_seconds)
        if res.returncode != 0:
            raise FaultApplicationError(
                f"Failed to pause container '{container_name}': {res.stderr or res.stdout}"
            )

    def unpause_container(self, container_name: str, timeout_seconds: float = 10.0) -> None:
        """Unpause execution of a previously paused container."""
        cmd = ["docker", "unpause", container_name]
        res = self._runner(cmd, timeout_seconds)
        if res.returncode != 0:
            raise FaultApplicationError(
                f"Failed to unpause container '{container_name}': {res.stderr or res.stdout}"
            )

    def restart_container(self, container_name: str, timeout_seconds: float = 15.0) -> None:
        """Restart a container (simulating crash and recovery)."""
        cmd = ["docker", "restart", "-t", "5", container_name]
        res = self._runner(cmd, timeout_seconds)
        if res.returncode != 0:
            raise FaultApplicationError(
                f"Failed to restart container '{container_name}': {res.stderr or res.stdout}"
            )

    def kill_container(self, container_name: str, timeout_seconds: float = 5.0) -> None:
        """Forcefully kill a container process (destructive)."""
        self.verify_destructive_allowed(f"kill_container({container_name})")
        cmd = ["docker", "kill", container_name]
        res = self._runner(cmd, timeout_seconds)
        if res.returncode != 0:
            raise FaultApplicationError(
                f"Failed to kill container '{container_name}': {res.stderr or res.stdout}"
            )

    def disconnect_network(
        self,
        container_name: str,
        network_name: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        """Disconnect container from a Docker network (simulating network partition)."""
        cmd = ["docker", "network", "disconnect", network_name, container_name]
        res = self._runner(cmd, timeout_seconds)
        if res.returncode != 0:
            raise FaultApplicationError(
                f"Failed to disconnect container '{container_name}' from network '{network_name}': {res.stderr or res.stdout}"
            )

    def connect_network(
        self,
        container_name: str,
        network_name: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        """Reconnect container to a Docker network (simulating partition heal)."""
        cmd = ["docker", "network", "connect", network_name, container_name]
        res = self._runner(cmd, timeout_seconds)
        if res.returncode != 0:
            raise FaultApplicationError(
                f"Failed to connect container '{container_name}' to network '{network_name}': {res.stderr or res.stdout}"
            )

    def get_container_status(self, container_name: str) -> str:
        """Query the runtime state (running, paused, exited, etc.) of a container."""
        cmd = ["docker", "inspect", "--format", "{{.State.Status}}", container_name]
        res = self._runner(cmd, 5.0)
        if res.returncode == 0:
            return res.stdout.strip()
        return "unknown"

    def get_docker_metadata(self) -> dict[str, Any]:
        """Collect Docker runtime and version information."""
        meta: dict[str, Any] = {"docker_available": False}
        if not self.is_docker_available():
            return meta

        meta["docker_available"] = True
        try:
            ver = self._runner(["docker", "version", "--format", "{{.Client.Version}}"], 5.0)
            if ver.returncode == 0:
                meta["client_version"] = ver.stdout.strip()
            compose_ver = self._runner(["docker", "compose", "version", "--short"], 5.0)
            if compose_ver.returncode == 0:
                meta["compose_version"] = compose_ver.stdout.strip()
        except Exception:
            pass
        return meta

    def cleanup_all(self) -> None:
        """Tear down all active Compose environments."""
        for compose_file in list(self._active_compose_files):
            self.compose_down(compose_file, remove_volumes=False)

    def __enter__(self) -> DockerEnvironmentManager:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.cleanup_all()
