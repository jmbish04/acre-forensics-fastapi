import os

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(".dev.vars", override=True)

from pathlib import Path

# Filesystem Configuration
# Defaults to /workspace for Sandbox compatibility, but respects env var or falls back to /app or /tmp if read-only
_explicit_workspace = os.getenv("WORKSPACE_DIR")
BASE_DIR = Path(_explicit_workspace) if _explicit_workspace else Path("/workspace")

# Safety Check: If strictly default /workspace and it's not writable, fallback to /tmp
# We only do this if the user didn't explicitly ask for a specific dir.
if not _explicit_workspace:
    try:
        # Check if exists and writable, or if parent is writable if it doesn't exist
        if BASE_DIR.exists():
            if not os.access(BASE_DIR, os.W_OK):
                import tempfile

                BASE_DIR = Path(tempfile.gettempdir()) / "acre-forensics"
        else:
            # If it doesn't exist, can we write to root? Unlikely.
            # In containers, /workspace usually exists. If not, we surely can't create it at /
            import tempfile

            BASE_DIR = Path(tempfile.gettempdir()) / "acre-forensics"
    except Exception:
        # Fallback on any error
        import tempfile

        BASE_DIR = Path(tempfile.gettempdir()) / "acre-forensics"

DATA_DIR = BASE_DIR / "src" / "data"

def _clean_path(env_key, default):
    """Strip leading slashes to ensure safe joining with BASE_DIR"""
    val = os.getenv(env_key, default)
    # If the path is intended to be absolute (like /root for NLTK), we keep it,
    # but for workspace-relative paths, we strip.
    # However, controller.ts mounts them relative to workspace (usually).
    # R2_EVIDENCE_PATH is typically "/r2/evidence", so we strip leading / to append to /workspace
    return val.lstrip("/")

DATA_DIR = BASE_DIR / "src" / "data"

# Dynamic Paths based on Env Injection (matching controller.ts mounts)
EVIDENCE_DIR = BASE_DIR / _clean_path("R2_EVIDENCE_PATH", "src/forensics/evidence")
OUTPUT_DIR = BASE_DIR / _clean_path("R2_REPORTS_PATH", "src/reports/output_final")
DOCS_DIR = BASE_DIR / _clean_path("R2_DOC_PAGES_PATH", "src/data/doc_pages")

DB_PATH = DATA_DIR / "forensics.db"
CREDENTIALS_DIR = BASE_DIR / ".credentials"


# Cloudflare Configuration
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
# Support both token names
CF_AUTH_TOKEN = (
    os.getenv("CLOUDFLARE_AUTH_TOKEN")
    or os.getenv("CLOUDFLARE_API_TOKEN")
    or os.getenv("CLOUDFLARE_AI_SEARCH_TOKEN", "").strip()
)
CF_MODEL_STRUCTURED = os.getenv(
    "CLOUDFLARE_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
).strip()
CF_MODEL_REASONING = "@cf/openai/gpt-oss-120b"
CF_MODEL_EMBEDDING = "@cf/baai/bge-base-en-v1.5"
CF_MODEL_RERANK = "@cf/baai/bge-reranker-base"

# RAG Configuration
RAG_NAME = os.getenv("CLOUDFLARE_RAG_NAME", "mr-roofing-artifacts-dec-2025")

# Database Configuration
# DEPRECATED: Direct DB Access
# DB_CONFIG = { ... }

# Worker Bridge Configuration
# We favor WORKER_URL which is injected by the Host into the container
HOST_API_URL = os.environ.get("HOST_API_URL") or os.environ.get(
    "WORKER_URL", "https://acre-forensics-backend.hacolby.workers.dev"
)
# The Host injects WORKER_API_KEY as the secret
INTERNAL_SERVICE_KEY = os.environ.get("WORKER_API_KEY", "dev-secret")


# R2 Configuration
R2_EVIDENCE_BUCKET_NAME = os.getenv("R2_EVIDENCE_BUCKET_NAME", "acre-forensics-evidence")
R2_DOC_PAGES_BUCKET_NAME = os.getenv("R2_DOC_PAGES_BUCKET_NAME", "acre-forensics-doc-pages")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL")


# Contractor Details
CONTRACTOR_INFO = {
    "name": "MR ROOFING INC",
    "address": "101 FIRST STREET, SOUTH SAN FRANCISCO, CA 94080",
    "phone": "(650) 872-3232",
    "license_number": "566386",
    "license_status": "Current and Active",
    "entity_type": "Corporation",
    "classifications": ["C39 - ROOFING", "C46 - SOLAR", "C10 - ELECTRICAL"],
    "bond_info": {
        "company": "MERCHANTS BONDING COMPANY (MUTUAL)",
        "number": "100340905",
        "amount": "$25,000",
        "effective_date": "02/03/2024",
    },
    "workers_comp": {
        "policy": "WC127921201",
        "effective_date": "07/01/2024",
        "expire_date": "12/31/2025",
    },
}

# Client Details
CLIENT_INFO = {
    "names": "Justin Bishop and Jasnon Owyong",
    "property_address": "126 Colby Street, San Francisco, CA 94134",
}
