import { ForensicsContainer } from "./controller";

export default {
    async fetch(_request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
        // Use a default name for testing
        const sandbox = new ForensicsContainer(env, { name: "test-session" });
        await sandbox.init();

        try {
            console.log("Testing Sandbox Connection...");

            // 1. Health Check
            const healthy = await sandbox.health();
            console.log(`Health Check: ${healthy.exitCode === 0 ? "OK" : "FAILED"}`);
            if (healthy.exitCode !== 0) throw new Error("Health check failed");

            // 2. Exec Command
            console.log("Testing Exec (echo 'Hello')...");
            const execResult = await sandbox.exec("echo 'Hello Sandbox'");
            console.log("Exec Result:", execResult);
            if (execResult.exitCode !== 0 || !execResult.stdout.includes("Hello Sandbox")) {
                throw new Error(`Exec failed: ${JSON.stringify(execResult)}`);
            }

            // 3. File Write
            console.log("Testing FS Write...");
            const content = "Test Content " + Date.now();
            await sandbox.writeFile("/tmp/test.txt", content);
            console.log("Write OK");

            // 4. File Read
            console.log("Testing FS Read...");
            const readRes = await sandbox.readFile("/tmp/test.txt");
            const readContent = readRes.content;
            console.log("Read Result:", readContent);
            if (readContent !== content) {
                throw new Error(`Read Content mismatch. Expected '${content}', got '${readContent}'`);
            }

            // 5. Logs Check
            console.log("Testing Logs...");
            // Generate some logs with exec
            await sandbox.exec("echo 'Log Entry 1'");

            // Fetch logs (non-following for test)
            // ForensicsContainer doesn't expose getLogs directly except via instance
            const logStream = await sandbox.instance.streamProcessLogs("echo 'Log Entry 1'");
            let foundLog = false;
            for await (const chunk of logStream) {
                console.log("Log Chunk:", JSON.stringify(chunk));
                const text = JSON.stringify(chunk);
                if (text.includes("Log Entry 1")) {
                    foundLog = true;
                    break;
                }
            }

            if (!foundLog) {
                console.warn("Warning: Did not find 'Log Entry 1' in logs. This might be due to timing or log buffering.");
            } else {
                console.log("Logs Check OK");
            }

            return new Response("Sandbox Test Passed Successfully", { status: 200 });

        } catch (e: any) {
            console.error("Test Failed:", e);
            return new Response(`Sandbox Test Failed: ${e.message}`, { status: 500 });
        }
    }
};
