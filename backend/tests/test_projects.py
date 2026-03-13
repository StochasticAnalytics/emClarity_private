"""Tests for project models, service, and API endpoints."""

from __future__ import annotations

from pathlib import Path

from backend.models.project import Project, ProjectState, TiltSeries
from backend.services.project_service import ProjectService


class TestProjectModels:
    """Verify Pydantic model creation."""

    def test_project_creation(self):
        project = Project(
            name="test",
            path="/tmp/test",
            state=ProjectState.UNINITIALIZED,
            current_cycle=0,
            tilt_series=[],
        )
        assert project.name == "test"
        assert project.state == ProjectState.UNINITIALIZED

    def test_tilt_series_creation(self):
        ts = TiltSeries(
            name="tilt1",
            stack_path="/data/tilt1.st",
            rawtlt_path="/data/tilt1.rawtlt",
            aligned=False,
            ctf_estimated=False,
        )
        assert ts.name == "tilt1"
        assert ts.aligned is False

    def test_project_state_values(self):
        """Ensure all expected states exist in the enum."""
        expected = {
            "uninitialized",
            "tilt_aligned",
            "ctf_estimated",
            "reconstructed",
            "particles_picked",
            "initialized",
            "cycle_n",
            "export",
            "done",
        }
        actual = {s.value for s in ProjectState}
        assert expected == actual


class TestProjectService:
    """Verify the project service logic."""

    def test_create_project(self, tmp_path):
        service = ProjectService()
        project_path = str(tmp_path / "new_project")
        project = service.create_project("my_project", project_path)

        assert project.name == "my_project"
        assert project.state == ProjectState.UNINITIALIZED
        assert Path(project_path).exists()
        assert (Path(project_path) / "rawData").exists()
        assert (Path(project_path) / "logFile").exists()

    def test_load_project(self, tmp_project):
        service = ProjectService()
        project = service.load_project(str(tmp_project))

        assert project.name == "test_project"
        assert project.state == ProjectState.UNINITIALIZED

    def test_detect_tilt_aligned_state(self, tmp_project):
        # Create a dummy file in fixedStacks to simulate alignment
        (tmp_project / "fixedStacks" / "tilt1_ali.mrc").touch()
        service = ProjectService()
        project = service.load_project(str(tmp_project))
        assert project.state == ProjectState.TILT_ALIGNED

    def test_discover_tilt_series(self, tmp_project):
        # Create dummy tilt-series files
        (tmp_project / "rawData" / "tilt1.st").touch()
        (tmp_project / "rawData" / "tilt1.rawtlt").touch()
        (tmp_project / "rawData" / "tilt2.st").touch()

        service = ProjectService()
        series = service.list_tilt_series(str(tmp_project))

        assert len(series) == 2
        names = {ts.name for ts in series}
        assert "tilt1" in names
        assert "tilt2" in names

        # tilt1 has a rawtlt file, tilt2 does not
        tilt1 = next(ts for ts in series if ts.name == "tilt1")
        tilt2 = next(ts for ts in series if ts.name == "tilt2")
        assert tilt1.rawtlt_path is not None
        assert tilt2.rawtlt_path is None


class TestProjectEndpoints:
    """Test the API endpoints via the test client."""

    def test_create_project(self, client, tmp_path):
        response = client.post(
            "/api/projects",
            json={"name": "api_test", "path": str(tmp_path / "api_project")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "api_test"
        assert data["state"] == "uninitialized"

    def test_load_nonexistent_project(self, client):
        response = client.get("/api/projects/nonexistent/path/nowhere")
        assert response.status_code == 404

    def test_health_check(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
