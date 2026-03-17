"""Tests for backend.utils.safe_json -- atomic writes and dual-locking."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from backend.utils.safe_json import atomic_write, locked_json_read_write


class TestAtomicWrite:
    """Verify atomic_write produces valid JSON files."""

    def test_creates_file(self, tmp_path: Path) -> None:
        target = tmp_path / "out.json"
        atomic_write(target, {"key": "value"})
        assert target.exists()
        assert json.loads(target.read_text()) == {"key": "value"}

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        target = tmp_path / "out.json"
        atomic_write(target, {"a": 1})
        atomic_write(target, {"b": 2})
        assert json.loads(target.read_text()) == {"b": 2}

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        target = tmp_path / "sub" / "dir" / "out.json"
        atomic_write(target, [1, 2, 3])
        assert json.loads(target.read_text()) == [1, 2, 3]

    def test_no_temp_file_left_on_success(self, tmp_path: Path) -> None:
        target = tmp_path / "out.json"
        atomic_write(target, {"ok": True})
        assert not target.with_suffix(".tmp").exists()


class TestLockedJsonReadWrite:
    """Verify locked_json_read_write provides correct read-modify-write."""

    def test_creates_file_from_none(self, tmp_path: Path) -> None:
        target = tmp_path / "new.json"

        def init(data):
            assert data is None
            return {"count": 0}

        result = locked_json_read_write(target, init)
        assert result == {"count": 0}
        assert json.loads(target.read_text()) == {"count": 0}

    def test_reads_existing_data(self, tmp_path: Path) -> None:
        target = tmp_path / "existing.json"
        target.write_text(json.dumps({"items": [1, 2]}))

        def add_item(data):
            data["items"].append(3)
            return data

        result = locked_json_read_write(target, add_item)
        assert result == {"items": [1, 2, 3]}

    def test_transform_error_does_not_corrupt(self, tmp_path: Path) -> None:
        target = tmp_path / "safe.json"
        target.write_text(json.dumps({"original": True}))

        def bad_transform(data):
            raise ValueError("intentional failure")

        with pytest.raises(ValueError, match="intentional failure"):
            locked_json_read_write(target, bad_transform)

        # Original data must still be intact
        assert json.loads(target.read_text()) == {"original": True}


class TestConcurrency:
    """Verify that concurrent access via locked_json_read_write is safe."""

    def test_concurrent_increments(self, tmp_path: Path) -> None:
        """Launch 100 threads each incrementing a counter — no lost updates."""
        target = tmp_path / "counter.json"
        target.write_text(json.dumps({"count": 0}))

        num_threads = 100
        errors: list[str] = []

        def increment() -> None:
            try:
                def _inc(data):
                    data["count"] += 1
                    return data

                locked_json_read_write(target, _inc)
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=increment) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent increments: {errors}"

        final = json.loads(target.read_text())
        assert final["count"] == num_threads, (
            f"Expected count={num_threads}, got {final['count']} — lost updates detected"
        )

    def test_concurrent_project_creates_no_data_loss(self, tmp_path: Path) -> None:
        """Simulate 50+ concurrent project-create operations.

        Each thread adds a unique project entry to a shared registry JSON.
        After all threads complete:
        - All projects must be present (no data loss)
        - The JSON must be valid (no truncation)
        - No exceptions raised
        """
        target = tmp_path / "projects.json"
        target.write_text(json.dumps({}))

        num_projects = 60
        errors: list[str] = []

        def create_project(idx: int) -> None:
            try:
                project_id = f"proj-{idx:04d}"

                def _add(data):
                    if data is None:
                        data = {}
                    data[project_id] = {
                        "id": project_id,
                        "name": f"Project {idx}",
                        "directory": f"/tmp/proj_{idx}",
                    }
                    return data

                locked_json_read_write(target, _add)
            except Exception as exc:
                errors.append(f"Thread {idx}: {exc}")

        threads = [
            threading.Thread(target=create_project, args=(i,))
            for i in range(num_projects)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No exceptions
        assert not errors, f"Errors during concurrent creates: {errors}"

        # Valid JSON (no truncation)
        raw = target.read_text()
        registry = json.loads(raw)

        # All projects present
        assert len(registry) == num_projects, (
            f"Expected {num_projects} projects, got {len(registry)} — data loss detected"
        )
        for i in range(num_projects):
            project_id = f"proj-{i:04d}"
            assert project_id in registry, f"Missing project {project_id}"
