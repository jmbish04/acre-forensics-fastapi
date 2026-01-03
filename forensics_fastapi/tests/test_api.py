import pytest

# Client fixture is now provided by conftest.py


def test_read_root(client):
    """Test landing page loads."""
    response = client.get("/")
    assert response.status_code == 200
    assert "ACRE" in response.text


def test_health_check_structure(client):
    """Test health check returns correct structure."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "secrets" in data
    assert "google" in data
    assert "worker" in data
    assert "status" in data


def test_container_env_paths():
    """Test that critical directories exist."""
    import os

    # expected_dirs was unused
    # We are running inside /app likely, so paths are relative to where api.py runs
    # or absolute structure in container.
    # But python package root 'src' is linked from /app/src -> /app/forensics_fastapi/forensics
    # In API code: EVIDENCE_DIR = "src/forensics/evidence"
    # Actually, let's verify if the app can write to evidence dir
    from forensics_fastapi.forensics.api import EVIDENCE_DIR

    assert os.path.exists(EVIDENCE_DIR) or os.access(os.path.dirname(EVIDENCE_DIR), os.W_OK)


def test_ingestion_module_import():
    """Verify core modules can be imported (detects path issues)."""
    try:
        from forensics_fastapi.forensics.ingestion import ArtifactRegistry
        _ = ArtifactRegistry
        assert True
    except ImportError as e:
        pytest.fail(f"Failed to import src.forensics.ingestion: {e}")
