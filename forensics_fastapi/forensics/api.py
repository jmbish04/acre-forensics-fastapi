import os
import traceback
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware  # [NEW]
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field

load_dotenv()
from typing import Dict, List, Optional

# --- Lifespan ---
from forensics_fastapi.config import EVIDENCE_DIR, OUTPUT_DIR
from forensics_fastapi.core.host_client import HostIntegrationClient
from forensics_fastapi.forensics.attachments.pipeline import AttachmentPipeline
from forensics_fastapi.forensics.gmail_collector import GmailCollector

# Import ACRE Modules
from forensics_fastapi.forensics.ingestion import ArtifactRegistry
from forensics_fastapi.forensics.logger import logger as app_logger
from forensics_fastapi.forensics.pipeline import ACREPipeline
from forensics_fastapi.forensics.remote_worker_api import RemoteWorkerClient
from forensics_fastapi.forensics.reporter import ForensicReporter

# IMPORT ROUTERS (But include them later)
from forensics_fastapi.forensics.routers import cli_router, container, engagements, sandbox, strategy, terminal


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize Host Client
    app.state.host_client = HostIntegrationClient()
    app_logger.info(
        f"Initialized HostIntegrationClient at {app.state.host_client.base_url}",
        step_name="Startup",
    )

    # 2. Setup Filesystem (Lazy Creation)
    try:
        os.makedirs(EVIDENCE_DIR, exist_ok=True)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        app_logger.info(
            f"Verified directories: Evidence={EVIDENCE_DIR}, Output={OUTPUT_DIR}",
            step_name="Startup",
        )
    except OSError as e:
        app_logger.warning(
            f"Failed to create directories: {e}. Falling back or running in restricted mode.",
            step_name="Startup",
        )

    yield

    # Cleanup
    await app.state.host_client.close()


# Initialize remote logger
WORKFLOW_ID = os.environ.get("WORKFLOW_ID", "container-startup")
ENGAGEMENT_ID = os.environ.get("ENGAGEMENT_ID")

client = RemoteWorkerClient()
app_logger.info(f"API Starting up... Workflow: {WORKFLOW_ID}", step_name="Startup")

tags_metadata = [
    {"name": "Monitor", "description": "Real-time oversight."},
    {"name": "Ingestion", "description": "Evidence ingestion operations."},
    {"name": "Pipeline", "description": "Forensic analysis pipeline."},
]

app = FastAPI(
    title="ACRE Forensic Engine",
    description="API for Adversarial Communication Reconstruction Engine",
    version="1.0.0",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

# --- Middleware (CORS is critical for WebSockets sometimes) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from starlette.types import ASGIApp, Receive, Scope, Send


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path")
            app_logger.info(f"Req: {path}", step_name="Middleware")
        await self.app(scope, receive, send)

app.add_middleware(RequestLoggingMiddleware)

# config
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)


# --- Schemas ---
class ExecResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int = Field(..., alias="exitCode")
    model_config = ConfigDict(populate_by_name=True)

class GmailSyncRequest(BaseModel):
    query: str = "after:2024/01/01"
    engagement_id: Optional[str] = None

class AnalysisSecrets(BaseModel):
    GCP_SERVICE_ACCOUNT: Optional[str] = None
    WORKER_API_KEY: Optional[str] = None

class AnalysisRequest(BaseModel):
    messageId: str
    from_: str = Field(..., alias="from")
    to: str
    subject: str
    body: str
    headers: Dict[str, str] = {}
    rawMessage: Optional[str] = None
    analysisTypes: List[str] = []
    timestamp: Optional[str] = None
    secrets: Optional[AnalysisSecrets] = None
    workflowId: Optional[str] = None
    engagementId: Optional[str] = None
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

class AttachmentIngestionRequest(BaseModel):
    file_path: str
    attachment_id: str
    session_id: str
    engagement_id: Optional[str] = None

class PipelineRunRequest(BaseModel):
    engagement_id: str = "default"
    gmail_domain: Optional[str] = None

class ReportGenRequest(BaseModel):
    engagement_id: Optional[str] = None
    thread_id: Optional[str] = None


# ==========================================
# 📡 MONITOR LOGIC (Hardened)
# ==========================================
import json


class PipelineMonitor:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        # Base stats structure
        self.stats = {
            "queued": 0, 
            "in_process": 0, 
            "completed": 0, 
            "threats": 0, 
            "recent_logs": []
        }

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WS] Client connected. Total: {len(self.active_connections)}")
        
        # Safe Initial Send
        try:
            # We strictly sanitize stats before sending to avoid serialization crashes
            safe_stats = json.loads(json.dumps(self.stats, default=str))
            await websocket.send_json({"type": "INIT_STATS", "data": safe_stats})
        except Exception as e:
            print(f"[WS] Error sending init stats: {e}")
            # Do NOT raise here, or we kill the connection. 
            # Just log it; the client will get updates later.

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"[WS] Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        # 1. Update Internal Stats safely
        msg_type = message.get("type")
        try:
            if msg_type == "ingest_start":
                self.stats["queued"] += int(message.get("count", 0))
            elif msg_type == "step_start":
                self.stats["in_process"] = 1 
            elif msg_type == "step_complete" and message.get("step") == "Pipeline":
                self.stats["in_process"] = 0
                self.stats["completed"] += 1
            elif msg_type == "decision_made" and message.get("label", {}).get("intent") == "Phishing":
                self.stats["threats"] += 1

            if "log" in message:
                # CRITICAL: Force string conversion to prevent objects breaking JSON
                log_msg = str(message["log"]) 
                self.stats["recent_logs"].insert(0, log_msg)
                self.stats["recent_logs"] = self.stats["recent_logs"][:50]
        except Exception as e:
            print(f"[WS] Error updating stats: {e}")

        # 2. Broadcast to clients safely
        # We copy the list to avoid "set changed size during iteration" errors
        for connection in list(self.active_connections):
            try:
                # Force sanitization of the outgoing message
                safe_msg = json.loads(json.dumps(message, default=str))
                await connection.send_json(safe_msg)
            except RuntimeError:
                # Connection likely closed/dead
                self.disconnect(connection)
            except Exception as e:
                print(f"[WS] Broadcast error: {e}")
                pass

monitor = PipelineMonitor()


# ==========================================
# ⚡ WEBSOCKET ENDPOINT (Robust)
# ==========================================

@app.websocket("/ws/monitor")
async def websocket_endpoint(websocket: WebSocket):
    try:
        await monitor.connect(websocket)
        while True:
            # Keep connection alive. We expect simple pings or nothing.
            # receive_text() waits for a message. If client disconnects, 
            # it raises WebSocketDisconnect immediately.
            data = await websocket.receive_text()
            
            # Optional: Heartbeat response
            if data == "ping":
                await websocket.send_text("pong")
                
    except WebSocketDisconnect:
        monitor.disconnect(websocket)
    except Exception as e:
        print(f"[WS] Critical Endpoint Error: {e}")
        traceback.print_exc()
        monitor.disconnect(websocket)





# ==========================================
# 🖥️ UI ROUTES
# ==========================================

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/overview", response_class=HTMLResponse)
def read_overview(request: Request):
    return templates.TemplateResponse("overview.html", {"request": request})

@app.get("/setup", response_class=HTMLResponse)
def read_setup(request: Request):
    return templates.TemplateResponse("setup_guide.html", {"request": request})

@app.get("/monitor", response_class=HTMLResponse)
def read_monitor(request: Request):
    return templates.TemplateResponse("oversight.html", {"request": request})

@app.get("/oversight")
def redirect_oversight():
    return RedirectResponse(url="/monitor")

@app.get("/tests", response_class=HTMLResponse)
def read_tests_ui(request: Request):
    return templates.TemplateResponse("tests.html", {"request": request})


# ==========================================
# 🛠️ API ACTION ROUTES
# ==========================================

@app.post("/pipeline/run")
async def run_pipeline(background_tasks: BackgroundTasks, request: PipelineRunRequest = PipelineRunRequest()):
    pipeline = ACREPipeline(monitor=monitor)
    background_tasks.add_task(
        pipeline.run_pipeline, 
        engagement_id=request.engagement_id, 
        gmail_domain=request.gmail_domain
    )
    return {"status": "accepted", "message": f"Pipeline started for {request.engagement_id}"}

@app.post("/analyze")
async def analyze_email(request: AnalysisRequest):
    secrets_dict = request.secrets.dict() if request.secrets else {}
    context = {"secrets": secrets_dict, "workflowId": request.workflowId, "engagementId": request.engagementId}
    pipeline = ACREPipeline(context_data=context, monitor=monitor)
    payload = request.dict(by_alias=True)
    try:
        result = pipeline.process_message(payload)
        return {"status": "success", "analysisResults": result}
    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "error": str(e)}

@app.post("/ingest/eml")
async def ingest_eml(file: UploadFile = File(...)):
    raw_bytes = await file.read()
    registry = ArtifactRegistry()
    sha256 = registry.compute_string_hash(raw_bytes.decode("utf-8", errors="ignore"))
    # from .storage import R2Storage  <-- Removed
    # key = f"evidence/{file.filename}"
    file_location = os.path.join(EVIDENCE_DIR, file.filename or "unknown_file")
    try:
        # We write directly to the mounted path
        with open(file_location, "wb") as f:
            f.write(raw_bytes)
        
        # Determine relative key for downstream refs
        key = f"evidence/{file.filename}" 
        return {"status": "stored", "key": key, "sha256": sha256}
    except Exception as e:
        app_logger.error(f"Failed to write evidence file: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")

@app.post("/ingest/gmail")
async def ingest_gmail(request: GmailSyncRequest, background_tasks: BackgroundTasks):
    # client = RemoteWorkerClient() 
    logger = app_logger # Use main logger for now
    service_account_json = os.environ.get("GCP_SERVICE_ACCOUNT")
    collector = GmailCollector(service_account_json=service_account_json, logger=logger)
    if not collector.service:
        raise HTTPException(status_code=400, detail="Gmail Auth failed.")
    background_tasks.add_task(collector.sync, request.query, request.engagement_id or "default")
    return {"status": "accepted", "message": "Sync started"}

@app.post("/ingest/attachment")
async def ingest_attachment(request: AttachmentIngestionRequest, background_tasks: BackgroundTasks):
    pipeline = AttachmentPipeline()
    background_tasks.add_task(pipeline.process_file, request.file_path, request.attachment_id, request.session_id, request.engagement_id or "default")
    return {"status": "accepted"}

# Health & Reporting
@app.get("/health", operation_id="health_check")
async def health_check():
    """Report health status of container, secrets, and connections."""
    results = {"secrets": {}, "google": {}, "worker": {}, "status": "ok"}

    # 1. Check Secrets
    required_secrets = [
        "GCP_SERVICE_ACCOUNT",
        "GOOGLE_SCOPES",
        "WORKER_API_KEY",
        "CF_ACCESS_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET",
    ]
    missing = []
    for s in required_secrets:
        val = os.environ.get(s)
        results["secrets"][s] = "present" if val else "missing"
        if not val:
            missing.append(s)

    if missing:
        results["status"] = "warning"
        results["secrets"]["missing"] = missing

    # 2. Check Google Connectivity
    try:
        sa_json = os.environ.get("GCP_SERVICE_ACCOUNT")
        if sa_json:
            # We use a try/except here because instantiating GmailCollector triggers auth
            try:
                collector = GmailCollector(service_account_json=sa_json)
                if collector.service:
                    results["google"]["status"] = "connected"
                else:
                    results["google"]["status"] = "auth_failed"
                    results["status"] = "error"
            except Exception as e:
                # If GmailCollector fails init (e.g. bad JSON)
                results["google"]["status"] = "error" 
                results["google"]["error"] = str(e)
        else:
            results["google"]["status"] = "skipped_no_sa"
    except Exception as e:
        results["google"]["status"] = "error"
        results["google"]["error"] = str(e)
        results["status"] = "error"

    # 3. Check Worker Bridge Connectivity
    try:
        bridge_client = getattr(app.state, "host_client", None)
        if bridge_client:
            results["worker"]["url"] = bridge_client.base_url
            try:
                # Execute simple query via Bridge
                _ = await bridge_client.execute_query("SELECT 1 as healthy")
                results["worker"]["connection"] = "ok"
                results["worker"]["d1_check"] = "pass"
            except Exception as e:
                results["worker"]["connection"] = f"failed: {str(e)}"
                results["worker"]["d1_check"] = "fail"
                results["status"] = "warning"
            results["worker"]["status"] = "configured"
        else:
            results["worker"]["status"] = "client_not_initialized"
            # Not strictly an error if running in standalone mode, but warned
            results["status"] = "warning"
    except Exception as e:
        results["worker"]["status"] = "error"
        results["worker"]["error"] = str(e)
        results["status"] = "error"

    return results

@app.post("/reports/generate")
def generate_report(request: ReportGenRequest):
    reporter = ForensicReporter()
    data = reporter.generate_json_timeline(thread_id=request.thread_id, engagement_id=request.engagement_id)
    reporter.generate_report_markdown(data)
    return {"status": "generated"}

@app.get("/reports/timeline")
def get_timeline():
    path = os.path.join(OUTPUT_DIR, "Reconstructed_Thread.json")
    if os.path.exists(path):
        import json
        with open(path, "r") as f:
            return json.load(f)
    raise HTTPException(404, "Not found")

@app.get("/reports/forensic")
def get_forensic_report():
    path = os.path.join(OUTPUT_DIR, "Forensic_Report.md")
    if os.path.exists(path):
        with open(path, "r") as f:
            return {"content": f.read()}
    raise HTTPException(404, "Not found")

@app.get("/api/tests/stream")
async def stream_tests():
    import subprocess

    from fastapi.responses import StreamingResponse
    async def generator():
        process = subprocess.Popen(
            ["uv", "run", "pytest", "-v", "forensics_fastapi/tests"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, cwd=os.getcwd()
        )
        if process.stdout:
            for line in process.stdout:
                yield line
            process.stdout.close()
        process.wait()
    return StreamingResponse(generator(), media_type="text/plain")


# ==========================================
# 🔌 ROUTER INCLUDES (MUST BE LAST)
# ==========================================
app.include_router(engagements.router)
app.include_router(strategy.router)
app.include_router(container.router)
app.include_router(terminal.router)
# app.include_router(commands.router) # Deprecated in favor of Sandbox SDK
# app.include_router(runtime.router) # Deprecated in favor of Sandbox SDK
app.include_router(sandbox.router)
app.include_router(cli_router.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)