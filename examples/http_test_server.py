"""Lightweight local HTTP test server simulating a 3-node distributed key-value cluster.

Can be run standalone or spawned in background threads for Strata integration tests.
Implements /health, /kv/<key>, /admin/fault/*, and /admin/reset endpoints.
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
from typing import Any
import urllib.parse


class ClusterNodeHandler(BaseHTTPRequestHandler):
    """HTTP handler implementing KV storage and chaos endpoints for a cluster node."""

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress standard HTTP server request logging."""
        pass

    @property
    def server_node(self) -> ClusterNodeServer:
        return self.server  # type: ignore

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # If crashed, fail immediately with 503 Service Unavailable
        if self.server_node.is_crashed:
            self._send_json(503, {"error": "node is crashed", "state": "offline"})
            return

        # Simulated artificial delay
        if self.server_node.delay_ms > 0:
            time.sleep(self.server_node.delay_ms / 1000.0)

        if path == "/health":
            self._send_json(200, {"status": "healthy", "node_id": self.server_node.node_id})
        elif path.startswith("/kv/"):
            key = path[4:]
            with self.server_node.lock:
                val = self.server_node.store.get(key)
            if val is not None:
                self._send_json(200, {"key": key, "value": val})
            else:
                self._send_json(404, {"error": f"Key '{key}' not found"})
        elif path == "/kv" or path == "/admin/state":
            with self.server_node.lock:
                snapshot = dict(self.server_node.store)
            self._send_json(200, snapshot)
        else:
            self._send_json(404, {"error": f"Not found: {path}"})

    def do_PUT(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if self.server_node.is_crashed:
            self._send_json(503, {"error": "node is crashed", "state": "offline"})
            return

        if self.server_node.delay_ms > 0:
            time.sleep(self.server_node.delay_ms / 1000.0)

        if path.startswith("/kv/"):
            key = path[4:]
            data = self._read_json()
            val = data.get("value")
            with self.server_node.lock:
                self.server_node.store[key] = val
                # Replicate to peers if not partitioned
                self.server_node.replicate_to_peers(key, val)
            self._send_json(200, {"key": key, "value": val, "status": "committed"})
        else:
            self._send_json(404, {"error": f"Cannot PUT to: {path}"})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_json()

        if path == "/admin/fault/crash":
            self.server_node.is_crashed = True
            self._send_json(200, {"status": "applied", "fault": "crash", "node_id": self.server_node.node_id})
        elif path == "/admin/fault/restart":
            self.server_node.is_crashed = False
            self._send_json(200, {"status": "applied", "fault": "restart", "node_id": self.server_node.node_id})
        elif path == "/admin/fault/delay":
            self.server_node.delay_ms = int(body.get("delay_ms", 50))
            self._send_json(200, {"status": "applied", "fault": "delay", "delay_ms": self.server_node.delay_ms})
        elif path == "/admin/fault/partition":
            isolate_from = body.get("isolate_from", [])
            with self.server_node.lock:
                self.server_node.isolated_peers = set(isolate_from)
            self._send_json(200, {"status": "applied", "fault": "partition", "isolated_from": list(self.server_node.isolated_peers)})
        elif path == "/admin/fault/heal":
            with self.server_node.lock:
                self.server_node.isolated_peers.clear()
            self._send_json(200, {"status": "applied", "fault": "heal"})
        elif path == "/admin/reset":
            with self.server_node.lock:
                self.server_node.store.clear()
                self.server_node.is_crashed = False
                self.server_node.delay_ms = 0
                self.server_node.isolated_peers.clear()
            self._send_json(200, {"status": "reset_complete", "node_id": self.server_node.node_id})
        elif path.startswith("/internal/replicate"):
            # Internal peer replication endpoint
            if self.server_node.is_crashed:
                self._send_json(503, {"error": "crashed"})
                return
            sender = body.get("sender")
            if sender in self.server_node.isolated_peers:
                self._send_json(403, {"error": "partitioned"})
                return
            key = body.get("key")
            val = body.get("value")
            with self.server_node.lock:
                self.server_node.store[key] = val
            self._send_json(200, {"status": "replicated"})
        else:
            self._send_json(404, {"error": f"Unknown POST path: {path}"})


class ClusterNodeServer(ThreadingHTTPServer):
    """Threading HTTP Server representing a single distributed node."""

    def __init__(
        self,
        node_id: str,
        host: str,
        port: int,
        peers: dict[str, str] | None = None,
    ) -> None:
        super().__init__((host, port), ClusterNodeHandler)
        self.node_id = node_id
        self.host = host
        self.port = port
        self.peers: dict[str, str] = peers or {}
        self.store: dict[str, Any] = {}
        self.lock = threading.Lock()
        self.is_crashed = False
        self.delay_ms = 0
        self.isolated_peers: set[str] = set()

    def replicate_to_peers(self, key: str, value: Any) -> None:
        """Propagate write to peers asynchronously."""
        for peer_id, peer_url in list(self.peers.items()):
            if peer_id in self.isolated_peers:
                continue
            t = threading.Thread(
                target=self._send_replicate,
                args=(peer_url, key, value),
                daemon=True,
            )
            t.start()

    def _send_replicate(self, peer_url: str, key: str, value: Any) -> None:
        try:
            import urllib.request
            req_data = json.dumps({"sender": self.node_id, "key": key, "value": value}).encode("utf-8")
            req = urllib.request.Request(
                f"{peer_url.rstrip('/')}/internal/replicate",
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=1.0) as _:
                pass
        except Exception:
            pass


class TestHttpCluster:
    """Manager to spawn, wire, and tear down an in-process 3-node HTTP test cluster."""

    def __init__(self, base_port: int = 18000) -> None:
        self.base_port = base_port
        self.servers: dict[str, ClusterNodeServer] = {}
        self.threads: list[threading.Thread] = []

    def start(self) -> dict[str, str]:
        """Start 3 nodes and wire peer URLs."""
        endpoints = {
            f"node-{i}": f"http://127.0.0.1:{self.base_port + i}"
            for i in range(1, 4)
        }

        for i in range(1, 4):
            node_id = f"node-{i}"
            port = self.base_port + i
            peers = {nid: url for nid, url in endpoints.items() if nid != node_id}
            srv = ClusterNodeServer(node_id, "127.0.0.1", port, peers=peers)
            self.servers[node_id] = srv
            th = threading.Thread(target=srv.serve_forever, daemon=True)
            th.start()
            self.threads.append(th)

        # Allow servers to bind and start listening
        time.sleep(0.1)
        return endpoints

    def stop(self) -> None:
        """Shut down all cluster nodes."""
        for srv in self.servers.values():
            srv.shutdown()
            srv.server_close()
        for th in self.threads:
            th.join(timeout=1.0)
        self.servers.clear()
        self.threads.clear()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start 3-node test HTTP cluster")
    parser.add_argument("--port", type=int, default=18000, help="Base port number")
    args = parser.parse_args()

    cluster = TestHttpCluster(base_port=args.port)
    endpoints = cluster.start()
    print("Test HTTP Cluster running at:")
    for nid, ep in endpoints.items():
        print(f"  {nid}: {ep}")
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping cluster...")
        cluster.stop()
        print("Cluster stopped.")
