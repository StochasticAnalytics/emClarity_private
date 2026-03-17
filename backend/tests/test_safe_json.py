"""Tests for backend.utils.safe_json -- atomic writes and dual-locking."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from backend.utils.safe_json import (
    atomic_write,
    atomic_write_text,
    locked_json_read,
    locked_json_read_write,
)


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


# ---------------------------------------------------------------------------
# atomic_write_text
# ---------------------------------------------------------------------------


class TestAtomicWriteText:
    """Verify atomic_write_text writes text atomically with UTF-8 encoding."""

    def test_writes_content(self, tmp_path: Path) -> None:
        target = tmp_path / "out.txt"
        atomic_write_text(target, "hello world")
        assert target.read_text(encoding="utf-8") == "hello world"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "deep.txt"
        atomic_write_text(target, "nested")
        assert target.read_text(encoding="utf-8") == "nested"

    def test_utf8_encoding(self, tmp_path: Path) -> None:
        """Content with non-ASCII characters must be written as UTF-8."""
        target = tmp_path / "utf8.txt"
        content = "café résumé naïve 日本語"
        atomic_write_text(target, content)
        assert target.read_bytes().decode("utf-8") == content

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        target = tmp_path / "over.txt"
        atomic_write_text(target, "original")
        atomic_write_text(target, "replaced")
        assert target.read_text(encoding="utf-8") == "replaced"

    def test_no_temp_file_on_success(self, tmp_path: Path) -> None:
        target = tmp_path / "clean.txt"
        atomic_write_text(target, "data")
        assert not target.with_suffix(".tmp").exists()

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        target = str(tmp_path / "str_path.txt")
        atomic_write_text(target, "works")
        assert Path(target).read_text(encoding="utf-8") == "works"


# ---------------------------------------------------------------------------
# locked_json_read
# ---------------------------------------------------------------------------


class TestLockedJsonRead:
    """Verify locked_json_read returns correct data under various conditions."""

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        result = locked_json_read(tmp_path / "nonexistent.json")
        assert result is None

    def test_returns_none_for_empty_file(self, tmp_path: Path) -> None:
        target = tmp_path / "empty.json"
        target.write_text("", encoding="utf-8")
        assert locked_json_read(target) is None

    def test_returns_none_for_whitespace_only(self, tmp_path: Path) -> None:
        target = tmp_path / "ws.json"
        target.write_text("   \n  \t  ", encoding="utf-8")
        assert locked_json_read(target) is None

    def test_reads_dict(self, tmp_path: Path) -> None:
        target = tmp_path / "data.json"
        data = {"key": "value", "count": 42}
        target.write_text(json.dumps(data), encoding="utf-8")
        assert locked_json_read(target) == data

    def test_reads_list(self, tmp_path: Path) -> None:
        target = tmp_path / "list.json"
        target.write_text("[1, 2, 3]", encoding="utf-8")
        assert locked_json_read(target) == [1, 2, 3]

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        target = tmp_path / "str.json"
        target.write_text('{"ok": true}', encoding="utf-8")
        assert locked_json_read(str(target)) == {"ok": True}

    def test_roundtrip_with_atomic_write(self, tmp_path: Path) -> None:
        """locked_json_read can read files produced by atomic_write."""
        target = tmp_path / "roundtrip.json"
        data = {"roundtrip": True, "nested": {"a": 1}}
        atomic_write(target, data)
        assert locked_json_read(target) == data

    def test_concurrent_reads(self, tmp_path: Path) -> None:
        """Multiple threads reading simultaneously should all succeed."""
        target = tmp_path / "concurrent.json"
        data = {"thread_safe": True, "value": 12345}
        target.write_text(json.dumps(data), encoding="utf-8")

        results: list[object] = [None] * 10
        errors: list[Exception | None] = [None] * 10

        def reader(idx: int) -> None:
            try:
                results[idx] = locked_json_read(target)
            except Exception as exc:
                errors[idx] = exc

        threads = [threading.Thread(target=reader, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for i in range(10):
            assert errors[i] is None, f"Thread {i} raised: {errors[i]}"
            assert results[i] == data
