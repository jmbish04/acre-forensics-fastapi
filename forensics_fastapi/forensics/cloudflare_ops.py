import logging
import os
from typing import Any, Dict, List, Optional

# Configure simple logging to match console.log behavior
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def get_cloudflare_config(config_or_env: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Retrieves Cloudflare configuration from a passed dictionary or environment variables.
    Callers MUST pass the config object or rely on os.environ.
    """

    # Helper to resolve keys from the config dict or os.environ
    def get(key: str, env_key: str) -> Optional[str]:
        val = None
        if config_or_env:
            val = config_or_env.get(key) or config_or_env.get(env_key)

        if val is None and os.environ:
            val = os.environ.get(env_key)

        return val

    account_id = get("cloudflare_account_id", "CLOUDFLARE_ACCOUNT_ID")
    # api_token = None  # disabled generic token

    # Map fields
    d1_id = get("cloudflare_d1_database_id", "CLOUDFLARE_D1_DATABASE_ID")

    vectorize_index = get("cloudflare_vectorize_index", "CLOUDFLARE_VECTORIZE_INDEX_NAME") or get(
        "cloudflare_vectorize_index", "CLOUDFLARE_VECTORIZE_INDEX"
    )

    embedding_model = get(
        "cloudflare_vectorize_embedding_model", "CLOUDFLARE_VECTORIZE_EMBEDDING_MODEL"
    )
    d1_kv_token = get("cloudflare_d1_kv_token", "CLOUDFLARE_D1_KV_TOKEN")

    kv_namespace_id = get("cloudflare_kv_namespace_id", "CLOUDFLARE_KV_NAMESPACE_ID") or get(
        "cloudflare_kv_namespace_id", "CLOUDFLARE_KV_NAMESPACE"
    )

    kv_namespace_agent_memory_id = get(
        "cloudflare_agent_memory_kv_namespace_id", "CLOUDFLARE_AGENT_MEMORY_KV_NAMESPACE_ID"
    ) or get("cloudflare_agent_memory_kv_namespace_id", "CLOUDFLARE_KV_NAMESPACE_AGENT_MEMORY")

    ai_gateway_token = get("cloudflare_ai_gateway_token", "CLOUDFLARE_AI_GATEWAY_TOKEN")
    ai_search_token = get("cloudflare_ai_search_token", "CLOUDFLARE_AI_SEARCH_TOKEN")
    browser_render_token = get("cloudflare_browser_render_token", "CLOUDFLARE_BROWSER_RENDER_TOKEN")
    worker_admin_token = get("cloudflare_worker_admin_token", "CLOUDFLARE_WORKER_ADMIN_TOKEN")

    account_token_admin_token = get(
        "cloudflare_account_token_admin_token", "CLOUDFLARE_ACCOUNT_TOKEN_ADMIN_TOKEN"
    )
    user_token_admin = get("cloudflare_user_token_admin", "CLOUDFLARE_USER_TOKEN_ADMIN")
    zone_dns_routes_token = get(
        "cloudflare_zone_dns_routes_token", "CLOUDFLARE_ZONE_DNS_ROUTES_TOKEN"
    )

    gh_templates_index = get(
        "cloudflare_vectorize_gh_templates_index_name",
        "CLOUDFLARE_VECTORIZE_GH_TEMPLATES_INDEX_NAME",
    )

    # Logic to resolve Worker Script Name
    # 1. Env Var `WORKER_SCRIPT_NAME`
    # 2. Parse from `WORKER_URL` (e.g. https://script-name.subdomain.workers.dev)
    # 3. Default to "acre-forensics-backend"
    worker_script_name = get("worker_script_name", "WORKER_SCRIPT_NAME")
    worker_url = get("worker_url", "WORKER_URL")

    if not worker_script_name:
        if worker_url:
            from urllib.parse import urlparse

            try:
                hostname = urlparse(worker_url).hostname
                if hostname:
                    # e.g. acre-forensics-backend.hacolby.workers.dev -> acre-forensics-backend
                    worker_script_name = hostname.split(".")[0]
            except Exception:
                pass

    if not worker_script_name:
        worker_script_name = "acre-forensics-backend"

    return {
        "accountId": account_id,
        "apiToken": None,  # Explicitly disabled
        "workerScriptName": worker_script_name,
        "workerUrl": worker_url,
        "d1Id": d1_id,
        "vectorizeIndex": vectorize_index,
        "embeddingModel": embedding_model,
        "d1KvToken": d1_kv_token,
        "kvNamespaceId": kv_namespace_id,
        "kvNamespaceAgentMemoryId": kv_namespace_agent_memory_id,
        "aiGatewayToken": ai_gateway_token,
        "aiSearchToken": ai_search_token,
        "browserRenderToken": browser_render_token,
        "workerAdminToken": worker_admin_token,
        "accountTokenAdminToken": account_token_admin_token,
        "userTokenAdmin": user_token_admin,
        "zoneDnsRoutesToken": zone_dns_routes_token,
        "ghTemplatesIndex": gh_templates_index,
        "vectorizeEmbeddingModel": embedding_model,
    }


def fetch_cloudflare(
    path: str,
    method: str = "GET",
    body: Any = None,
    headers: Optional[Dict[str, str]] = None,
    token: Optional[str] = None,
    token_name: Optional[str] = None,
    ignore_errors: Optional[List[int]] = None,
    silent: bool = False,
    env: Optional[Dict[str, Any]] = None,
    expects_json: bool = True,
    **kwargs,
) -> Any:
    """
    Executes a request against the Cloudflare API with intelligent token selection.

    Args:
        path: API path (e.g., '/workers/scripts')
        method: HTTP method (default GET)
        body: Request body (dict for JSON, or raw bytes/files)
        headers: Optional extra headers
        token: Explicit token override
        token_name: Explicit token name override
        ignore_errors: List of status codes to suppress logging for
        silent: If True, suppresses all logs
        env: Optional config dictionary to override environment variables
        expects_json: If True, returns config['result'], else returns the response object
        **kwargs: Passed directly to requests.request (e.g. files, timeout)
    """
    import requests  # Imported locally to keep module clean if unused

    config = get_cloudflare_config(env)

    # Extract config values
    account_id = config.get("accountId")
    browser_render_token = config.get("browserRenderToken")
    d1_kv_token = config.get("d1KvToken")
    ai_gateway_token = config.get("aiGatewayToken")
    user_token_admin = config.get("userTokenAdmin")
    account_token_admin_token = config.get("accountTokenAdminToken")
    zone_dns_routes_token = config.get("zoneDnsRoutesToken")
    worker_admin_token = config.get("workerAdminToken")

    # Token Inference Logic
    if not token:
        if "/browser-rendering" in path:
            token = browser_render_token
            token_name = "CLOUDFLARE_BROWSER_RENDER_TOKEN"
        elif "/d1/" in path or "/storage/kv" in path:
            token = d1_kv_token
            token_name = "CLOUDFLARE_D1_KV_TOKEN"
        elif any(x in path for x in ["/ai/run", "/vectorize", "/ai/v1", "/autorag"]):
            token = ai_gateway_token
            token_name = "CLOUDFLARE_AI_GATEWAY_TOKEN"
        elif "/user/tokens" in path:
            token = user_token_admin
            token_name = "CLOUDFLARE_USER_TOKEN_ADMIN"
        elif "/tokens" in path:
            # Matches /accounts/:id/tokens
            token = account_token_admin_token
            token_name = "CLOUDFLARE_ACCOUNT_TOKEN_ADMIN_TOKEN"
        elif "/zones" in path:
            token = zone_dns_routes_token
            token_name = "CLOUDFLARE_ZONE_DNS_ROUTES_TOKEN"
        elif any(x in path for x in ["/workers/", "/pages", "/queues", "/r2/", "/builds"]):
            token = worker_admin_token
            token_name = "CLOUDFLARE_WORKER_ADMIN_TOKEN"

    token_name = token_name or "UNKNOWN_TOKEN"

    if not account_id or not token:
        # Construct helpful error message
        missing = []
        if not account_id:
            missing.append("CLOUDFLARE_ACCOUNT_ID")
        if not token:
            missing.append("Service-Specific Token (e.g. WORKER_ADMIN_TOKEN)")

        raise ValueError(
            f"Missing configuration for path '{path}': {', '.join(missing)}. "
            "(generic CLOUDFLARE_API_TOKEN is disabled)"
        )

    # URL Construction
    base_url = "https://api.cloudflare.com/client/v4"

    if (
        path.startswith("/accounts")
        or path.startswith("/user")
        or path.startswith("/zones")
        or path.startswith("/memberships")
        or path.startswith("/graphql")
    ):
        url = f"{base_url}{path}"
    else:
        url = f"{base_url}/accounts/{account_id}{path}"

    # Logging
    masked_token = f"{token[:4]}...{token[-4:]}" if token and len(token) > 8 else "MISSING"

    if not silent:
        logger.info(f"\n[CF API] Request: {method} {url}")
        logger.info(f"[CF API] Auth: Using {token_name} ({masked_token})")

    # Header Setup
    final_headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    if headers:
        final_headers.update(headers)

    # Handle Body / JSON
    # If body is a dict and 'files' is not in kwargs, assume JSON
    json_data = None
    data_payload = None

    if body is not None:
        # Check if this looks like a file upload (requests uses 'files' kwarg)
        if "files" in kwargs:
            # If sending files, requests handles Content-Type boundary automatically
            if "Content-Type" in final_headers:
                del final_headers["Content-Type"]
            data_payload = body  # Pass body as 'data' for form fields if needed
        elif isinstance(body, dict):
            json_data = body
        else:
            data_payload = body

    # Execute Request
    try:
        res = requests.request(
            method=method,
            url=url,
            headers=final_headers,
            json=json_data,
            data=data_payload,
            **kwargs,
        )
    except Exception as e:
        raise ConnectionError(f"Failed to connect to Cloudflare API: {str(e)}")

    if not silent:
        logger.info(f"[CF API] Response: {res.status_code} {res.reason}")

    # Error Handling
    if not res.ok:
        error_text = res.text
        should_log = not (ignore_errors and res.status_code in ignore_errors)

        if should_log and not silent:
            logger.error(f"[CF API] Error Body: {error_text}")
        elif not silent:
            logger.info(f"[CF API] (Ignored Error {res.status_code}): {error_text}")

        error_msg = f"Cloudflare API Error: {res.status_code} {res.reason} - {error_text}"

        if res.status_code in [401, 403]:
            error_msg += f" (Used Token: {token_name})"
            logger.warning(
                f"[Auth Error] 401/403 with Token: {token_name} (Masked: {masked_token})"
            )

        raise Exception(error_msg)

    if not expects_json:
        return res

    try:
        json_resp = res.json()
        return json_resp.get("result")
    except ValueError:
        # If response was OK but not JSON (rare for CF API but possible)
        return res.text
