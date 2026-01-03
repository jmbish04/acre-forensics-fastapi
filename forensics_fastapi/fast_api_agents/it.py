from typing import Dict, List, Optional

from .base import BaseAgentClient


class ItAgentClient(BaseAgentClient):
    """
    Client for the IT/Geeksquad Agent.
    Note: This agent exposes specific REST-like endpoints in its onRequest handler.
    """
    def __init__(self, engagement_id: str = "global"):
        super().__init__("geeksquad", engagement_id)

    def spinup_container(self, container_id: str, task_name: str, config: Optional[Dict] = None) -> Dict:
        """
        POST /agent/container/spinup
        """
        # We access the internal client directly to hit specific paths
        return self.client.post("/api/agent/container/spinup", {
            "containerId": container_id,
            "taskName": task_name,
            "config": config or {}
        })

    def execute_task(self, container_id: str, task_name: str, command: str) -> Dict:
        """
        POST /agent/task/execute
        Run a command in a specific container and log it.
        """
        return self.client.post("/api/agent/task/execute", {
            "containerId": container_id,
            "taskName": task_name,
            "command": command
        })

    def investigate_error(self, error_id: str, container_id: str) -> str:
        """
        POST /agent/error/investigate
        Returns a text analysis of the logs.
        """
        # Note: This endpoint might return plain text, so we might need `_post` variants that handle text
        # Using the standard post which expects JSON response might fail if it returns plain text.
        # However, RemoteWorkerClient.post expects JSON. 
        # If the agent returns text (as seen in TS: `new Response(analysis, { 'Content-Type': 'text/plain' })`),
        # we need a raw call.
        
        url = f"{self.client.base_url}/api/agent/error/investigate"
        import requests
        resp = requests.post(url, json={"errorId": error_id, "containerId": container_id}, headers=self.client.headers)
        resp.raise_for_status()
        return resp.text

    def chat(self, messages: List[Dict]) -> Dict:
        """
        POST /agent/chat
        Chat with the IT System Administrator.
        """
        return self.client.post("/api/agent/chat", {"messages": messages})
    
    def get_audit_logs(self, container_id: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None) -> Dict:
        """
        GET /agent/audit/logs
        """
        params = {}
        if container_id:
            params['containerId'] = container_id
        if start:
            params['start'] = start
        if end:
            params['end'] = end
        
        return self.client._get("/api/agent/audit/logs", params=params)
