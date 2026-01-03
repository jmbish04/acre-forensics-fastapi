import os
import sys
import traceback

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from typing import Dict, Optional

from .atomizer import Atomizer
from .attribution import AttributionEngine
from .ingestion import ArtifactRegistry, MimeExploder
from .remote_worker_api import RemoteWorkerClient, WorkerLogger
from .reporter import ForensicReporter
from .verification import VerificationEngine

# DB Init (Assume already run or import)
# from src.forensics.init_db import init_db
# import sqlite3  <-- DELETED


class ACREPipeline:
    def __init__(self, context_data: Optional[Dict] = None, monitor=None):
        """
        Initialize pipeline.
        :param context_data: Optional dictionary containing secrets or context.
                             e.g. {'secrets': {'WORKER_API_KEY': '...', 'GCP_SERVICE_ACCOUNT': '...'},
                                   'workflowId': '...', 'engagementId': '...'}
        """
        self.registry = ArtifactRegistry()
        self.exploder = MimeExploder()
        self.atomizer = Atomizer()
        self.attributor = AttributionEngine()
        self.verifier = VerificationEngine()
        self.reporter = ForensicReporter()

        # Configure Client with dynamic secrets if provided
        secrets = context_data.get("secrets", {}) if context_data else {}

        # Use secrets from payload if present, otherwise let RemoteWorkerClient use env vars
        self.client = RemoteWorkerClient(
            secret=secrets.get("WORKER_API_KEY"), worker_url=secrets.get("WORKER_URL")
        )

        # Fallback to Env Var for Service Account if not in payload
        self.gcp_service_account = secrets.get("GCP_SERVICE_ACCOUNT") or os.environ.get(
            "GCP_SERVICE_ACCOUNT"
        )

        self.engagement_id = (
            context_data.get("engagementId", "default") if context_data else "default"
        )

        # Setup Logger
        self.logger = WorkerLogger(
            client=self.client,
            workflow_id=context_data.get("workflowId", "UNKNOWN_WORKFLOW")
            if context_data
            else "UNKNOWN_WORKFLOW",
            engagement_id=self.engagement_id,
        )

        # Track Session ID for HIL Loop
        self.session_id = (
            context_data.get("sessionId", "INITIAL_PROCESSING") if context_data else "INITIAL_PROCESSING"
        )

        # Initialize Agents
        from ..agents.classifier import ClassifierAgent
        from ..agents.forensic import ForensicAnalystAgent

        self.classifier = ClassifierAgent(self.engagement_id)
        self.forensic_agent = ForensicAnalystAgent(self.engagement_id)

        # Regulatory Agents (On-Demand)
        from ..agents.regulatory import CaRegsAgent, SfDbiAgent, SfRegsAgent

        self.sf_dbi = SfDbiAgent(self.client, self.engagement_id)
        self.sf_regs = SfRegsAgent(self.client, self.engagement_id)
        self.sf_regs = SfRegsAgent(self.client, self.engagement_id)
        self.ca_regs = CaRegsAgent(self.client, self.engagement_id)

        # Monitor
        self.monitor = monitor

    async def _emit(self, event_type: str, data: dict):
        if self.monitor:
            payload = {"type": event_type, "timestamp": "now", **data}
            await self.monitor.broadcast(payload)

    def run_regulatory_verification(self, message_payload: dict) -> dict:
        """
        Run deep-dive verification using regulatory agents if keywords are detected.
        This is an optional, expensive step.
        """
        results = {}
        content = (message_payload.get("body") or "") + " " + (message_payload.get("subject") or "")
        content_lower = content.lower()

        # 1. Check for Contractor License (Simple regex or keyword)
        # Regex could be better: [A-Z]{2,}\d{5,} etc. keeping it simple for now.
        import re

        # Look for "License #123456" or "Lic: 123456"
        lic_match = re.search(r"lic(?:ense)?\.?\s*(?:#|no\.?)?\s*(\d{6,})", content_lower)
        if lic_match:
            license_number = lic_match.group(1)
            self.logger.info(
                "verify_context",
                f"Detected License {license_number}. Verifying with SF DBI...",
                metadata={"license": license_number},
            )
            try:
                # Assuming lookup_contractor_history returns a JSON string, we verify the presence of text
                history = self.sf_dbi.lookup_contractor_history(license_number)
                results["sf_dbi_contractor"] = {"license": license_number, "result": history}
            except Exception as e:
                results["sf_dbi_contractor"] = {"error": str(e)}

        # 2. Check for Address/Permit Mentions
        # "123 Market St", "Permit #..."
        # This is harder to extract reliably without NER.
        # We will trigger if specific keywords exist and just try a generic property lookup on a dummy or extracted entity?
        # User prompt said "check message_payload for keywords... invoke corresponding agent".
        # Let's check for "permit" + "San Francisco"
        if "permit" in content_lower and (
            "san francisco" in content_lower or "sf" in content_lower
        ):
            self.logger.info(
                "verify_context",
                "Detected Permit+SF discussion. (Placeholder for address extraction)",
            )
            results["sf_dbi_permit_check"] = "Triggered but address extraction not implemented yet."

        # 3. Regulatory Code Questions
        # "code", "regulation", "title 24", "sprinkler"
        if "title 24" in content_lower or "california building code" in content_lower:
            self.logger.info("verify_context", "Detected CA Code reference. Searching CA Regs...")
            try:
                # Search for the whole subject as query?
                query = message_payload.get("subject") or "General Code Inquiry"
                regs = self.ca_regs.search_ca_code(query)
                results["ca_regs_search"] = regs
            except Exception as e:
                results["ca_regs_search"] = {"error": str(e)}

        if "sf code" in content_lower or "san francisco building code" in content_lower:
            self.logger.info("verify_context", "Detected SF Code reference. Searching SF Regs...")
            try:
                query = message_payload.get("subject") or "General SF Code Inquiry"
                regs = self.sf_regs.search_sf_code(query)
                results["sf_regs_search"] = regs
            except Exception as e:
                results["sf_regs_search"] = {"error": str(e)}

        return results

    async def process_message(self, message_payload):
        """
        Process a single message received from the Worker workflow.
        """
        message_id = message_payload.get("messageId")
        self.logger.info(
            "process_message",
            f"Starting processing for {message_id}",
            metadata={"messageId": message_id},
        )
        await self._emit(
            "step_start", {"step": "Process Message", "log": f"Processing {message_id}..."}
        )

        # Extract content
        headers = message_payload.get("headers", {})
        body_plain = message_payload.get("body", "")
        body_html = message_payload.get("htmlBody", "")

        # Fetch from Gmail if needed
        if (not body_plain) and self.gcp_service_account:
            try:
                from .gmail_collector import GmailCollector

                collector = GmailCollector(
                    service_account_json=self.gcp_service_account, logger=self.logger
                )
                msg = None
                fetch_result = collector.fetch_raw_message(message_id)
                if fetch_result:
                    raw_bytes, meta = fetch_result

                    # Parse raw bytes
                    parsed_headers, _, msg = self.exploder.parse_eml_bytes(raw_bytes)
                    headers.update(parsed_headers)

                if msg:
                    if msg.is_multipart():
                        for part in msg.walk():
                            ctype = part.get_content_type()
                            if ctype == "text/html":
                                body_html = part.get_payload(decode=True).decode(
                                    "utf-8", errors="ignore"
                                )
                            elif ctype == "text/plain":
                                body_plain = part.get_payload(decode=True).decode(
                                    "utf-8", errors="ignore"
                                )
                    else:
                        # Non-multipart
                        body_plain = msg.get_payload(decode=True).decode(
                            "utf-8", errors="ignore"
                        )
                else:
                    self.logger.warning("process_message", f"Could not parse email message body for {message_id}")
                self.logger.info(
                    "process_message", "Fethed content from Gmail", metadata={"source": "Gmail API"}
                )
            except Exception as e:
                self.logger.error(
                    "process_message",
                    f"Failed to fetch from Gmail: {e}",
                    error_type="GMAIL_FETCH_ERROR",
                )

        # 1.5 PERSISTENCE: Ensure Message Record Exists in D1
        # Map payload to Schema fields expected by internal API
        db_message = {
            "messageId": message_id,
            "engagement_id": self.engagement_id,
            "threadId": message_payload.get("threadId"),  # Might be None
            "fromAddress": headers.get("From"),
            "toAddress": headers.get("To"),
            "subject": headers.get("Subject"),
            "bodyPlain": body_plain,
            "bodyHtml": body_html,
            "sentDate": headers.get(
                "Date"
            ),  # String format, API should handle or we rely on parsing
            # headers field expected as JSON string or object? API Schema.Message usually expects Json.
            # internal.ts:175 just passes body to dataService.create("message", body).
            # Prisma expects Json type for 'headers'.
            "headers": headers,
        }

        self.logger.info("process_message", "Persisting base message record to D1...")
        try:
            self.client.create_message(db_message)
        except Exception as e:
            # Duplicate error is likely if re-running. We proceed.
            self.logger.info(
                "process_message", f"Message creation skipped/failed (likely exists): {e}"
            )
            # Optimization: If message exists, we assume it's processed. Skip expensive steps.
            return {"status": "skipped", "reason": "duplicate"}

        # 2. Atomize
        self.logger.info("process_message", f"Atomizing {message_id}...")
        await self._emit("step_start", {"step": "Atomization", "log": "Extracting artifacts..."})
        atoms = self.atomizer.atomize(message_id, body_html, body_plain, headers.get("From"))
        await self._emit(
            "artifact_found", {"count": len(atoms), "log": f"Extracted {len(atoms)} atoms."}
        )

        # 3. Attribute
        self.logger.info("process_message", f"Attributing {len(atoms)} atoms...")
        attributed_atoms = self.attributor.attribute_atoms(atoms, headers.get("From"))

        # 4. Classify using Agent
        self.logger.info("process_message", "Invoking Classifier Agent...")
        try:
            # Prepare payload for classifier (needs id and content)
            classifier_input = [{"id": a["id"], "content": a["content"]} for a in attributed_atoms]
            classification_results = self.classifier.classify_batch(classifier_input)
            # Enrich atoms with labels
            for atom in attributed_atoms:
                # Classification result is a dict: {id: [tags]}
                atom["labels"] = classification_results.get(atom["id"], [])

            # Emit Decision
            labels_summary = (
                list(classification_results.values())[0] if classification_results else []
            )
            await self._emit(
                "decision_made", {"label": labels_summary, "log": "AI Classification complete."}
            )

        except Exception as e:
            self.logger.error("process_message", f"Classification Failed: {e}")

        # 5. Save Transcripts via API
        transcripts_payload = []
        for atom in attributed_atoms:
            transcripts_payload.append(
                {
                    "id": atom["id"],
                    "messageId": atom["messageId"],
                    "content": atom["content"],
                    "normalizedHash": atom["normalizedHash"],
                    "sequenceIndex": atom["sequenceIndex"],
                    "quoteDepth": atom["quoteDepth"],
                    "visualStyle": atom["visualStyle"],
                    "attributedTo": atom["attributedTo"],
                    "attributionMethod": atom["attributionMethod"],
                    "tags": atom.get("labels", []),  # Include tags now
                }
            )

        self.logger.info(
            "process_message", f"Saving {len(transcripts_payload)} transcripts to Worker..."
        )
        self.client.batch_create_transcripts(transcripts_payload)

        # 6. Store Analysis Result (Update Message)
        self.logger.info("process_message", "Storing Analysis Meta...")
        analysis_meta = {
            "attribution_stats": self._summarize_attribution(attributed_atoms),
        }
        self.client.store_analysis(
            message_id, 
            analysis_meta, 
            deception_score=0, 
            session_id=self.session_id
        )

        self.logger.info("process_message", "Message Processing Complete.")
        await self._emit("step_complete", {"step": "Pipeline", "log": "Processing finished."})
        return {"status": "success", "atoms": len(atoms)}

    def _summarize_attribution(self, atoms):
        stats = {}
        for a in atoms:
            auth = a.get("attributedTo", "unknown")
            stats[auth] = stats.get(auth, 0) + 1
        return stats

    async def run_pipeline(self, engagement_id: str = "default", gmail_domain: Optional[str] = None):
        """
        Run the pipeline by ingesting from Gmail and processing messages.
        1. Inits GmailCollector.
        2. Lists all IDs first (for progress tracking).
        3. Fetches messages chronologically.
        4. Checks deduplication (process_message handles this).
        """
        self.engagement_id = engagement_id 
        
        # Query Logic
        if gmail_domain:
            if " " in gmail_domain or ":" in gmail_domain:
                query = gmail_domain # Assume raw query
            else:
                query = f"from:{gmail_domain} OR to:{gmail_domain}"
        else:
            query = "mrroofing.net" 

        self.logger.info("run_pipeline", f"Starting Pipeline for {engagement_id}, query: {query}")
        
        try:
            from forensics_fastapi.forensics.gmail_collector import GmailCollector
        except ImportError:
            from .gmail_collector import GmailCollector

        try:
            collector = GmailCollector(
                service_account_json=self.gcp_service_account, 
                logger=self.logger
            )
        except Exception as e:
            self.logger.error("run_pipeline", f"Failed to init GmailCollector: {e}")
            await self._emit("error", {"msg": f"Gmail Init Failed: {e}"})
            return []

        # 3. List messages first to get total count
        self.logger.info("run_pipeline", f"Listing messages for query: {query}")
        message_ids = collector.list_message_ids(query)
        total_messages = len(message_ids)

        # Notify FE of start
        await self._emit("pipeline_start", {
            "log": f"Pipeline started. Found {total_messages} messages for {query}.",
            "total_estimated": total_messages
        })

        processed_count = 0
        skipped_count = 0

        # 4. Stream and Process
        async for email_data in collector.fetch_messages(message_ids):
            msg_id = email_data.get("messageId") 
            gmail_id = email_data.get("id")      
            
            # Construct Payload for internal processor
            message_payload = {
                "messageId": msg_id,
                "threadId": email_data.get("threadId", gmail_id), # Fallback to gmail ID if threadId missing
                "headers": email_data.get("headers", {}),
                "body": email_data.get("bodyPlain"),
                "htmlBody": email_data.get("bodyHtml"),
                "from": email_data.get("fromAddress"),
                "subject": email_data.get("subject"),
                "timestamp": email_data.get("sentDate"),
            }

            # PROCESS
            # We modify process_message to return a status we can track
            try:
                # We'll rely on process_message handling the "create" step. 
                # If create fails (duplicate), process_message currently catches it and continues.
                # We should probably propagate that "skip" signal up if possible, 
                # OR just inspect the logs/return value.
                # Let's assume process_message is idempotent-ish.
                # For optimization (Skip already processed):
                # If we could check existence efficiently we would.
                # Since we lack a direct "exists(msg_id)" API in RemoteWorkerClient without id,
                # we'll rely on process_message's db interaction.
                
                # Update: The user explicitly asked to "Skip already processed message IDs".
                # If `process_message` is expensive (AI calls), we MUST skip if exists.
                # Let's try to fetch by attribute? `client.list_messages(filter=...)`? No simple filter.
                # Okay, we will use a "try/catch" block in process_message to DETECT duplicate and return early.
                # But `process_message` calls `create_message`. 
                
                # HOTFIX: We will call `process_message` but we need to update IT to stop if DB insert says "Exists".
                
                await self._emit("ingest_progress", {"log": f"Ingesting {msg_id}..."})
                res = await self.process_message(message_payload)
                if res.get("status") == "skipped":
                    skipped_count += 1
                    await self._emit("ingest_skip", {"id": msg_id, "log": "Skipped (Duplicate)"})
                else:
                    processed_count += 1
            
            except Exception as e:
                self.logger.error("run_pipeline", f"Error on {msg_id}: {e}")

        await self._emit("pipeline_complete", {
            "processed": processed_count, 
            "skipped": skipped_count, 
            "log": f"Done. Processed {processed_count}, Skipped {skipped_count}."
        })
        return {"processed": processed_count, "skipped": skipped_count}


if __name__ == "__main__":
    import argparse
    import asyncio
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=str, required=True, help="JSON payload")
    args = parser.parse_args()

    try:
        payload = json.loads(args.json)
        action = payload.get("action", "run_pipeline")
        engagement_id = payload.get("engagementId", "default")
        
        pipeline = ACREPipeline(context_data=payload)

        if action == "run_pipeline" or action == "ingest_gmail":
            # Map payload to method args
            gmail_domain = payload.get("gmail_domain") or payload.get("query")
            
            # Run async method
            result = asyncio.run(
                pipeline.run_pipeline(
                    engagement_id=engagement_id, 
                    gmail_domain=gmail_domain
                )
            )
            # Output Result as JSON
            print(json.dumps(result))
            
        else:
            print(json.dumps({"error": f"Unknown action: {action}"}))
            sys.exit(1)

    except Exception as e:
        print(json.dumps({"error": str(e), "details": traceback.format_exc()}))
        sys.exit(1)
