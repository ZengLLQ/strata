"""Unit tests for DockerEnvironmentManager."""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any
import pytest

from strata.adapters.docker import DockerEnvironmentManager
from strata.core.errors import (
    DestructiveActionRefusalError,
    EnvironmentSetupError,
    FaultApplicationError,
)


class MockCommandRunner:
    """Mock command runner recording commands and returning configurable results."""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.history: list[tuple[list[str], float]] = []

    def __call__(self, cmd: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        self.history.append((cmd, timeout))
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=self.returncode,
            stdout=self.stdout,
            stderr=self.stderr,
        )


def test_docker_available_check() -> None:
    # 1. Success case
    success_runner = MockCommandRunner(returncode=0, stdout="24.0.5")
    mgr = DockerEnvironmentManager(command_runner=success_runner)
    assert mgr.is_docker_available() is True
    assert success_runner.history[0][0] == ["docker", "version", "--format", "{{.Client.Version}}"]

    # 2. Failure case
    fail_runner = MockCommandRunner(returncode=1, stderr="daemon not running")
    mgr_fail = DockerEnvironmentManager(command_runner=fail_runner)
    assert mgr_fail.is_docker_available() is False


def test_docker_metadata_collection() -> None:
    runner = MockCommandRunner(returncode=0, stdout="24.0.5")
    mgr = DockerEnvironmentManager(command_runner=runner)
    meta = mgr.get_docker_metadata()
    assert meta["docker_available"] is True
    assert "client_version" in meta


def test_compose_up_and_down(tmp_path: Path) -> None:
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("version: '3.8'\nservices:\n  app:\n    image: nginx\n")

    runner = MockCommandRunner(returncode=0)
    mgr = DockerEnvironmentManager(command_runner=runner)

    # compose_up
    mgr.compose_up(compose_file)
    assert runner.history[-1][0] == ["docker", "compose", "-f", str(compose_file), "up", "-d"]

    # compose_down
    mgr.compose_down(compose_file)
    assert runner.history[-1][0] == ["docker", "compose", "-f", str(compose_file), "down"]


def test_compose_up_missing_file_raises_error() -> None:
    mgr = DockerEnvironmentManager()
    with pytest.raises(EnvironmentSetupError) as exc_info:
        mgr.compose_up(Path("/nonexistent/docker-compose.yml"))
    assert "file not found" in str(exc_info.value).lower()


def test_container_lifecycle_faults() -> None:
    runner = MockCommandRunner(returncode=0)
    mgr = DockerEnvironmentManager(command_runner=runner)

    mgr.pause_container("cluster-node-2")
    assert runner.history[-1][0] == ["docker", "pause", "cluster-node-2"]

    mgr.unpause_container("cluster-node-2")
    assert runner.history[-1][0] == ["docker", "unpause", "cluster-node-2"]

    mgr.restart_container("cluster-node-2")
    assert runner.history[-1][0] == ["docker", "restart", "-t", "5", "cluster-node-2"]


def test_network_partition_faults() -> None:
    runner = MockCommandRunner(returncode=0)
    mgr = DockerEnvironmentManager(command_runner=runner)

    mgr.disconnect_network("cluster-node-1", "strata-net")
    assert runner.history[-1][0] == ["docker", "network", "disconnect", "strata-net", "cluster-node-1"]

    mgr.connect_network("cluster-node-1", "strata-net")
    assert runner.history[-1][0] == ["docker", "network", "connect", "strata-net", "cluster-node-1"]


def test_destructive_operations_refusal_by_default() -> None:
    runner = MockCommandRunner(returncode=0)
    safe_mgr = DockerEnvironmentManager(allow_destructive=False, command_runner=runner)

    # 1. kill_container refusal
    with pytest.raises(DestructiveActionRefusalError):
        safe_mgr.kill_container("cluster-node-1")

    # 2. compose_down with volumes refusal
    with pytest.raises(DestructiveActionRefusalError):
        safe_mgr.compose_down("docker-compose.yml", remove_volumes=True)


def test_destructive_operations_allowed_when_configured() -> None:
    runner = MockCommandRunner(returncode=0)
    auth_mgr = DockerEnvironmentManager(allow_destructive=True, command_runner=runner)

    auth_mgr.kill_container("cluster-node-1")
    assert runner.history[-1][0] == ["docker", "kill", "cluster-node-1"]

    auth_mgr.compose_down("docker-compose.yml", remove_volumes=True)
    assert runner.history[-1][0] == ["docker", "compose", "-f", "docker-compose.yml", "down", "-v"]


def test_context_manager_cleanup(tmp_path: Path) -> None:
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("version: '3.8'\nservices:\n  test:\n    image: alpine\n")

    runner = MockCommandRunner(returncode=0)
    with DockerEnvironmentManager(command_runner=runner) as mgr:
        mgr.compose_up(compose_file)

    # Check that compose_down was called during exit
    assert any("down" in cmd[0] for cmd in runner.history)
