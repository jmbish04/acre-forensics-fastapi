import os
from typing import Any, Dict, Optional

import requests


class AgentBrainClient:
    def __init__(self, worker_url: Optional[str] = None, secret: Optional[str] = None):
        self.base_url = worker_url or os.environ.get("WORKER_URL")
        self.secret = secret or os.environ.get("WORKER_API_KEY")
        self.headers = {"Content-Type": "application/json", "X-Worker-Api-Key": self.secret}

    def ask_agent(
        self, engagement_id: str, prompt: str, task: str = "analyze_evidence"
    ) -> Optional[Dict[str, Any]]:
        """
        Asks the Stateful Agent for an opinion/analysis.
        This allows the Python script to benefit from the Agent's memory of previous emails.
        """
        # Matches your src/routes/agents.ts route structure
        url = f"{self.base_url}/agents/forensic/{engagement_id}/ask"

        payload = {
            "prompt": prompt,
            "task": task,
            "context_request": ["rag", "history"],  # Tell agent to use its brain
        }

        try:
            resp = requests.post(url, json=payload, headers=self.headers, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"Failed to consult Agent Brain: {e}")
            return None
