"""Tests for the filesystem browse API endpoint (GET /api/v1/filesystem/browse).

Coverage map (acceptance-criteria checklist):
  - default path (no param)
  - empty string path (same as default)
  - whitespace-only path (same as default)
  - explicit valid path with all three response fields verified
  - root path (parent: null)
  - root-path entry path construction (no double slash)
  - path with '..' (400)
  - URL-encoded traversal (400) – FastAPI decodes before handler
  - null byte (400)
  - file path (400) with JSON body containing the offending path
  - nonexistent path (404) with JSON body
  - permission-denied path (403) with JSON body
  - directory containing only files (200, entries: [])
  - symlinks excluded (both dir-links and file-links)
  - path normalisation (trailing slash stripped)
  - symlink path resolved to real path in response
  - relative path without leading slash (400, "absolute" in detail)
  - path longer than PATH_MAX (400)
  - race-condition removal during scandir (404, not 500)
  - non-UTF-8 filename silently skipped (200, no 500)
  - unauthenticated request (401) — SKIPPED, auth not yet implemented
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Default-path behaviour (no param / empty / whitespace)
# ---------------------------------------------------------------------------


class TestDefaultPath:
    def test_no_param_returns_home(self, client: TestClient) -> None:
        response = client.get("/api/v1/filesystem/browse")
        assert response.status_code == 200
        data = response.json()
        # path must equal the real home directory
        assert data["path"] == str(Path(os.path.realpath(str(Path.home()))))
        assert "parent" in data
        assert isinstance(data["entries"], list)

    def test_empty_string_param_returns_home(self, client: TestClient) -> None:
        response = client.get("/api/v1/filesystem/browse?path=")
        assert response.status_code == 200
        assert response.json()["path"] == str(Path(os.path.realpath(str(Path.home()))))

    def test_whitespace_only_param_returns_home(self, client: TestClient) -> None:
        response = client.get("/api/v1/filesystem/browse?path=   ")
        assert response.status_code == 200
        assert response.json()["path"] == str(Path(os.path.realpath(str(Path.home()))))


# ---------------------------------------------------------------------------
# Happy paths – valid directories
# ---------------------------------------------------------------------------


class TestValidPaths:
    def test_explicit_tmp_all_fields_present(self, client: TestClient) -> None:
        response = client.get("/api/v1/filesystem/browse?path=/tmp")
        assert response.status_code == 200
        data = response.json()
        real_tmp = os.path.realpath("/tmp")
        assert data["path"] == real_tmp
        assert data["parent"] == str(Path(real_tmp).parent)
        assert isinstance(data["entries"], list)
        for entry in data["entries"]:
            assert "name" in entry
            assert entry["type"] == "directory"
            assert "path" in entry

    def test_root_path_parent_is_null(self, client: TestClient) -> None:
        response = client.get("/api/v1/filesystem/browse?path=/")
        assert response.status_code == 200
        data = response.json()
        assert data["path"] == "/"
        assert data["parent"] is None  # JSON null, not the string "null"
        assert isinstance(data["entries"], list)

    def test_root_entry_paths_have_no_double_slash(self, client: TestClient) -> None:
        response = client.get("/api/v1/filesystem/browse?path=/")
        assert response.status_code == 200
        for entry in response.json()["entries"]:
            assert not entry["path"].startswith("//"), (
                f"Entry path must not start with //: {entry['path']!r}"
            )
            assert entry["path"] == f"/{entry['name']}"

    def test_subdir_entries_correct_paths(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        (tmp_path / "alpha").mkdir()
        (tmp_path / "beta").mkdir()
        (tmp_path / "file.txt").write_text("content")

        response = client.get(f"/api/v1/filesystem/browse?path={tmp_path}")
        assert response.status_code == 200
        data = response.json()
        names = {e["name"] for e in data["entries"]}
        assert names == {"alpha", "beta"}
        for entry in data["entries"]:
            expected = f"{data['path']}/{entry['name']}"
            assert entry["path"] == expected

    def test_only_directories_in_entries(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        (tmp_path / "subdir").mkdir()
        (tmp_path / "regular_file.txt").write_text("hello")
        (tmp_path / "another_file").write_text("world")

        response = client.get(f"/api/v1/filesystem/browse?path={tmp_path}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["entries"]) == 1
        assert data["entries"][0]["name"] == "subdir"

    def test_symlinks_excluded(self, client: TestClient, tmp_path: Path) -> None:
        real_dir = tmp_path / "real_dir"
        real_dir.mkdir()
        link_dir = tmp_path / "link_to_dir"
        link_dir.symlink_to(real_dir)

        real_file = tmp_path / "real_file.txt"
        real_file.write_text("content")
        link_file = tmp_path / "link_to_file.txt"
        link_file.symlink_to(real_file)

        response = client.get(f"/api/v1/filesystem/browse?path={tmp_path}")
        assert response.status_code == 200
        names = {e["name"] for e in response.json()["entries"]}
        assert "link_to_dir" not in names
        assert "link_to_file.txt" not in names
        assert "real_dir" in names

    def test_directory_with_only_files_returns_empty_entries(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        (tmp_path / "file1.txt").write_text("a")
        (tmp_path / "file2.txt").write_text("b")

        response = client.get(f"/api/v1/filesystem/browse?path={tmp_path}")
        assert response.status_code == 200
        assert response.json()["entries"] == []

    def test_trailing_slash_normalised(self, client: TestClient) -> None:
        r_plain = client.get("/api/v1/filesystem/browse?path=/tmp")
        r_slash = client.get("/api/v1/filesystem/browse?path=/tmp/")
        assert r_plain.status_code == 200
        assert r_slash.status_code == 200
        real_tmp = os.path.realpath("/tmp")
        assert r_plain.json()["path"] == r_slash.json()["path"] == real_tmp

    def test_symlink_path_resolves_to_real(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        link_path = tmp_path / "link_to_real"
        link_path.symlink_to(real_dir)

        response = client.get(f"/api/v1/filesystem/browse?path={link_path}")
        assert response.status_code == 200
        # The response path must be the resolved real path, not the symlink path.
        assert response.json()["path"] == str(real_dir.resolve())


# ---------------------------------------------------------------------------
# Error conditions
# ---------------------------------------------------------------------------


class TestErrorConditions:
    def test_path_traversal_double_dots_returns_400(
        self, client: TestClient
    ) -> None:
        response = client.get("/api/v1/filesystem/browse?path=../../etc/passwd")
        assert response.status_code == 400
        assert "detail" in response.json()

    def test_url_encoded_traversal_returns_400(self, client: TestClient) -> None:
        # FastAPI decodes %2e%2e%2f → ../../ before the handler; our validator
        # must catch the decoded form.
        response = client.get("/api/v1/filesystem/browse?path=%2e%2e%2fetc%2fpasswd")
        assert response.status_code == 400
        assert "detail" in response.json()

    def test_null_byte_returns_400(self, client: TestClient) -> None:
        response = client.get("/api/v1/filesystem/browse?path=/tmp%00evil")
        assert response.status_code == 400
        assert "detail" in response.json()

    def test_file_path_returns_400_with_json_body(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        file_path = tmp_path / "test_file.txt"
        file_path.write_text("content")

        response = client.get(f"/api/v1/filesystem/browse?path={file_path}")
        assert response.status_code == 400
        assert response.headers["content-type"].startswith("application/json")
        data = response.json()
        assert "detail" in data
        assert str(file_path) in data["detail"]

    def test_nonexistent_path_returns_404_with_json_body(
        self, client: TestClient
    ) -> None:
        response = client.get(
            "/api/v1/filesystem/browse?path=/nonexistent/path/xyz"
        )
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")
        data = response.json()
        assert "detail" in data
        assert "/nonexistent/path/xyz" in data["detail"]

    def test_permission_denied_returns_403_with_json_body(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        if os.geteuid() == 0:
            pytest.skip("Running as root – chmod 000 does not restrict access")

        restricted = tmp_path / "restricted"
        restricted.mkdir()
        restricted.chmod(0o000)
        try:
            response = client.get(
                f"/api/v1/filesystem/browse?path={restricted}"
            )
            assert response.status_code == 403
            assert response.headers["content-type"].startswith("application/json")
            data = response.json()
            assert "detail" in data
            assert str(restricted) in data["detail"]
        finally:
            restricted.chmod(0o755)  # restore so tmp_path cleanup succeeds

    def test_relative_path_returns_400_with_absolute_message(
        self, client: TestClient
    ) -> None:
        response = client.get("/api/v1/filesystem/browse?path=tmp")
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "absolute" in data["detail"].lower()

    def test_path_longer_than_path_max_returns_400(
        self, client: TestClient
    ) -> None:
        # Build a path that is definitely longer than 4096 characters.
        long_path = "/" + "a" * 4097
        response = client.get(f"/api/v1/filesystem/browse?path={long_path}")
        assert response.status_code == 400
        assert "detail" in response.json()

    def test_race_condition_dir_removed_during_scandir_returns_404(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        """Directory deleted between existence check and os.scandir → 404, not 500."""
        target = tmp_path / "vanishing_dir"
        target.mkdir()

        def _raise_fnf(path: object) -> None:
            raise FileNotFoundError(f"No such file or directory: {path!r}")

        with patch(
            "backend.api.v1_filesystem.os.scandir", side_effect=_raise_fnf
        ):
            response = client.get(
                f"/api/v1/filesystem/browse?path={target}"
            )

        assert response.status_code == 404
        assert "detail" in response.json()

    def test_non_utf8_filename_silently_skipped(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        """Non-UTF-8 directory entries are skipped; response is 200, never 500."""
        (tmp_path / "valid_dir").mkdir()

        # Build a mock DirEntry whose name contains a surrogate character
        # (what Python uses for undecodable filesystem bytes via surrogateescape).
        bad_entry = MagicMock()
        bad_entry.is_dir.return_value = True
        bad_entry.name = "bad\udcffname"  # surrogate → encode('utf-8') raises

        good_entry = MagicMock()
        good_entry.is_dir.return_value = True
        good_entry.name = "valid_dir"

        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(
            return_value=iter([bad_entry, good_entry])
        )
        mock_cm.__exit__ = MagicMock(return_value=False)

        with patch(
            "backend.api.v1_filesystem.os.scandir", return_value=mock_cm
        ):
            response = client.get(
                f"/api/v1/filesystem/browse?path={tmp_path}"
            )

        assert response.status_code == 200
        names = [e["name"] for e in response.json()["entries"]]
        assert "valid_dir" in names
        assert "bad\udcffname" not in names


# ---------------------------------------------------------------------------
# Authentication (skipped until auth middleware is implemented)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="auth not yet implemented")
class TestAuthentication:
    def test_unauthenticated_request_returns_401(
        self, client: TestClient
    ) -> None:
        # When auth middleware is added, an unauthenticated GET should return 401.
        response = client.get("/api/v1/filesystem/browse")
        assert response.status_code == 401
