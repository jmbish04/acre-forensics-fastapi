
import { OpenAPIHono, createRoute, z } from '@hono/zod-openapi';
import { ForensicsContainer } from "./controller";

export const containerRouter = new OpenAPIHono<{ Bindings: Env }>();

// Schema Definitions
export const ContainerControlSchema = z.object({
    action: z.enum(["start", "stop", "restart"]),
    name: z.string().optional()
});

export const ProvisionRequestSchema = z.object({
    name: z.string().optional(),
    size: z.string().optional().default("medium"),
    envVars: z.any().optional(),
});

// REST Endpoints

// GET /api/container/status
containerRouter.openapi(
    createRoute({
        method: "get",
        path: "/status",
        responses: {
            200: {
                description: "Get container status",
                content: {
                    "application/json": {
                        schema: z.object({
                            success: z.boolean(),
                            containers: z.array(z.any())
                        })
                    }
                }
            },
            500: { description: "Internal Server Error" }
        }
    }),
    async (c) => {
        try {
            const ctrl = new ForensicsContainer(c.env, { name: c.env.SANDBOX_INSTANCE_NAME });

            // Check health via exec with timeout
            const start = Date.now();
            let res: any = { exitCode: -1 };
            let status = "starting"; // Default to starting if timeout

            try {
                // Timeout promise (3s)
                const timeout = new Promise((_, reject) => setTimeout(() => reject(new Error("Timeout")), 3000));
                // Race exec against timeout
                res = await Promise.race([ctrl.exec("echo ok"), timeout]);
                status = res.exitCode === 0 ? "running" : "error";
            } catch (err: any) {
                // Timeout or exec error -> assume starting/unresponsive but valid container object
                console.log("Status check timed out or failed:", err.message);
                status = "starting"; // Assume starting if timeout
                if (err.message !== "Timeout") {
                    // unexpected error (e.g. 500 from microVM)
                    status = "unresponsive";
                }
            }

            const latency = Date.now() - start;

            const containers = [{
                name: c.env.SANDBOX_INSTANCE_NAME,
                status: status,
                type: "ForensicsContainer",
                created_at: new Date().toISOString(),
                lastPing: status === "running" ? new Date().toISOString() : undefined,
                uptimeSeconds: 3600, // Mocked for now, strictly would need state persistence
                metadata: {
                    binding: "SANDBOX",
                    latencyMs: latency
                }
            }];

            return c.json({ success: true, containers });
        } catch (e: any) {
            return c.json({ success: false, error: e.message }, 500);
        }
    }
);

// GET /api/container/logs
containerRouter.openapi(
    createRoute({
        method: "get",
        path: "/logs",
        request: {
            query: z.object({
                limit: z.string().optional()
            })
        },
        responses: {
            200: {
                description: "Get container logs",
                content: {
                    "application/json": {
                        schema: z.object({
                            logs: z.array(z.string())
                        })
                    }
                }
            }
        }
    }),
    async (c) => {
        try {
            const name = c.env.SANDBOX_INSTANCE_NAME;
            const ctrl = new ForensicsContainer(c.env, { name });
            await ctrl.init();

            // 1. Find the application process (Uvicorn)
            const processes = await ctrl.listProcesses();
            const appProcess = processes.find(p => p.command.includes("uvicorn") && p.command.includes("forensics_fastapi"));

            if (appProcess) {
                // 2. Fetch logs from the process stream
                const { stdout, stderr } = await ctrl.getProcessLogs(appProcess.id);

                const stdoutLogs = stdout.split("\n").filter(l => l.trim()).map(l => `[APP] ${l}`);
                const stderrLogs = stderr.split("\n").filter(l => l.trim()).map(l => `[ERR] ${l}`);

                // Combine and take last 100 lines (or limit query)
                const allLogs = [...stdoutLogs, ...stderrLogs].slice(-100);

                return c.json({
                    logs: [
                        `[${new Date().toISOString()}] [INFO] Attached to process ${appProcess.id}`,
                        ...allLogs
                    ]
                });
            }

            // Fallback: List processes
            const ps = await ctrl.exec("ps aux");
            const logs = [
                `[${new Date().toISOString()}] [INFO] Connected to Sandbox ${name}`,
                `[${new Date().toISOString()}] [WARN] FastAPI process not found. System Process List:`,
                ...(ps.stdout || "").split("\n").map(l => `[SYSTEM] ${l}`).slice(0, 20)
            ];

            return c.json({ logs });
        } catch (e: any) {
            return c.json({ logs: [`[ERROR] Failed to fetch logs: ${e.message}`] });
        }
    }
);

// POST /api/container/control
containerRouter.openapi(
    createRoute({
        method: "post",
        path: "/control",
        request: {
            body: {
                content: {
                    "application/json": {
                        schema: ContainerControlSchema.omit({ name: true })
                    }
                }
            }
        },
        responses: {
            200: {
                description: "Control action result",
                content: {
                    "application/json": {
                        schema: z.object({
                            success: z.boolean(),
                            message: z.string().optional()
                        })
                    }
                }
            }
        }
    }),
    async (c) => {
        // Sandbox is managed by the SDK (auto-sleeps). 
        // For 'stop' we can call destroy()
        const { action } = c.req.valid("json");
        const targetName = c.env.SANDBOX_INSTANCE_NAME;

        if (action === "stop") {
            const ctrl = new ForensicsContainer(c.env, { name: targetName });
            await ctrl.destroy();
            return c.json({ success: true, message: "Sandbox destroyed." });
        }

        return c.json({ success: true, message: "Sandbox state is managed automatically by SDK." });
    }
);

// POST /api/container/provision
containerRouter.openapi(
    createRoute({
        method: "post",
        path: "/provision",
        request: {
            body: {
                content: {
                    "application/json": {
                        schema: ProvisionRequestSchema.omit({ name: true })
                    }
                }
            }
        },
        responses: {
            200: {
                description: "Provisioning started",
                content: {
                    "application/json": {
                        schema: z.object({ success: z.boolean(), message: z.string() })
                    }
                }
            }
        }
    }),
    async (c) => {
        // Strict Single Container
        const targetName = c.env.SANDBOX_INSTANCE_NAME;
        // SDK lazy-provisions on first use. We can force a wake-up.
        const ctrl = new ForensicsContainer(c.env, { name: targetName });
        await ctrl.exec("true");
        return c.json({ success: true, message: "Sandbox " + targetName + " is ready." });
    }
);

// POST /api/container/verify
containerRouter.openapi(
    createRoute({
        method: "post",
        path: "/verify",
        request: {
            body: {
                content: {
                    "application/json": {
                        schema: z.object({}) // No params needed
                    }
                }
            }
        },
        responses: {
            200: {
                description: "Verification results",
                content: {
                    "application/json": {
                        schema: z.object({
                            results: z.any(), // relaxed schema for dynamic results
                            success: z.boolean()
                        })
                    }
                }
            },
            500: { description: "Internal Server Error" }
        }
    }),
    async (c) => {
        try {
            const targetName = c.env.SANDBOX_INSTANCE_NAME;
            const ctrl = new ForensicsContainer(c.env, { name: targetName });

            const command = "python3 /app/forensics_fastapi/scripts/verify_health.py";
            const result = await ctrl.exec(command);

            if (result.exitCode !== 0) {
                return c.json({
                    success: false,
                    error: result.stderr || "Diagnostics script failed",
                    stdout: result.stdout
                }, 500);
            }

            try {
                const parsedResults = JSON.parse(result.stdout);
                return c.json({
                    success: true,
                    results: parsedResults
                });
            } catch (parseErr) {
                return c.json({
                    success: false,
                    error: "Failed to parse diagnostic output",
                    raw: result.stdout
                }, 500);
            }
        } catch (e) {
            return c.json({ success: false, error: String(e) }, 500);
        }
    }
);

// GET /api/container/terminal (Implicitly targets main sandbox)
containerRouter.get(
    "/terminal",
    async (c) => {
        const upgradeHeader = c.req.header("Upgrade");
        if (!upgradeHeader || upgradeHeader !== "websocket") {
            return c.text("Expected Upgrade: websocket", 426);
        }

        const name = c.env.SANDBOX_INSTANCE_NAME;

        try {
            // Use SDK to connect to a WebSocket service running in the sandbox
            const ctrl = new ForensicsContainer(c.env, { name });

            // Connect to port 8080 (assuming terminal service/ttyd is running there)
            // If you are running a custom terminal server, ensure it is started on this port.
            return await ctrl.wsConnect(c.req.raw, 8080);

        } catch (e) {
            console.error("Terminal Connection Error:", e);
            return c.json({ error: String(e) }, 500);
        }
    }
);

// POST /api/container/exec
containerRouter.openapi(
    createRoute({
        method: "post",
        path: "/exec",
        request: {
            body: {
                content: {
                    "application/json": {
                        schema: z.object({
                            command: z.string(),
                            args: z.array(z.string()).optional()
                        })
                    }
                }
            }
        },
        responses: {
            200: {
                description: "Command execution result",
                content: {
                    "application/json": {
                        schema: z.object({
                            stdout: z.string(),
                            stderr: z.string(),
                            exitCode: z.number()
                        })
                    }
                }
            },
            500: { description: "Execution failed" }
        }
    }),
    async (c) => {
        const targetName = c.env.SANDBOX_INSTANCE_NAME;
        const { command, args } = c.req.valid("json");

        try {
            const ctrl = new ForensicsContainer(c.env, { name: targetName });
            const fullCommand = args ? `${command} ${args.join(" ")}` : command;
            const result = await ctrl.exec(fullCommand);
            return c.json(result);
        } catch (e) {
            return c.json({ error: String(e) }, 500);
        }
    }
);

// POST /api/container/exec-python
containerRouter.openapi(
    createRoute({
        method: "post",
        path: "/exec-python",
        request: {
            body: {
                content: {
                    "application/json": {
                        schema: z.object({ code: z.string() })
                    }
                }
            }
        },
        responses: {
            200: {
                description: "Python code execution result",
                content: {
                    "application/json": {
                        schema: z.object({
                            stdout: z.string(),
                            stderr: z.string(),
                            exitCode: z.number()
                        })
                    }
                }
            },
            500: { description: "Execution failed" }
        }
    }),
    async (c) => {
        const targetName = c.env.SANDBOX_INSTANCE_NAME;
        const { code } = c.req.valid("json");

        try {
            const ctrl = new ForensicsContainer(c.env, { name: targetName });

            // Write code to a file to avoid complex escaping in command line
            const filename = `/tmp/script_${Date.now()}.py`;
            await ctrl.writeFile(filename, code);

            const result = await ctrl.exec(`python3 ${filename}`);

            // Cleanup
            // await ctrl.exec(`rm ${filename}`); // Optional

            return c.json(result);
        } catch (e) {
            return c.json({ error: String(e) }, 500);
        }
    }
);
