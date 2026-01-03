"""
Test suite for Cloudflare Workers container control endpoints.
Adapts Claude's tests to the merged structure and AsyncClient pattern.
"""


import pytest

# Imports from merged structure
# Imports from merged structure
from forensics_fastapi.forensics.worker_manager import CloudflareWorkerAPI

# ============================================================================
# Fixtures
# ============================================================================


# Client fixture and anyio_backend are now provided by conftest.py


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up mock environment variables"""
    monkeypatch.setenv("CLOUDFLARE_WORKER_ADMIN_TOKEN", "test-token-12345")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-account-id")
    # workerScriptName should be picked up by get_cloudflare_config
    monkeypatch.setenv("WORKER_SCRIPT_NAME", "test-worker")


@pytest.fixture
def cloudflare_client(mock_env_vars):
    """Instantiate Cloudflare API client for testing"""
    return CloudflareWorkerAPI(
        api_token="test-token-12345", account_id="test-account-id", script_name="test-worker"
    )


# ... (omitted fixtures)

# ============================================================================
# Tests: Environment & Configuration
# ============================================================================


def test_missing_api_token(client, monkeypatch):
    """Should require CLOUDFLARE_WORKER_ADMIN_TOKEN (or other specific token)"""
    monkeypatch.delenv("CLOUDFLARE_WORKER_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)  # Ensure generic is gone too
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-id")

    response = client.get("/api/container/status")

    assert response.status_code == 500
    assert "Missing" in response.json()["detail"]


def test_missing_account_id(client, monkeypatch):
    """Should require CLOUDFLARE_ACCOUNT_ID"""
    monkeypatch.setenv("CLOUDFLARE_WORKER_ADMIN_TOKEN", "test-token")
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)

    response = client.get("/api/container/status")

    assert response.status_code == 500
    assert "Missing" in response.json()["detail"]
