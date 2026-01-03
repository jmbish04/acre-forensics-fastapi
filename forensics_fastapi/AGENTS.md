
# Agent Instructions: ACRE Cloudflare Architecture

> **CRITICAL**: The ACRE system has migrated to a **Cloudflare Worker** backend. The local Python code in `src/` is now a *thin client*.

## 1. Golden Rule: "Remote API First"
All data operations, AI inference, and vector search MUST use the central Cloudflare Worker API.
**Do NOT** attempt to connect to SQLite files (`forensics.db`) or call OpenAI interactively from Python.

## 2. Architecture Overview
- **Backend**: `cloudflare_workers/acre-forensics-backend/` (Hono + D1 + R2 + Workers AI)
- **Frontend**: `cloudflare_workers/acre-forensics-backend/client/` (React + Vite)
- **Local Python**: `src/` (Scripts & Notebooks)

## 3. Python Development Guidelines (`src/`)
When writing Python code (e.g., notebooks, scripts, pipelines):

### A. Database Access (D1)
You CANNOT access the database directly via `sqlite3`.
Instead, use the **`ACREClient`** bridge located in `src/remote_api.py`.
```python
from src.remote_api import ACREClient
client = ACREClient()
engagements = client.list_engagements()
```

### B. AI Operations (Workers AI)
Do NOT import `openai` or `langchain` locally. Use `ACREClient` to invoke the purpose designed agents using Cloudflare Agents SDK. If there is no purpose designed agent to process a prompt for a new use case you've been tasked with and you think an agent (cloudflare agents sdk) would be a good fit, you should create one and then update remote_worker_api.py with the new method and import remote_worker_api into the new module you're building. If an agent is not a good fit, you should use the src/core/worker_ai.py module to run a direct worker-ai call. 

#DO NOT USE OPENAI, GEMINI, ANTHROPIC, ETC -- YOU MUST USE A CLOUDFLARE AGENTS SDK AI AGENT SETUP ON THE ACRE BACKEND WORKER OR src/core/worker_ai.py MODULE FOR WORKER AI. 

```python
# GOOD
response = client.run_llm(prompt="Analyze this...")
embeddings = client.generate_embeddings(text="some text")

# BAD
import openai
response = openai.ChatCompletion.create(...)
```

### C. Vector Search (Vectorize)
Do NOT index vectors locally (e.g., `chromadb` or `faiss`). All vectors live in Cloudflare Vectorize.
```python
results = client.vector_search(vector=[0.1, 0.2...])
```

## 4. Schema & Migrations
The Source of Truth for the data model is:
**`cloudflare_workers/acre-forensics-backend/prisma/schema.prisma`**

If you need to change the database structure:
1.  Edit `cloudflare_workers/acre-forensics-backend/prisma/schema.prisma`.
2.  Run `npx prisma migrate dev` (or `wrangler d1 migrations create`).
3.  Deploy the worker.
4.  **Do NOT edit `src/data/schema.prisma`** (it is deprecated).
