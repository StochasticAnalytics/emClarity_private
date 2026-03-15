"""Regression tests for the entry-path contract in the filesystem browse endpoint.

These tests specifically verify that every entry's ``path`` field is consistent
with ``response.path`` (both rooted at the resolved real path), which is the
contract documented in the module docstring of ``v1_filesystem.py``.

This file was added as part of TASK-002a/PATCH to provide regression protection
for Defect #1 (entry_base symlink inconsistency).  Two existing tests
(``test_only_directories_in_entries`` and ``test_symlink_path_resolves_to_real``)
verify the response structure but leave entry ``path`` values unchecked; this
file closes that gap without modifying the original test file.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestEntryPathContract:
    """Entry path values must always equal response.path + "/" + entry.name."""

    def test_only_directories_entry_path_matches_parent(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        """Regression for test_only_directories_in_entries missing entry path check.

        That test verifies one entry named "subdir" is returned but does not
        assert entry["path"].  This test ensures the path is correct.
        """
        (tmp_path / "subdir").mkdir()
        (tmp_path / "regular_file.txt").write_text("hello")

        response = client.get(f"/api/v1/filesystem/browse?path={tmp_path}")
        assert response.status_code == 200
        data = response.json()

        assert len(data["entries"]) == 1
        entry = data["entries"][0]
        assert entry["name"] == "subdir"

        # The entry path must be consistent with response.path, not with the
        # caller-supplied path (which may differ when symlinks are involved).
        expected_entry_path = f"{data['path']}/{entry['name']}"
        assert entry["path"] == expected_entry_path, (
            f"Entry path {entry['path']!r} is inconsistent with "
            f"response.path {data['path']!r}. "
            "Expected: {expected_entry_path!r}"
        )

    def test_symlink_target_entry_paths_use_real_path(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        """Regression for test_symlink_path_resolves_to_real missing entry path check.

        The original test only checks response.path == real_dir.resolve().
        This test additionally verifies that entry paths are rooted at the
        resolved real path, not at the symlink path.

        Before Defect #1 was fixed, entry_base used display_path (the symlink
        path) so entry.path would be ``/symlink/subdir`` while response.path
        was ``/real``.  After the fix both must use the resolved real path.
        """
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        # Add a subdirectory so entries is non-empty.
        (real_dir / "inner").mkdir()

        link_path = tmp_path / "link_to_real"
        link_path.symlink_to(real_dir)

        response = client.get(f"/api/v1/filesystem/browse?path={link_path}")
        assert response.status_code == 200
        data = response.json()

        real_path = str(real_dir.resolve())
        # response.path must be the resolved real path.
        assert data["path"] == real_path

        # Every entry path must also be rooted at the resolved real path.
        assert len(data["entries"]) == 1
        entry = data["entries"][0]
        assert entry["name"] == "inner"

        expected_entry_path = f"{real_path}/{entry['name']}"
        assert entry["path"] == expected_entry_path, (
            f"Entry path {entry['path']!r} does not match the resolved real "
            f"path {real_path!r}.  This likely means entry_base still uses "
            "display_path (the symlink path) instead of the real path."
        )

        # Explicitly verify entry path is NOT rooted at the symlink path.
        symlink_based_path = f"{link_path}/{entry['name']}"
        assert entry["path"] != symlink_based_path, (
            "Entry path must not be rooted at the symlink path "
            f"{str(link_path)!r}; it must use the real path {real_path!r}."
        )

    def test_all_entry_paths_consistent_with_response_path(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        """Generic contract: for every entry, entry.path == response.path + "/" + entry.name."""
        (tmp_path / "alpha").mkdir()
        (tmp_path / "beta").mkdir()
        (tmp_path / "gamma").mkdir()
        (tmp_path / "file.txt").write_text("content")

        response = client.get(f"/api/v1/filesystem/browse?path={tmp_path}")
        assert response.status_code == 200
        data = response.json()

        response_path = data["path"]
        for entry in data["entries"]:
            expected = f"{response_path}/{entry['name']}"
            assert entry["path"] == expected, (
                f"Entry {entry['name']!r}: path {entry['path']!r} != "
                f"expected {expected!r} (derived from response.path={response_path!r})"
            )

    def test_root_entry_path_contract(self, client: TestClient) -> None:
        """Root entries: path must be '/' + name (no double slash, consistent with response.path)."""
        response = client.get("/api/v1/filesystem/browse?path=/")
        assert response.status_code == 200
        data = response.json()
        assert data["path"] == "/"

        for entry in data["entries"]:
            assert entry["path"] == f"/{entry['name']}", (
                f"Root entry {entry['name']!r} path {entry['path']!r} should be "
                f"'/{entry['name']}'"
            )
