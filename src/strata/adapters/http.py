"""HTTP Service Adapter for integration testing against real external HTTP services."""

from __future__ import annotations

import json
import time
from typing import Any, Mapping, Sequence
import urllib.error
import urllib.request

from strata.adapters.base import BaseServiceAdapter
from strata.core.contracts import EventContract
from strata.core.errors import (
    EnvironmentSetupError,
    FaultApplicationError,
    HealthCheckFailedError,
)
from strata.core.types import EventPriority
from strata.simulation.events import FaultAppliedEvent, WorkloadOperationEvent


class HttpServiceAdapter(BaseServiceAdapter):
    """Adapter connecting Strata to live HTTP microservices and REST clusters.
    
    Translates abstract workloads and faults into real HTTP/REST requests,
    measuring physical round-trip latencies, capturing HTTP response codes,
    and observing external failure behavior without simulated abstractions.
    """

    def __init__(
        self,
        endpoints: Mapping[str, str],
        allow_destructive: bool = False,
        default_timeout_seconds: float = 5.0,
        health_path: str = "/health",
        kv_path: str = "/kv",
        admin_path: str = "/admin",
    ) -> None:
        super().__init__(allow_destructive=allow_destructive)
        self.endpoints: dict[str, str] = dict(endpoints)
        self.default_timeout_seconds = default_timeout_seconds
        self.health_path = health_path
        self.kv_path = kv_path
        self.admin_path = admin_path
        self._sequence_counter = 0

    @property
    def adapter_name(self) -> str:
        return "http"

    def _next_sequence_id(self) -> int:
        self._sequence_counter += 1
        return self._sequence_counter

    def _make_request(
        self,
        method: str,
        url: str,
        data: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> tuple[int, Any]:
        """Perform an HTTP request using standard library urllib."""
        timeout_val = timeout or self.default_timeout_seconds
        req_data = None
        headers = {
            "User-Agent": "Strata-Integration-Harness/0.1.0",
            "Accept": "application/json",
        }
        if data is not None:
            req_data = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout_val) as resp:
                status = resp.status
                raw_body = resp.read().decode("utf-8")
                try:
                    parsed_body = json.loads(raw_body) if raw_body else {}
                except json.JSONDecodeError:
                    parsed_body = {"raw": raw_body}
                return status, parsed_body
        except urllib.error.HTTPError as err:
            raw_body = err.read().decode("utf-8")
            try:
                parsed_body = json.loads(raw_body) if raw_body else {}
            except json.JSONDecodeError:
                parsed_body = {"raw": raw_body}
            return err.code, parsed_body
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return 0, {"error": str(exc)}

    def setup(self, timeout_seconds: float = 30.0) -> None:
        """Verify that all configured node endpoints are reachable."""
        if not self.endpoints:
            raise EnvironmentSetupError("HttpServiceAdapter requires at least one configured node endpoint.")

        start_time = time.monotonic()
        last_error = None

        while time.monotonic() - start_time < timeout_seconds:
            all_up = True
            for node_id, base_url in self.endpoints.items():
                health_url = f"{base_url.rstrip('/')}{self.health_path}"
                status, body = self._make_request("GET", health_url, timeout=3.0)
                if status != 200:
                    all_up = False
                    last_error = f"Node '{node_id}' at {health_url} returned status {status}: {body}"
                    break
            if all_up:
                return
            time.sleep(0.5)

        raise EnvironmentSetupError(
            f"HTTP cluster environment setup timed out after {timeout_seconds}s. Last error: {last_error}"
        )

    def health_check(self, timeout_seconds: float = 5.0) -> bool:
        """Probe all node health endpoints."""
        for node_id, base_url in self.endpoints.items():
            health_url = f"{base_url.rstrip('/')}{self.health_path}"
            status, _ = self._make_request("GET", health_url, timeout=timeout_seconds)
            if status != 200:
                return False
        return True

    def execute_workload(
        self,
        workload_config: Any,
        start_time_ns: int,
    ) -> Sequence[EventContract]:
        """Execute simulated KV operations against real HTTP endpoints."""
        events: list[EventContract] = []
        target_nodes = getattr(workload_config, "target_nodes", None) or list(self.endpoints.keys())
        operations_count = getattr(workload_config, "operations_count", 10)
        key_space_size = getattr(workload_config, "key_space_size", 5)
        arrival_interval_us = getattr(workload_config, "arrival_interval_us", 0)

        for i in range(operations_count):
            target_node = target_nodes[i % len(target_nodes)]
            base_url = self.endpoints.get(target_node)
            if not base_url:
                continue

            key = f"key_{i % key_space_size}"
            value = f"val_{i}_{time.time_ns() % 100000}"
            op_type = "put" if i % 2 == 0 else "get"

            t0 = time.time_ns()
            timestamp_us = (t0 - start_time_ns) // 1000

            if op_type == "put":
                req_url = f"{base_url.rstrip('/')}{self.kv_path}/{key}"
                status_code, resp_body = self._make_request("PUT", req_url, data={"value": value})
            else:
                req_url = f"{base_url.rstrip('/')}{self.kv_path}/{key}"
                status_code, resp_body = self._make_request("GET", req_url)
                if isinstance(resp_body, dict) and "value" in resp_body:
                    value = resp_body["value"]

            t1 = time.time_ns()
            latency_us = (t1 - t0) // 1000

            op_event = WorkloadOperationEvent.create(
                sequence_id=self._next_sequence_id(),
                timestamp_us=timestamp_us,
                target_node=target_node,
                operation_id=f"op_{i}",
                op_type=op_type,
                key=key,
                value=value,
                extra={
                    "latency_us": latency_us,
                    "http_status": status_code,
                    "success": 200 <= status_code < 300,
                    "response": resp_body,
                },
            )
            events.append(op_event)

            if arrival_interval_us > 0:
                sleep_s = arrival_interval_us / 1_000_000.0
                time.sleep(min(sleep_s, 0.5))

        return events

    def inject_fault(
        self,
        fault_config: Any,
        now_ns: int,
    ) -> EventContract:
        """Inject a fault into external HTTP service nodes."""
        fault_id = getattr(fault_config, "id", "fault_0")
        fault_type = getattr(fault_config, "fault_type", "unknown")
        target = getattr(fault_config, "target", "")
        parameters = getattr(fault_config, "parameters", {})

        is_destructive = parameters.get("destructive", False)
        if is_destructive or fault_type in ("process_kill", "hard_reboot"):
            self.verify_destructive_allowed(f"{fault_type} on {target}")

        evidence: dict[str, Any] = {"applied_at_ns": now_ns}

        if fault_type in ("node_crash", "node_restart"):
            base_url = self.endpoints.get(target)
            if not base_url:
                raise FaultApplicationError(f"Target node '{target}' not found in HTTP endpoints.")
            sub_path = "crash" if fault_type == "node_crash" else "restart"
            admin_url = f"{base_url.rstrip('/')}{self.admin_path}/fault/{sub_path}"
            status, body = self._make_request("POST", admin_url, data={"fault_id": fault_id, **parameters})
            evidence["http_status"] = status
            evidence["response"] = body
        elif fault_type in ("network_partition", "network_heal"):
            # Multi-node partition: send isolation rules to all nodes in group_a
            group_a = parameters.get("group_a", [target] if target else [])
            group_b = parameters.get("group_b", [])
            sub_path = "partition" if fault_type == "network_partition" else "heal"

            for node in group_a:
                node_url = self.endpoints.get(node)
                if node_url:
                    admin_url = f"{node_url.rstrip('/')}{self.admin_path}/fault/{sub_path}"
                    status, body = self._make_request("POST", admin_url, data={"isolate_from": group_b})
                    evidence[f"node_{node}_status"] = status
        elif fault_type == "message_delay":
            base_url = self.endpoints.get(target)
            if base_url:
                admin_url = f"{base_url.rstrip('/')}{self.admin_path}/fault/delay"
                status, body = self._make_request("POST", admin_url, data=parameters)
                evidence["http_status"] = status
                evidence["response"] = body
        else:
            # Custom fault hook
            base_url = self.endpoints.get(target)
            if base_url:
                admin_url = f"{base_url.rstrip('/')}{self.admin_path}/fault/{fault_type}"
                status, body = self._make_request("POST", admin_url, data=parameters)
                evidence["http_status"] = status
                evidence["response"] = body
            else:
                evidence["warning"] = f"No endpoint for target '{target}'; fault dispatched as no-op"

        return FaultAppliedEvent.create(
            sequence_id=self._next_sequence_id(),
            timestamp_us=(now_ns) // 1000,
            fault_id=fault_id,
            fault_type=fault_type,
            target=target,
            evidence=evidence,
        )

    def collect_results(self) -> dict[str, Any]:
        """Fetch final key-value state from all live nodes."""
        node_states: dict[str, dict[str, Any]] = {}
        for node_id, base_url in self.endpoints.items():
            state_url = f"{base_url.rstrip('/')}{self.kv_path}"
            status, body = self._make_request("GET", state_url)
            if status == 200 and isinstance(body, dict):
                node_states[node_id] = body
            else:
                node_states[node_id] = {}
        return {"node_states": node_states}

    def teardown(self) -> None:
        """Reset external nodes and remove active faults."""
        for node_id, base_url in self.endpoints.items():
            reset_url = f"{base_url.rstrip('/')}{self.admin_path}/reset"
            self._make_request("POST", reset_url, timeout=2.0)
