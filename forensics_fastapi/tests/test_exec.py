

def test_exec_command_success(client):
    """Test successful command execution using real echo."""
    response = client.post("/api/commands/exec", json={"command": "echo", "args": ["hello"]})

    assert response.status_code == 200
    data = response.json()
    assert data["stdout"].strip() == "hello"
    assert data["stderr"] == ""
    assert data["exitCode"] == 0


def test_exec_command_missing_command(client):
    """Test validation failure."""
    response = client.post("/api/commands/exec", json={"args": []})
    assert response.status_code == 422
    assert "detail" in response.json()


def test_exec_python_success(client):
    """Test successful python generic execution."""
    response = client.post("/api/commands/exec-python", json={"code": "print('test_output')"})

    assert response.status_code == 200
    data = response.json()
    assert data["stdout"].strip() == "test_output"
    assert data["exitCode"] == 0


def test_exec_python_error(client):
    """Test python execution with error."""
    # Running a command that exits with 1
    response = client.post("/api/commands/exec-python", json={"code": "import sys; sys.exit(1)"})

    assert response.status_code == 200
    data = response.json()
    assert data["exitCode"] == 1
