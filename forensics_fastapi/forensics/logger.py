import json
import os
import threading
from datetime import datetime
from typing import Optional

import requests


class AsyncWebhookLogger:
    """
    Logs messages to the Cloudflare Worker via Webhook asynchronously.
    Falls back to console if webhook fails.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(AsyncWebhookLogger, cls).__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self.worker_url = os.environ.get(
            "WORKER_URL", "https://acre-forensics-backend.hacolby.workers.dev"
        )
        self.webhook_url = f"{self.worker_url}/webhooks/container/logs"
        self.session_token = os.environ.get("WORKER_API_KEY")
        self.headers = {"Content-Type": "application/json"}
        if self.session_token:
            self.headers["X-Worker-Api-Key"] = self.session_token

        if self.session_token:
            self.headers["X-Worker-Api-Key"] = self.session_token

        # [NEW] File persistence for local retrieval/tailing
        # Use /tmp to ensure writability and consistent path for provider to read
        self.log_file = "/tmp/forensics.log"
        try:
            # Ensure file exists
            with open(self.log_file, "a") as f:
                f.write(f"[{datetime.now().isoformat()}] [SYSTEM] Logger initialized\n")
        except Exception:
            pass  # Fail silently if FS not ready

    def log(self, type: str, message: str, step_name: str = "General", metadata: Optional[dict] = None):
        # Always print to console/stdout for Docker logs
        timestamp = datetime.now().isoformat()
        log_line = f"[{timestamp}] [{type}] [{step_name}] {message}"
        print(log_line)
        if metadata:
            print(f"Metadata: {json.dumps(metadata)}")

        # Write to file for tailing
        try:
            with open(self.log_file, "a") as f:
                f.write(log_line + "\n")
        except Exception:
            pass

        # Send to Webhook in background thread to avoid blocking
        payload = {
            "type": type,
            "message": message,
            "stepName": step_name,
            "timestamp": timestamp,
            "metadata": metadata,
            # Context
            "workflowId": os.environ.get("WORKFLOW_ID"),
            "engagementId": os.environ.get("ENGAGEMENT_ID"),
        }

        threading.Thread(target=self._send_webhook, args=(payload,), daemon=True).start()

    def _send_webhook(self, payload: dict):
        try:
            # Strip /internal if present in base URL to get root, or just trust WORKER_URL
            # The prompt asked for host worker to create path, so if WORKER_URL is the root,
            # appending /webhooks/container/logs is correct.
            requests.post(self.webhook_url, json=payload, headers=self.headers, timeout=5)
        except Exception:
            # print(f"Failed to send webhook log: {e}") # Avoid spamming stderr if worker is down
            pass

    def info(self, message: str, step_name: str = "INFO", metadata: Optional[dict] = None):
        self.log("INFO", message, step_name, metadata)

    def error(self, message: str, step_name: str = "ERROR", metadata: Optional[dict] = None):
        self.log("ERROR", message, step_name, metadata)

    def warning(self, message: str, step_name: str = "WARN", metadata: Optional[dict] = None):
        self.log("WARN", message, step_name, metadata)


# Global Accessor
logger = AsyncWebhookLogger()
