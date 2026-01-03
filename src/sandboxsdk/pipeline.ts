import { createDbClient } from "../db";
import { messages, messageContexts } from "../db/schema.d1";
import { eq } from "drizzle-orm";
// import { ForensicsJob } from "./types";
import { ForensicsContainer } from "./controller";

export type ForensicsJob = {
    engagementId: string;
    emailId: string;
    source: string;
    payload: any;
    createdAt: string;
};

export class ForensicsPipeline {
    env: Env;

    constructor(env: Env) {
        this.env = env;
    }

    /**
     * Enqueue email for forensics processing
     */
    async enqueueEmailForAnalysis(emailId: string, engagementId: string, emailData: any) {
        const job: ForensicsJob = {
            engagementId,
            emailId,
            source: "gmail",
            payload: emailData,
            createdAt: new Date().toISOString()
        };

        if (this.env.FORENSIC_ANALYSIS_QUEUE) {
            await this.env.FORENSIC_ANALYSIS_QUEUE.send(job);
        } else {
            console.error("FORENSIC_ANALYSIS_QUEUE not bound");
            throw new Error("Queue not configured");
        }
    }

    /**
     * Process a single forensics job (called by queue consumer)
     */
    async processJob(job: ForensicsJob) {
        try {
            console.log(`Processing job for email ${job.emailId} (Engagement: ${job.engagementId})`);

            // 1. Initialize Controller
            // This abstracts away the Sandbox ID resolution, options, and connectivity
            const forensics = new ForensicsContainer(this.env, {
                name: this.env.SANDBOX_INSTANCE_NAME
            });

            // 2. Prepare Container
            // Ensures secrets are injected and R2 buckets are mounted (if in production)
            await forensics.init();

            // 3. Execute Analysis
            // Runs `python -m forensics_fastapi.forensics.email.pipeline --json ...` inside the container
            // and returns the parsed JSON result.
            const analysisData = await forensics.analyzeEmail(job.emailId);

            // 4. Store results in D1
            const db = createDbClient(this.env);

            try {
                const msg = await db.select().from(messages).where(eq(messages.messageId, job.emailId)).get();

                if (msg) {
                    // Update field on Message directly: status & engagementId
                    await db.update(messages)
                        .set({
                            status: "PROCESSED",
                            engagementId: job.engagementId
                        })
                        .where(eq(messages.id, msg.id))
                        .run();

                    // Update or Create Context with analysis
                    const existingCtx = await db.select().from(messageContexts).where(eq(messageContexts.messageId, msg.messageId)).get();

                    if (existingCtx) {
                        await db.update(messageContexts)
                            .set({ analysisJson: JSON.stringify(analysisData) })
                            .where(eq(messageContexts.id, existingCtx.id))
                            .run();
                    } else {
                        // Create new context
                        await db.insert(messageContexts).values({
                            id: crypto.randomUUID(), // Assuming UUID generator needed or rely heavily on DB
                            messageId: msg.messageId,
                            analysisJson: JSON.stringify(analysisData)
                        }).run();
                    }
                }
            } catch (e: any) {
                console.warn("Could not save to Message table via Drizzle. Logging only.", e.message);
            }

            // 5. Notify Orchestrator
            try {
                // Determine ID (either existing or new derived from engagementId)
                const orchestratorId = this.env.ENGAGEMENT_ORCHESTRATOR.idFromName(job.engagementId);
                const orchestrator = this.env.ENGAGEMENT_ORCHESTRATOR.get(orchestratorId);

                // RPC call via fetch to the Orchestrator DO
                await orchestrator.fetch("http://internal/analyzeForensicsResult", {
                    method: "POST",
                    body: JSON.stringify(analysisData)
                });
            } catch (e: any) {
                // Log failure but don't fail the whole job if orchestration notification fails
                console.warn(`Orchestrator notification failed for engagementId: ${job.engagementId}; error: ${e.message}`);
            }

            return { success: true, analysis: analysisData };

        } catch (error: any) {
            console.error("Forensics pipeline failed:", JSON.stringify(error));
            throw error; // Trigger retry in queue
        }
    }
}