import {
    getSandbox,
    type Sandbox,
    type SandboxOptions,
    type Process,
    type ExecOptions,
    type ExecResult,
    type ProcessOptions,
    type CreateContextOptions,
    type CodeContext,
    type RunCodeOptions,
    type ExecutionResult
} from "@cloudflare/sandbox";
import type {
    ForensicsAnalysisResponse,
    WriteFileResult,
    ReadFileResult
} from "./types";




/**
 * Configuration for the Forensics Container.
 */
export interface ForensicsConfig {
    /** Name/ID of the sandbox session (e.g., 'engagement-123') */
    name: string;
    /** Environment variables to inject into the container */
    secrets?: Record<string, string>;
}

export interface CliResult {
    success: boolean;
    stdout: string;
    stderr: string;
    exitCode: number;
}

/**
 * Unified Controller for the Forensics FastAPI Container.
 * Handles CLI execution, Server lifecycle, Filesystem operations, and Forensic pipelines.
 */
export class ForensicsContainer {
    private sandbox: Sandbox;
    private env: Env;
    public readonly name: string;

    // Configured paths and ports
    private HTTP_PORT: number;
    private R2_EVIDENCE_PATH: string;
    private R2_DOC_PAGES_PATH: string;
    private R2_DOC_AI_SEARCH_PATH: string;
    private R2_REPORTS_PATH: string;
    private R2_SYS_MISC_PATH: string;

    // Constants based on Python module structure
    private readonly CLI_MODULE = "forensics_fastapi.cli";
    private readonly API_MODULE = "forensics_fastapi.forensics.api:app";
    private readonly WORK_DIR = "/workspace";
    private readonly SYS_MISC_DIR = "/root";

    constructor(env: Env, config: ForensicsConfig) {
        this.env = env;

        // Resolve effective container name based on consolidation strategy
        // Resolve effective container name based on consolidation strategy
        if (config.name && config.name.length > 0) {
            this.name = config.name;
        } else if (env.HEALTH_SANDBOX_NAME) {
            // Default to health sandbox if no name provided (often used in tests)
            this.name = env.HEALTH_SANDBOX_NAME;
        } else {
            // Fallback to instance name or explicit default
            this.name = env.SANDBOX_INSTANCE_NAME || "default-forensics-sandbox";
        }

        // Final safety check to satisfy "1-63 characters" constraint
        if (!this.name || this.name.trim().length === 0) {
            this.name = "default-sandbox";
        }

        // Default to 8000 if not set, avoiding reserved port 3000
        this.HTTP_PORT = env.CONTAINER_HTTP_PORT || 8000;

        // Sanitize paths to ensure they are absolute within the container but relative for R2 mapping if needed
        const sanitizePath = (p: string) => `${this.WORK_DIR}/${(p || '').replace(this.WORK_DIR, '').replace(/^\/+/, '')}`;
        const sanitizeSysMiscPath = (p: string) => `${this.SYS_MISC_DIR}/${(p || '').replace(this.SYS_MISC_DIR, '').replace(/^\/+/, '')}`;

        this.R2_EVIDENCE_PATH = sanitizePath(env.R2_EVIDENCE_PATH);
        this.R2_DOC_PAGES_PATH = sanitizePath(env.R2_DOC_PAGES_PATH);
        this.R2_DOC_AI_SEARCH_PATH = sanitizePath(env.R2_DOC_AI_SEARCH_PATH);
        this.R2_REPORTS_PATH = sanitizePath(env.R2_REPORTS_PATH);
        this.R2_SYS_MISC_PATH = sanitizeSysMiscPath(env.R2_SYS_MISC_PATH);

        const options: SandboxOptions = {
            // Lowercase sandbox IDs for preview URL compatibility (DNS standards)
            normalizeId: true,
            // Sleep after 10 minutes of inactivity
            sleepAfter: env.CONTAINER_SLEEP_AFTER || "10m",
            keepAlive: env.CONTAINER_KEEP_ALIVE || false,
            containerTimeouts: {
                instanceGetTimeoutMS: env.CONTAINER_INSTANCE_TIMEOUT_MS || 60000,
                portReadyTimeoutMS: env.CONTAINER_INSTANCE_PORT_READY_TIMEOUT_MS || 120000
            }
        };

        try {
            if (env.CONTAINER_SANDBOX_SDK) {
                this.sandbox = getSandbox(env.CONTAINER_SANDBOX_SDK, this.name, options);
            } else {
                console.warn(`[ForensicsContainer] CONTAINER_SANDBOX_SDK binding missing. Using Mock Mode.`);
                // @ts-ignore
                this.sandbox = null;
            }
        } catch (error) {
            console.error(`Failed to create sandbox: ${JSON.stringify(error)}`);
            throw error;
        }
    }

    /**
     * Get underlying Sandbox instance for advanced use.
     */
    get instance(): Sandbox {
        return this.sandbox;
    }

    /**
     * Initializes the container environment.
     * Injects secrets, mounts R2 buckets, and starts the FastAPI server.
     */
    async init(hostname?: string): Promise<void> {
        if (!this.sandbox) {
            console.log(`[Mock] init called - No Sandbox Binding`);
            return;
        }

        // Optimization: Check if already running to reuse instance
        try {
            const processes = await this.sandbox.listProcesses();
            // Check for the specific uvicorn process we start
            // @ts-ignore - SDK type definition might be missing cmdline or command depending on version
            const isRunning = processes.some((p: any) => {
                const cmd = p.cmdline || p.command || "";
                if (Array.isArray(cmd)) {
                    return cmd.some((arg: string) => arg.includes("uvicorn") && arg.includes(this.API_MODULE));
                }
                return typeof cmd === "string" && cmd.includes("uvicorn") && cmd.includes(this.API_MODULE);
            });

            if (isRunning) {
                console.log(`[ForensicsContainer] Sandbox '${this.name}' already active with API server. Skipping full init.`);
                return;
            }
        } catch (e) {
            console.warn(`[ForensicsContainer] Failed to check existing processes, proceeding with full init. Error: ${e}`);
        }

        // 1. Inject Secrets
        const secrets = this.configSecrets || this.getEnvSecrets();
        await this.sandbox.setEnvVars({
            ...secrets,
            "PYTHONUNBUFFERED": "1",
            "PORT": this.HTTP_PORT.toString()
        });

        // 2. Mount R2 Buckets (Requires FUSE support/Production)
        await this.safeMount(this.env.R2_EVIDENCE_BUCKET_NAME, this.R2_EVIDENCE_PATH);
        await this.safeMount(this.env.R2_DOC_PAGES_BUCKET_NAME, this.R2_DOC_PAGES_PATH);
        await this.safeMount(this.env.R2_DOC_AI_SEARCH_BUCKET_NAME, this.R2_DOC_AI_SEARCH_PATH);
        await this.safeMount(this.env.R2_REPORTS_BUCKET_NAME, this.R2_REPORTS_PATH);
        // Mount NLTK cache to /root which is one of the default search paths
        await this.safeMount(this.env.R2_SYS_MISC_BUCKET_NAME, this.R2_SYS_MISC_PATH);

        // 3. Set NLTK Environment Variable (Explicitly)
        await this.sandbox.setEnvVars({
            ...secrets,
            "PYTHONUNBUFFERED": "1",
            "PORT": this.HTTP_PORT.toString(),
            "NLTK_DATA": `${this.R2_SYS_MISC_PATH}/nltk_data`
        });

        // 4. Ensure FastAPI Server is Running & Exposed
        await this.startServer(hostname);
    }

    // =========================================================================
    // ⚙️ GENERIC COMMANDS API (Wrappers)
    // =========================================================================

    async destroy(): Promise<void> {
        return this.sandbox.destroy();
    }

    async wsConnect(request: Request, port: number): Promise<Response> {
        if (!this.sandbox) {
            return new Response("Mock WS Connected", { status: 101, webSocket: null as any });
        }
        return this.sandbox.wsConnect(request, port);
    }

    async exec(command: string, options?: ExecOptions): Promise<ExecResult> {
        if (!this.sandbox) {
            return {
                success: true,
                stdout: "Mock Output",
                stderr: "",
                exitCode: 0,
                command: command,
                duration: 0,
                timestamp: Date.now().toString()
            };
        }
        return this.sandbox.exec(command, options);
    }

    async execStream(command: string, options?: ExecOptions): Promise<ReadableStream> {
        return this.sandbox.execStream(command, options);
    }

    async writeFile(path: string, content: string | Uint8Array, options?: { encoding?: 'base64' | 'utf-8' }): Promise<WriteFileResult> {
        // If content is Uint8Array, convert to base64 and force encoding
        if (content instanceof Uint8Array) {
            const base64 = this.arrayBufferToBase64(content.buffer as ArrayBuffer);
            return this.sandbox.writeFile(path, base64, { encoding: 'base64' });
        }
        return this.sandbox.writeFile(path, content, options);
    }

    async readFile(path: string, options?: { encoding?: 'base64' | 'utf-8' }): Promise<ReadFileResult> {
        return this.sandbox.readFile(path, options);
    }

    async startProcess(command: string, options?: ProcessOptions): Promise<Process> {
        return this.sandbox.startProcess(command, options);
    }

    async listProcesses(): Promise<Process[]> {
        if (!this.sandbox) {
            return [{ id: "mock-1", pid: 123, command: "python -m uvicorn " + this.API_MODULE, started: "" } as any];
        }
        return await this.sandbox.listProcesses();
    }

    async getProcess(processId: string): Promise<Process | undefined> {
        const processes = await this.listProcesses();
        return processes.find(p => p.id === processId);
    }

    async killProcess(processId: string, signal?: string): Promise<void> {
        return this.sandbox.killProcess(processId, signal);
    }

    async killAllProcesses(): Promise<void> {
        await this.sandbox.killAllProcesses();
    }

    async streamProcessLogs(processId: string): Promise<ReadableStream> {
        return this.sandbox.streamProcessLogs(processId);
    }

    async getProcessLogs(processId: string): Promise<{ stdout: string; stderr: string; processId: string }> {
        if (!this.sandbox) {
            return { stdout: "Mock Log 1\nMock Log 2", stderr: "", processId };
        }
        return this.sandbox.getProcessLogs(processId);
    }

    // =========================================================================
    // 🐍 CODE INTERPRETER API (Wrappers)
    // =========================================================================

    async createCodeContext(options?: CreateContextOptions): Promise<CodeContext> {
        return this.sandbox.createCodeContext(options);
    }

    async runCode(code: string, options?: RunCodeOptions): Promise<ExecutionResult> {
        return this.sandbox.runCode(code, options);
    }

    async listCodeContexts(): Promise<CodeContext[]> {
        return this.sandbox.listCodeContexts();
    }

    async deleteCodeContext(contextId: string): Promise<void> {
        return this.sandbox.deleteCodeContext(contextId);
    }

    // =========================================================================
    // 🛠️ SPECIFIC FORENSICS CLI INTEGRATIONS
    // =========================================================================

    private async runMainCli(command: string, flags: string[] = []): Promise<CliResult> {
        const cmdStr = `python -m ${this.CLI_MODULE} ${command} ${flags.join(" ")}`;
        console.log(`[Sandbox:${this.name}] Executing CLI: ${cmdStr}`);

        const result = await this.exec(cmdStr, { cwd: this.WORK_DIR });

        return {
            success: result.success,
            stdout: result.stdout,
            stderr: result.stderr,
            exitCode: result.exitCode
        };
    }

    private async connectCliWs(method: string): Promise<WebSocket> {
        if (!this.sandbox) {
            throw new Error("Sandbox not initialized");
        }

        // Construct the WebSocket URL path
        const path = `/ws/container/sandbox/cli/${method}`;
        const url = `http://localhost:${this.HTTP_PORT}${path}`; // wsConnect handles the protocol

        // Create a fake request to trigger the upgrade
        const request = new Request(url, {
            headers: {
                "Upgrade": "websocket",
                "Connection": "Upgrade",
                "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
                "Sec-WebSocket-Version": "13"
            }
        });

        const response = await this.sandbox.wsConnect(request, this.HTTP_PORT);

        if (response.status !== 101 || !response.webSocket) {
            throw new Error(`Failed to establish WebSocket connection: ${response.status} ${response.statusText}`);
        }

        const ws = response.webSocket;
        ws.accept();
        return ws;
    }

    /**
     * Executes a CLI command via WebSocket and aggregates the result.
     * Useful for one-shot commands like health, sysinfo, or short scans.
     */
    private async runCliCommandWs(method: string, payload: any = {}): Promise<CliResult> {
        const ws = await this.connectCliWs(method);

        return new Promise<CliResult>((resolve, reject) => {
            let stdout = "";
            let stderr = "";
            let exitCode = 0;
            let completed = false;

            ws.addEventListener("message", (event) => {
                if (typeof event.data === "string") {
                    try {
                        const msg = JSON.parse(event.data);
                        // Handle standard message types from cli_router
                        switch (msg.type) {
                            case "log":
                            case "stream":
                                stdout += (msg.content || "") + "\n";
                                break;
                            case "error":
                                stderr += (msg.content || "") + "\n";
                                break;
                            case `${method}_result`: // e.g. health_result, sysinfo_result
                            case "result":
                                stdout += JSON.stringify(msg.data || msg.content) + "\n";
                                break;
                            case "scan_complete":
                            case "complete":
                            case "end":
                                completed = true;
                                if (msg.exit_code !== undefined) exitCode = msg.exit_code;
                                ws.close();
                                resolve({
                                    success: exitCode === 0,
                                    stdout: stdout.trim(),
                                    stderr: stderr.trim(),
                                    exitCode
                                });
                                break;
                            default:
                                // Fallback for raw messages
                                // console.log("Unknown WS message:", msg);
                                break;
                        }
                    } catch (e) {
                        // Non-JSON message? Treat as stdout
                        stdout += event.data + "\n";
                    }
                }
            });

            ws.addEventListener("close", () => {
                if (!completed) {
                    resolve({
                        success: exitCode === 0,
                        stdout: stdout.trim(),
                        stderr: stderr.trim(),
                        exitCode
                    });
                }
            });

            ws.addEventListener("error", (err) => {
                console.error("WS Error:", err);
                reject(err);
            });

            // Send initial payload
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify(payload));
            } else {
                ws.addEventListener("open", () => {
                    ws.send(JSON.stringify(payload));
                });
            }
        });
    }

    private async runModule(module: string, input: any): Promise<CliResult> {
        const inputJson = JSON.stringify(input);
        const escapedJson = inputJson.replace(/'/g, "'\\''");
        const command = `python3 -m ${module} --json '${escapedJson}'`;
        console.log(`[Sandbox:${this.name}] Executing Module: ${module}`);

        try {
            const result = await this.exec(command, { cwd: this.WORK_DIR });
            return {
                success: result.success,
                stdout: result.stdout || "",
                stderr: result.stderr || "",
                exitCode: result.exitCode ?? 0
            };
        } catch (e: any) {
            console.error("Sandbox exec error:", e);
            throw new Error(`Sandbox execution failed: ${e.message}`);
        }
    }

    async scan(target: string = "all", autoFix: boolean = false): Promise<CliResult> {
        const payload = { target, auto_fix: autoFix };
        // Use WS implementation
        try {
            return await this.runCliCommandWs("scan", payload);
        } catch (e) {
            console.error("WS Scan failed, falling back to CLI", e);
            // Fallback to CLI if WS fails (optional, or remove fallback)
            const flags = [];
            if (target) flags.push(`--target "${target}"`);
            if (autoFix) flags.push("--auto-fix");
            return this.runMainCli("scan", flags);
        }
    }

    async health(): Promise<CliResult> {
        try {
            return await this.runCliCommandWs("health");
        } catch (e) {
            console.warn("WS health check failed, using fallback:", e);
            return this.runMainCli("health");
        }
    }

    async sysinfo(): Promise<any> {
        let result: CliResult;
        try {
            result = await this.runCliCommandWs("sysinfo");
        } catch (e) {
            console.warn("WS sysinfo failed, using fallback:", e);
            result = await this.runMainCli("sysinfo");
        }

        if (result.success) {
            try {
                // If the stdout contains just the JSON, parse it.
                // Note: runCliCommandWs implementation accumulates standard output. 
                // For sysinfo, the websocket streams the JSON result as a 'sysinfo_result' type 
                // which gets added to stdout as stringified JSON one line per message.
                // We might need to handle the case where we get multiple lines (logs + result).

                // Regex to find the JSON object? Or just try parsing the last line?
                // The current runCliCommandWs logic appends "JSON.stringify(msg.data) + \n" for results.
                // So parsing result.stdout might fail if there are logs before it.
                // For sysinfo, we expect a clean JSON object. 

                // Let's attempt to parse the *last* non-empty line if full parse fails.
                try {
                    return JSON.parse(result.stdout);
                } catch {
                    const lines = result.stdout.trim().split("\n");
                    const lastLine = lines[lines.length - 1];
                    return JSON.parse(lastLine);
                }
            } catch (e) {
                return { error: "Failed to parse sysinfo JSON", raw: result.stdout };
            }
        }
        throw new Error(`Sysinfo failed: ${result.stderr}`);
    }

    async streamCliCommand(command: string, flags: string[] = []): Promise<ReadableStream> {
        const cmdStr = `python -m ${this.CLI_MODULE} ${command} ${flags.join(" ")}`;
        return await this.execStream(cmdStr, { cwd: this.WORK_DIR });
    }

    // =========================================================================
    // 🔍 FORENSIC PIPELINE OPERATIONS
    // =========================================================================

    async analyzeAttachment(attachmentId: string, fileKey: string) {
        const result = await this.runModule("forensics_fastapi.forensics.attachments.pipeline", {
            action: "analyze",
            attachmentId,
            fileKey
        });
        if (result.exitCode !== 0) throw new Error(`Attachment analysis failed: ${result.stderr}`);
        try {
            return JSON.parse(result.stdout);
        } catch (e) {
            return { stdout: result.stdout, raw: true };
        }
    }

    async analyzeEmail(messageId: string | object): Promise<ForensicsAnalysisResponse> {
        let payload: any = {};
        if (typeof messageId === 'string') {
            payload = { action: "analyze", messageId };
        } else {
            payload = { action: "analyze", ...messageId };
        }
        const result = await this.runModule("forensics_fastapi.forensics.email.pipeline", payload);
        if (result.exitCode !== 0) throw new Error(`Email analysis failed: ${result.stderr}`);
        return JSON.parse(result.stdout);
    }

    async ingestEmlFile(fileName: string, fileContent: ArrayBuffer) {
        const result = await this.runModule("forensics_fastapi.forensics.email.pipeline", {
            action: "ingest",
            fileName,
            fileContent: this.arrayBufferToBase64(fileContent)
        });
        if (result.exitCode !== 0) throw new Error(`Ingest failed: ${result.stderr}`);
        return JSON.parse(result.stdout);
    }

    async getTimeline() {
        const result = await this.runModule("forensics_fastapi.forensics.timeline.pipeline", {});
        if (result.exitCode !== 0) throw new Error(`Timeline retrieval failed: ${result.stderr}`);
        try {
            return JSON.parse(result.stdout);
        } catch {
            return result.stdout;
        }
    }

    async getForensicReport(): Promise<string> {
        const result = await this.runModule("forensics_fastapi.forensics.report.pipeline", {});
        if (result.exitCode !== 0) throw new Error(`Report generation failed: ${result.stderr}`);
        return result.stdout;
    }

    async runPipeline() {
        return await this.runModule("forensics_fastapi.forensics.pipeline", {});
    }

    async ingestGmail(engagementId: string = "default", query?: string): Promise<CliResult> {
        return await this.runModule("forensics_fastapi.forensics.pipeline", {
            action: "ingest_gmail",
            engagementId,
            query
        });
    }

    async runTests() {
        return await this.runModule("forensics_fastapi.scripts.verify_health", {});
    }

    // =========================================================================
    // 🌐 SERVER LIFECYCLE (FastAPI)
    // =========================================================================

    async startServer(hostname?: string): Promise<{ url: string; pid: number }> {
        if (!this.sandbox) {
            return { url: "http://mock-sandbox-url", pid: 9999 };
        }
        const processes = await this.listProcesses();
        const existing = processes.find(p => p.command.includes("uvicorn") && p.command.includes(this.API_MODULE));

        if (existing) {
            console.log(`[Sandbox:${this.name}] Server already running (PID: ${existing.pid})`);
            let url = "";
            if (hostname) {
                const exposed = await this.sandbox.exposePort(this.HTTP_PORT, {
                    hostname,
                    name: "http"
                });
                url = exposed.url;
            }
            return { url, pid: existing.pid || 0 };
        }

        console.log(`[Sandbox:${this.name}] Starting FastAPI on port ${this.HTTP_PORT}...`);
        const server = await this.startProcess(
            `python -m uvicorn ${this.API_MODULE} --host 0.0.0.0 --port ${this.HTTP_PORT}`,
            {
                cwd: this.WORK_DIR,
                env: { "PORT": this.HTTP_PORT.toString() }
            }
        );

        await this.waitForPortInternal(this.HTTP_PORT, server.pid);

        let url = `http://localhost:${this.HTTP_PORT}`;
        if (hostname) {
            const exposed = await this.sandbox.exposePort(this.HTTP_PORT, {
                hostname,
                name: "api"
            });
            url = exposed.url;
        }

        return { url, pid: server.pid || 0 };
    }

    private async waitForPortInternal(port: number, processId?: number, retries = 60): Promise<void> {
        for (let i = 0; i < retries; i++) {
            // 1. Fast fail if process died
            if (processId) {
                try {
                    const processes = await this.listProcesses();
                    const proc = processes.find(p => p.pid === processId);
                    if (!proc) {
                        throw new Error(`Server process (PID ${processId}) died unexpectedly during startup.`);
                    }
                } catch (e: any) {
                    // Only throw if it's our specific "died" error, otherwise log and continue
                    // We don't want a single 500 on listProcesses to kill the wait loop if the server is just busy
                    if (e.message && e.message.includes("died unexpectedly")) throw e;
                    console.warn(`[waitForPort] listProcesses transient failure: ${e.message}`);
                }
            }

            // 2. Check Port
            try {
                const result = await this.exec(`nc -z localhost ${port}`);
                if (result.exitCode === 0) return;
            } catch (e: any) {
                console.warn(`[waitForPort] nc execution failure: ${e.message}`);
                // Continue waiting, maybe transient
            }

            await new Promise(resolve => setTimeout(resolve, 1000));
        }
        throw new Error(`Timeout waiting for port ${port}`);
    }

    async stopServer(): Promise<void> {
        const processes = await this.listProcesses();
        const server = processes.find(p => p.command.includes("uvicorn"));
        if (server) {
            await this.killProcess(server.id);
        }
    }

    // =========================================================================
    // 📂 UTILITIES & HELPERS
    // =========================================================================

    async uploadEvidence(fileName: string, content: ArrayBuffer): Promise<string> {
        const path = `${this.R2_EVIDENCE_PATH.replace(/\/+$/, '')}/${fileName}`;
        const base64 = this.arrayBufferToBase64(content);
        await this.sandbox.writeFile(path, base64, { encoding: "base64" });
        return path;
    }

    async downloadReport(reportName: string = "Forensic_Report.md"): Promise<string> {
        const path = `${this.R2_REPORTS_PATH.replace(/\/+$/, '')}/${reportName}`;
        const file = await this.sandbox.readFile(path);
        return file.content;
    }

    private async safeMount(bucketName: string, path: string): Promise<void> {
        if (!bucketName) return;
        try {
            await this.sandbox.mountBucket(bucketName, path, {
                endpoint: this.env.R2_ENDPOINT_URL,
                provider: 'r2'
            });
        } catch (e: any) {
            console.warn(`Bucket mount failed for ${bucketName} (likely dev mode):`, e.message);
        }
    }

    private get configSecrets(): Record<string, string> | undefined {
        return undefined;
    }

    private getEnvSecrets(): Record<string, string> {
        const secrets: Record<string, string> = {};
        for (const key of Object.keys(this.env)) {
            const val = (this.env as any)[key];
            if (typeof val === 'string') {
                secrets[key] = val;
            }
        }
        return secrets;
    }

    private arrayBufferToBase64(buffer: ArrayBuffer): string {
        let binary = '';
        const bytes = new Uint8Array(buffer);
        const len = bytes.byteLength;
        for (let i = 0; i < len; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary);
    }
}