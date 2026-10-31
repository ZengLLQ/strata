"""Experiment run manifest generation and cryptographic checksum verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from strata.core.errors import ArtifactIntegrityError


def compute_sha256(path: Path | str) -> str:
    """Compute SHA-256 digest of a file in streaming chunks."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Cannot compute hash of non-existent file: {path}")

    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class RunManifest:
    """Manifest recording experiment run metadata and artifact checksums."""

    def __init__(
        self,
        run_id: str,
        experiment_id: str,
        seed: int,
        engine_version: str = "0.1.0",
        artifacts: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.run_id = run_id
        self.experiment_id = experiment_id
        self.seed = seed
        self.engine_version = engine_version
        self.artifacts: dict[str, str] = artifacts or {}  # filename -> sha256
        self.metadata: dict[str, Any] = metadata or {}

    def add_artifact(self, filename: str, file_path: Path | str) -> None:
        """Hash and record an artifact file."""
        self.artifacts[filename] = compute_sha256(file_path)

    def write_to(self, output_path: Path | str) -> None:
        """Write manifest JSON to disk."""
        data = {
            "run_id": self.run_id,
            "experiment_id": self.experiment_id,
            "seed": self.seed,
            "engine_version": self.engine_version,
            "artifacts": self.artifacts,
            "metadata": self.metadata,
        }
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load_from(cls, manifest_path: Path | str) -> RunManifest:
        """Load manifest from disk."""
        path = Path(manifest_path)
        if not path.exists():
            raise FileNotFoundError(f"Manifest not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)

        return cls(
            run_id=d["run_id"],
            experiment_id=d["experiment_id"],
            seed=d["seed"],
            engine_version=d.get("engine_version", "0.1.0"),
            artifacts=d.get("artifacts", {}),
            metadata=d.get("metadata", {}),
        )

    def verify_directory(self, root_dir: Path | str) -> dict[str, bool]:
        """Verify that all recorded artifacts exist and match their SHA-256 checksums."""
        root = Path(root_dir)
        results: dict[str, bool] = {}

        for filename, expected_hash in self.artifacts.items():
            target_path = root / filename
            if not target_path.exists():
                raise ArtifactIntegrityError(f"Missing artifact file: {filename}")
            actual_hash = compute_sha256(target_path)
            if actual_hash != expected_hash:
                raise ArtifactIntegrityError(
                    f"Checksum mismatch for '{filename}': expected {expected_hash}, got {actual_hash}"
                )
            results[filename] = True

        return results
