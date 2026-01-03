import json
import os
import sys
from typing import Any, Dict, List, Optional, Union, cast
from urllib.parse import urlparse, urlunparse

import requests


class OutputDup:
    """Duplicate output to both stdout/stderr and remote worker."""
    def __init__(self, original_stream, logger_func):
        self.original_stream = original_stream
        self.logger_func = logger_func
        self.buffer = ""

    def write(self, message):
        self.original_stream.write(message)
        self.original_stream.flush()
        self.buffer += message
        if "\n" in self.buffer:
            lines = self.buffer.split("\n")
            for line in lines[:-1]:
                if line.strip():
                    self.logger_func(line)
            self.buffer = lines[-1]

    def flush(self):
        self.original_stream.flush()
        if self.buffer.strip():
            self.logger_func(self.buffer)
            self.buffer = ""

    def isatty(self):
        return getattr(self.original_stream, "isatty", lambda: False)()

    @property
    def encoding(self):
        return getattr(self.original_stream, "encoding", "utf-8")


class WorkerLogger:
    """Handles logging to the remote D1 database via Worker API."""
    def __init__(self, client: "RemoteWorkerClient", workflow_id: str, engagement_id: Optional[str] = None):
        self.client = client
        self.workflow_id = workflow_id
        self.engagement_id = engagement_id

    def enable_console_capture(self):
        sys.stdout = OutputDup(sys.stdout, lambda m: self.info("STDOUT", m))
        sys.stderr = OutputDup(sys.stderr, lambda m: self.error("STDERR", m))

    def info(self, step_name: str, message: str, action_type: str = "ACTION", metadata: Optional[Dict] = None):
        try:
            self.client.log_event("INFO", self.workflow_id, step_name, message, self.engagement_id, action_type=action_type, metadata=metadata)
        except Exception:
            pass

    def error(self, step_name: str, message: str, error_type: str = "CONTAINER_ERROR", stack_trace: Optional[str] = None, metadata: Optional[Dict] = None):
        try:
            self.client.log_event("ERROR", self.workflow_id, step_name, message, self.engagement_id,
                                  error_type=error_type, stack_trace=stack_trace, metadata=metadata)
        except Exception:
            pass

    def warning(self, step_name: str, message: str, metadata: Optional[Dict] = None):
        try:
            self.client.log_event("WARN", self.workflow_id, step_name, message, self.engagement_id, metadata=metadata)
        except Exception:
            pass


class RemoteWorkerClient:
    """
    Unified Client for all Worker API operations (Internal Bridge).
    Supports both /api (public/data) and /internal (system/ops) namespaces.
    """
    def __init__(self, worker_url: Optional[str] = None, secret: Optional[str] = None):
        # 1. Load URL
        raw_url = worker_url or os.environ.get(
            "WORKER_URL", "https://acre-forensics-backend.hacolby.workers.dev"
        )
        parsed = urlparse(raw_url)
        self.base_url = urlunparse((parsed.scheme or "https", parsed.netloc, "", "", "", "")).rstrip("/")

        # 2. Load Secrets
        self.api_key = secret or os.environ.get("WORKER_API_KEY")
        self.cf_id = os.environ.get("CF_ACCESS_CLIENT_ID")
        self.cf_secret = os.environ.get("CF_ACCESS_CLIENT_SECRET")

        if not self.api_key:
            print("[WARN] RemoteWorkerClient: No WORKER_API_KEY found.")

        # 3. Build Robust Headers (FIXED AUTH LOGIC)
        self.headers = {
            "Content-Type": "application/json",
            # Standard Worker Auth headers (supports both conventions to be safe)
            "X-Session-Token": self.api_key if self.api_key else "",
            "X-Internal-Token": self.api_key if self.api_key else "",
            "Authorization": f"Bearer {self.api_key}" if self.api_key else ""
        }

        # 4. Attach Cloudflare Access Headers (Zero Trust)
        use_cf_access = os.environ.get("USE_CLOUDFLARE_ACCESS", "true").lower() == "true"
        
        if use_cf_access:
            if self.cf_id and self.cf_secret:
                self.headers["CF-Access-Client-Id"] = self.cf_id
                self.headers["CF-Access-Client-Secret"] = self.cf_secret
            else:
                print("[WARN] RemoteWorkerClient: Missing CF Access Headers.")
        else:
             # Explicitly disabled
             pass

    def _request(self, method: str, path: str, **kwargs) -> Any:
        """Centralized request handler with auth error logging."""
        url = f"{self.base_url}{path}"
        try:
            resp = requests.request(method, url, headers=self.headers, timeout=30, **kwargs)
            
            if resp.status_code in [401, 403]:
                print(f"❌ API {method} Failed [{path}]: {resp.status_code} Unauthorized.")
                # print(f"   Headers: {list(self.headers.keys())}") 
                return {}

            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ API {method} Error [{path}]: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"   Response: {e.response.text[:200]}")
            raise

    def _post(self, path: str, data: Dict) -> Dict:
        return self._request("POST", path, json=data)

    def _get(self, path: str, params: Optional[Dict] = None) -> Dict:
        return self._request("GET", path, params=params)

    def _put(self, path: str, data: Dict) -> Dict:
        return self._request("PUT", path, json=data)

    def _delete(self, path: str) -> Dict:
        return self._request("DELETE", path)
    
    # Alias for 'post' used in other files
    def post(self, path: str, json: Dict) -> Dict:
        return self._post(path, json)

    # ------------------------------------------------------------------
    # 1. RAW DATABASE ACCESS (D1)
    # ------------------------------------------------------------------

    def execute_query(self, sql: str, params: Optional[List] = None) -> Dict:
        return self._post("/internal/d1/execute", {"sql": sql, "params": params or []})

    def list_tables(self) -> Dict:
        return self._get("/api/db/tables")

    def inspect_table(self, table_name: str) -> Dict:
        return self._get(f"/api/db/table/{table_name}")

    # ------------------------------------------------------------------
    # 2. UNIVERSAL CRUD
    # ------------------------------------------------------------------

    def crud(self, resource: str, action: str, id: Optional[str] = None, payload: Optional[Dict] = None) -> Any:
        base_path = f"/api/data/{resource}"
        if action == "list":
            return self._get(base_path)
        elif action == "create":
            return self._post(base_path, payload or {})
        elif action == "get":
            return self._get(f"{base_path}/{id}")
        elif action == "update":
            return self._put(f"{base_path}/{id}", payload or {})
        elif action == "delete":
            return self._delete(f"{base_path}/{id}")
        else:
            raise ValueError(f"Unknown action: {action}")

    # ------------------------------------------------------------------
    # 3. LOGGING
    # ------------------------------------------------------------------

    def log_event(self, type: str, workflow_id: str, step_name: str, message: str, 
                  engagement_id: Optional[str] = None, action_type: Optional[str] = None, 
                  error_type: Optional[str] = None, stack_trace: Optional[str] = None, 
                  metadata: Optional[Dict] = None):
        payload = {
            "type": type, "workflowId": workflow_id, "engagementId": engagement_id,
            "stepName": step_name, "message": message, "metadata": metadata,
        }
        if type == "INFO":
            payload["actionType"] = action_type
        elif type == "ERROR":
            payload["errorType"] = error_type
            payload["stackTrace"] = stack_trace

        try:
            # Short timeout for logs to avoid blocking main flow
            requests.post(f"{self.base_url}/internal/log", json=payload, headers=self.headers, timeout=5)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 4. INTERNAL OPS (Context, HIL, Transcript)
    # ------------------------------------------------------------------

    def get_thread_context(self, engagement_id: str, thread_id: str) -> Dict:
        return self._post("/internal/context/thread", {"engagementId": engagement_id, "threadId": thread_id})

    def store_analysis(self, message_id: str, analysis_json: Dict, deception_score: float = 0.0, status: str = "ANALYZED", session_id: Optional[str] = None):
        # Using the specific endpoint from your successful local test path if needed, 
        # otherwise defaulting to the generic internal path
        return self._post("/internal/db/message/update-analysis", {
            "messageId": message_id, "analysis": analysis_json, 
            "deceptionScore": deception_score, "sessionId": session_id
        })

    def create_message(self, message_data: Dict):
        return self._post("/internal/db/message/create", message_data)

    def batch_create_transcripts(self, transcripts: List[Dict]):
        return self._post("/internal/db/transcripts/batch", {"transcripts": transcripts})

    # ------------------------------------------------------------------
    # 5. PUBLIC ENTITY WRAPPERS
    # ------------------------------------------------------------------

    def list_engagements(self): return self._get("/api/engagements")
    def create_engagement(self, data: Dict): return self._post("/api/engagements", data)
    def add_fact(self, engagement_id: str, fact_data: Dict): return self._post(f"/api/engagements/{engagement_id}/facts", fact_data)
    
    # Missing methods from type check
    def get_engagement(self, engagement_id: str) -> Dict:
        return self._get(f"/api/engagements/{engagement_id}")

    def get_context_pack(self, engagement_id: str) -> Dict:
        return self._get(f"/api/engagements/{engagement_id}/context")
    
    def draft_reply(self, intent: str, tone: str, facts: List, engagement_context: Dict) -> Dict:
        return self._post("/internal/agents/strategy/draft", {
            "intent": intent, "tone": tone, "facts": facts, "engagementContext": engagement_context
        })

    def reality_check(self, draft_text: str, facts: List, engagement_id: Optional[str] = None) -> Dict:
        return self._post("/internal/agents/strategy/check", {
            "draftText": draft_text, "facts": facts, "engagementId": engagement_id
        })

    # ------------------------------------------------------------------
    # 6. AI & AGENTS
    # ------------------------------------------------------------------

    def run_ai(self, task: str, prompt: Optional[str] = None, system: Optional[str] = None, 
               model: Optional[str] = None, json_schema: Optional[Dict] = None, 
               text: Optional[Union[str, List[str]]] = None, inputs: Optional[Dict] = None) -> Any:
        if inputs is None:
            inputs = {"task": task, "prompt": prompt, "system": system, "jsonSchema": json_schema, "text": text}
            inputs = {k: v for k, v in inputs.items() if v is not None}
        elif system and "system" not in inputs:
            inputs["system"] = system
        
        payload = {"model": model or "@cf/meta/llama-3-8b-instruct", "inputs": inputs}
        return self._post("/internal/ai/run", payload).get("result")

    def run_agent(self, agent_name: str, action: str, payload: Dict = {}, agent_id: str = "default") -> Any:
        return self._post("/internal/agent/run", {"agentName": agent_name, "agentId": agent_id, "action": action, "payload": payload}).get("result")

    def classify_transcripts_batch(self, payload: Dict[str, Any]) -> Dict[str, List[str]]:
        inputs = {"context": "", "transcripts": payload.get("transcripts", {})}
        system_prompt = "Classify transcripts: Financial, Legal, Personal, Other."
        json_schema = {"type": "object", "additionalProperties": {"type": "array", "items": {"type": "string"}}}
        
        result = self.run_ai("classify_transcripts", inputs=inputs, system=system_prompt, json_schema=json_schema)
        
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except Exception:
                return {}
        return cast(Dict[str, List[str]], result) if isinstance(result, dict) else {}