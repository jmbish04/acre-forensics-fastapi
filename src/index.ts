/**
 * src/index.ts
 * Entry point for the Cloudflare Worker hosting the ACRE Forensics Container.
 */
import { 
  getSandbox, 
  proxyToSandbox, 
  Sandbox 
} from "@cloudflare/sandbox";

// Export the Sandbox class so Cloudflare can load the Durable Object
// The name 'ContainerSandboxSDK' MUST match the 'class_name' in wrangler.jsonc
export class ContainerSandboxSDK extends Sandbox {}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // 1. Identify the Sandbox Instance
    // We use a singleton "default" instance for this deployment to keep the cache warm.
    // In a multi-tenant setup, you might use `request.headers.get("X-Engagement-ID")`.
    const sandboxId = env.SANDBOX_INSTANCE_NAME || "default-forensics-sandbox";
    const sandbox = getSandbox(env.CONTAINER_SANDBOX_SDK, sandboxId);

    // 2. Handle System/Health Checks specific to the Worker (optional)
    if (url.pathname === "/worker-health") {
      return new Response("Worker is healthy. Container status unknown.", { status: 200 });
    }

    // 3. Proxy Request to the Python Container
    // The FastAPI server inside the container is listening on port 8000.
    // proxyToSandbox handles the networking magic.
    try {
      // You can inject specific headers here if needed by the Python app
      // request.headers.set("X-Forwarded-Proto", "https");
      
      return await proxyToSandbox(sandbox, request, { 
        port: 8000,
        // Optional: wait for the port to be open (cold start handling)
        requirePortReady: true 
      });

    } catch (e: any) {
      console.error("[Worker] Proxy Error:", e);
      
      // Provide a helpful error if the container is crashing
      if (e.message.includes("connection refused") || e.message.includes("502")) {
        return new Response(
          JSON.stringify({
            error: "Container Unavailable",
            detail: "The Python FastAPI service is not reachable. It may be booting or crashed.",
            tip: "Check logs via 'wrangler tail' or ensure Dockerfile CMD binds to 0.0.0.0"
          }),
          { status: 502, headers: { "Content-Type": "application/json" } }
        );
      }
      
      return new Response(`Internal Proxy Error: ${e.message}`, { status: 500 });
    }
  },
};

// Define the Env interface for TypeScript intellisense
interface Env {
  CONTAINER_SANDBOX_SDK: DurableObjectNamespace<ContainerSandboxSDK>;
  SANDBOX_INSTANCE_NAME?: string;
  [key: string]: any;
}
