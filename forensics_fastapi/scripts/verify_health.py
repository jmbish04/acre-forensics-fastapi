import json
import os
import sys


def check_db():
    # Simple check for SQLite database usually present in these containers
    base_dir = os.environ.get("WORKSPACE_DIR", "/workspace")
    db_path = os.path.join(base_dir, "src/data/forensics.db")
    if os.path.exists(db_path):
        return {"status": "pass", "message": f"Database found at {db_path}"}
    return {"status": "fail", "message": f"Database file not found at {db_path}"}


def check_r2_mount():
    mount_path = "/evidence"
    if os.path.exists(mount_path):
        try:
            # Try to list files to verify access
            files = os.listdir(mount_path)
            return {"status": "pass", "message": f"R2 mount accessible, found {len(files)} items"}
        except Exception as e:
            return {"status": "fail", "message": f"R2 mount found but inaccessible: {str(e)}"}
    return {"status": "fail", "message": "R2 Evidence Locker not mounted at /evidence"}


def check_gmail_token():
    # Check for presence of credentials file or env var
    base_dir = os.environ.get("WORKSPACE_DIR", "/workspace")
    token_path = os.path.join(base_dir, ".credentials/token.json")
    if os.path.exists(token_path) or os.environ.get("GMAIL_TOKEN"):
        return {"status": "pass", "message": "Gmail API credentials detected"}
    return {"status": "fail", "message": "Gmail API token missing in .credentials or environment"}


def run_diagnostics():
    results = [
        {"name": "Database Connectivity", **check_db()},
        {"name": "R2 Evidence Locker", **check_r2_mount()},
        {"name": "Gmail API Token", **check_gmail_token()},
    ]
    return results


if __name__ == "__main__":
    try:
        results = run_diagnostics()
        print(json.dumps(results))
    except Exception as e:
        print(json.dumps([{"name": "System", "status": "fail", "message": str(e)}]))
        sys.exit(1)
