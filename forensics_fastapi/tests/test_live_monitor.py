
from forensics_fastapi.forensics.api import monitor


def test_monitor_page_loads(client):
    """Verify the /monitor page serves HTML."""
    response = client.get("/monitor")
    assert response.status_code == 200
    assert "ACRE Oversight" in response.text
    assert "iframe" not in response.text  # Just a sanity check against nesting


def test_websocket_init_stats(client):
    """Verify WebSocket connects and receives initial Clean stats."""
    # Reset monitor stats for deterministic test
    monitor.stats["queued"] = 999

    with client.websocket_connect("/ws/monitor") as websocket:
        # Receive INIT_STATS
        data = websocket.receive_json()
        assert data["type"] == "INIT_STATS"
        assert data["data"]["queued"] == 999

    # Verify disconnect handling
    # The context manager exit closes the socket
    # We can check if monitor cleaned up (might depend on implementation timing though)
    # monitor cleanup happens on Update/Loop exit, might not be instant in TestClient
