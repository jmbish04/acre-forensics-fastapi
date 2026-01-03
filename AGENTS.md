# Agent Instructions: ACRE Forensics FastAPI (Cloudflare Sandbox)

## 1. Project Architecture & Intent
This project runs a specialized **FastAPI** Python application inside a secure **Cloudflare Worker** using the `@cloudflare/sandbox` SDK.
* **Host:** Cloudflare Worker (TypeScript) handles ingress and orchestration.
* **Sandbox (DO):** A Durable Object (`ContainerSandboxSDK`) managing a microVM.
* **Runtime:** The microVM runs a Docker image (`docker.io/cloudflare/sandbox:0.3.3` base) containing the `forensics_fastapi` Python package.

## 2. Documentation & Knowledge Retrieval (CRITICAL)
If you are unsure about Cloudflare specific implementations (Workers, Durable Objects, Vectorize, R2), you **MUST** use the provided documentation tool before hallucinating APIs.

* **Command:** `pnpm exec tsx scripts/ask-cloudflare.ts "Your specific question here"`
* **When to use:**
    * "How do I mount a bucket in sandbox-sdk?"
    * "What is the limit for Durable Object alarms?"
    * "How do I use proxyToSandbox?"

## 3. Implementation Rules

### A. Networking & Proxying
* **Traffic Flow:** External Request -> Worker `src/index.ts` -> `proxyToSandbox` -> MicroVM Port 8000 -> FastAPI (`uvicorn`).
* **Host Binding:** The Python FastAPI app **MUST** bind to `0.0.0.0`. Binding to `127.0.0.1` inside the container will cause 502 Bad Gateway errors.
* **Proxy Utility:** Always use the SDK's `proxyToSandbox` for HTTP traffic. Do not manually `fetch()` the internal IP unless dealing with specific raw sockets.

### B. The `ContainerSandboxSDK` Class
* **Export:** You must export a class that extends `Sandbox` from `@cloudflare/sandbox` in `src/index.ts`.
* **Binding:** The `wrangler.jsonc` file expects the class name `ContainerSandboxSDK`.
* **Persistence:** Use a **Named Instance** (e.g., `"default"`) when calling `getSandbox` to ensure the container stays "warm" and retains state between requests.

### C. File System & R2 Integration
* **Mounts:** R2 buckets (`R2_EVIDENCE`, `R2_DOC_PAGES`) are mounted into the container via the `Sandbox` configuration.
* **Paths:** The Python code expects evidence at `/workspace/src/forensics/evidence`. Ensure the boot script or init logic creates necessary directories if R2 is not mounted (e.g., in dev mode).

## 4. Development Workflow
1.  **Dependency Management:**
    * Python: `pyproject.toml` / `uv.lock`.
    * TypeScript: `package.json` / `pnpm`.
2.  **Testing Connection:**
    * Use `src/sandboxsdk/test-connection.ts` logic to verify the container is responding before writing complex features.
3.  **Logs:**
    * Container logs are accessible via `sandbox.getProcessLogs(pid)`.
    * Worker logs are visible via `wrangler tail`.

## 5. Common Pitfalls
* **Cold Starts:** The container takes a few seconds to boot. The `proxyToSandbox` function handles some waiting, but your code should be resilient to initial timeouts.
* **Secrets:** Secrets like `GCP_SERVICE_ACCOUNT` are injected into the container environment. Ensure they are present in `.dev.vars` for local development.
