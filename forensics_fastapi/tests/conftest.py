import os
import sys
from typing import Generator

import pytest
from fastapi.testclient import TestClient

# --- 1. PATH FIX: Ensure we can import from the source tree ---
# Adds the project root to sys.path so 'from forensics_fastapi.forensics.api import app' works
current_dir = os.path.dirname(os.path.abspath(__file__))
# Go up two levels: tests/ -> forensics_fastapi/ -> root
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


# --- 2. LOOP FIX: Tell AnyIO to use asyncio ---
@pytest.fixture(scope="session")
def anyio_backend():
    """
    This fixture tells pytest-anyio to use the standard 'asyncio' backend.
    It resolves the 'RuntimeError: Cannot run the event loop' conflict.
    """
    return "asyncio"


# --- 3. CLIENT FIX: Shared TestClient ---
@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    # Import inside the fixture to ensure sys.path is ready
    from forensics_fastapi.forensics.api import app

    with TestClient(app) as c:
        yield c
