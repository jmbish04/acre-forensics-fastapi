from typing import Any, Dict, List, Optional

import httpx

from forensics_fastapi.config import HOST_API_URL, INTERNAL_SERVICE_KEY


class HostIntegrationClient:
    """
    Client for the Internal Bridge API hosted on the Cloudflare Worker.
    Supports AI, raw SQL, internal storage, and universal CRUD for data tables.
    """

    def __init__(self, base_url: str = HOST_API_URL, token: str = INTERNAL_SERVICE_KEY):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Content-Type": "application/json", "X-Worker-Api-Key": token}
        self.client = httpx.AsyncClient(headers=self.headers, timeout=30.0)

    async def _post(self, path: str, json: Optional[Dict] = None):
        """Internal helper for POST requests with error handling."""
        url = f"{self.base_url}{path}"
        try:
            response = await self.client.post(url, json=json or {})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            print(f"Bridge POST Error [{path}]: {e}")
            raise

    async def _get(self, path: str, params: Optional[Dict] = None):
        """Internal helper for GET requests."""
        url = f"{self.base_url}{path}"
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            print(f"Bridge GET Error [{path}]: {e}")
            raise

    # ------------------------------------------------------------------
    # 1. RAW DATABASE ACCESS (D1)
    # ------------------------------------------------------------------

    async def execute_query(self, sql: str, params: Optional[List] = None):
        """Execute raw SQL on Host D1 via /internal/d1/execute."""
        return await self._post("/internal/d1/execute", {"sql": sql, "params": params or []})

    async def list_tables(self):
        """List all tables in the database via /api/db/tables."""
        return await self._get("/api/db/tables")

    async def inspect_table(self, table_name: str):
        """Get rows from a specific table via /api/db/table/{name}."""
        return await self._get(f"/api/db/table/{table_name}")

    # ------------------------------------------------------------------
    # 2. INTERNAL STORAGE & WRITE OPERATIONS
    # ------------------------------------------------------------------

    async def store_forensic_analysis(self, message_id: str, analysis: Dict, score: float, status: str = "ANALYZED"):
        """
        Store Python analysis results via /internal/analysis/store.
        """
        payload = {
            "messageId": message_id,
            "analysisJson": analysis,
            "deceptionScore": score,
            "status": status
        }
        return await self._post("/internal/analysis/store", payload)

    async def create_raw_message(self, message_data: Dict):
        """
        Create a raw message record via /internal/db/message/create.
        Used when hydrating the database from initial Gmail fetch.
        """
        return await self._post("/internal/db/message/create", message_data)

    async def batch_create_transcripts(self, transcripts: List[Dict]):
        """
        Bulk insert transcripts via /internal/db/transcript/batch-create.
        """
        return await self._post("/internal/db/transcript/batch-create", {"transcripts": transcripts})

    # ------------------------------------------------------------------
    # 3. UNIVERSAL DATA CRUD
    # ------------------------------------------------------------------

    async def crud(self, resource: str, action: str, id: Optional[str] = None, payload: Optional[Dict] = None):
        """
        Universal handler for all /api/data/{resource} endpoints.

        Supported Resources:
        - threads, messages, engagements
        - engagementfacts, gmailevidences, forensicflags
        - agentconfigs, workflowlogs, workflowerrors
        - technicalentitys, rolodexs, emailtags

        Args:
            resource: The resource name (plural), e.g., "threads"
            action: "list", "get", "create", "update", "delete"
            id: Required for get/update/delete
            payload: Required for create/update
        """
        base_path = f"/api/data/{resource}"

        if action == "list":
            return await self._get(base_path)

        elif action == "create":
            if not payload:
                raise ValueError("Payload required for create")
            return await self._post(base_path, payload)

        elif action == "get":
            if not id:
                raise ValueError("ID required for get")
            return await self._get(f"{base_path}/{id}")

        elif action == "update":
            if not id or not payload:
                raise ValueError("ID and Payload required for update")
            # Using PUT explicitly here
            url = f"{self.base_url}{base_path}/{id}"
            try:
                response = await self.client.put(url, json=payload)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                print(f"Bridge PUT Error [{base_path}]: {e}")
                raise

        elif action == "delete":
            if not id:
                raise ValueError("ID required for delete")
            # Using DELETE explicitly here
            url = f"{self.base_url}{base_path}/{id}"
            try:
                response = await self.client.delete(url)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                print(f"Bridge DELETE Error [{base_path}]: {e}")
                raise
        else:
            raise ValueError(f"Unknown action: {action}")

    # ------------------------------------------------------------------
    # 4. AGENTS & AI (Existing)
    # ------------------------------------------------------------------

    async def run_ai_model(self, model: str, inputs: Any):
        """Run AI Model on Host using Workers AI"""
        return await self._post("/internal/ai/run", {"model": model, "inputs": inputs})

    async def push_ingest(self, emails: List, engagement_id: Optional[str] = None):
        """Push batch of emails to Host Ingest Queue"""
        return await self._post("/internal/ingest", {"emails": emails, "engagementId": engagement_id})

    async def consult_agent(self, agent_name: str, payload: Dict):
        """Consult a Worker Agent (e.g. Judge)"""
        return await self._post("/internal/agent/consult", {"agentName": agent_name, "payload": payload})

    async def trigger_forensic_workflow(self, message_data: Dict):
        """
        Trigger the async Forensic Workflow on the Host Worker.
        This replaces synchronous agent calls for ingestion.
        
        Args:
            message_data: Dict containing messageId, engagementId, body, etc.
        """
        return await self._post("/internal/workflow/trigger/forensic", message_data)

    async def close(self):
        await self.client.aclose()