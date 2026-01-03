import json
import os
from datetime import datetime
from typing import Dict, Optional

from .remote_worker_api import RemoteWorkerClient

OUTPUT_DIR = "src/reports/output_final"


class ForensicReporter:
    def __init__(self, db_path="src/data/forensics.db"):
        self.db_path = db_path
        self.client = RemoteWorkerClient()
        os.makedirs(OUTPUT_DIR, exist_ok=True)

    def generate_json_timeline(
        self, thread_id: Optional[str] = None, engagement_id: Optional[str] = None
    ) -> Dict:
        """
        Fetches enriched timeline data from Cloudflare Worker D1 + AI.
        """
        try:
            payload = {}
            if thread_id:
                payload["threadId"] = thread_id
            if engagement_id:
                payload["engagementId"] = engagement_id

            # This returns { "timeline": [...], "enrichment": {...} }
            data = self.client.post("/reports/timeline", payload)

            # Save locally for reference
            output_path = os.path.join(OUTPUT_DIR, "Reconstructed_Thread.json")
            with open(output_path, "w") as f:
                json.dump(data, f, indent=2)

            return data
        except Exception as e:
            print(f"Error fetching remote timeline: {e}")
            return {"timeline": [], "enrichment": {"error": str(e)}}

    def generate_report_markdown(self, timeline_data: Dict) -> str:
        """
        Generates a Markdown report from the enriched timeline data.
        """
        messages = timeline_data.get("timeline", [])
        enrichment = timeline_data.get("enrichment", {})

        report_lines = []
        report_lines.append("# Forensic Timeline Report")
        report_lines.append(f"Generated: {datetime.now().isoformat()}\n")

        # 1. AI Analysis Section
        if enrichment:
            report_lines.append("## AI Forensic Analysis")
            if "overview" in enrichment:
                report_lines.append(f"**Overview:** {enrichment['overview']}\n")

            if "potential_risks" in enrichment and enrichment["potential_risks"]:
                report_lines.append("### Potential Risks")
                for risk in enrichment["potential_risks"]:
                    report_lines.append(f"- ⚠️ {risk}")
                report_lines.append("")

            report_lines.append("---\n")

        # 2. Key Statistics
        senders = set(m.get("fromAddress", "Unknown") for m in messages)
        report_lines.append("## Statistics")
        report_lines.append(f"- Total Messages: {len(messages)}")
        report_lines.append(f"- Participants: {', '.join(senders)}\n")

        # 3. Detailed Timeline
        report_lines.append("## Detailed Timeline")

        for msg in messages:
            date_str = msg.get("sentDate", "Unknown Date")
            sender = msg.get("fromAddress", "Unknown")
            subject = msg.get("subject", "No Subject")
            snippet = (msg.get("bodyPlain") or "")[:200].replace("\n", " ")

            report_lines.append(f"\n### 📧 {date_str} - {sender}")
            report_lines.append(f"**Subject:** {subject}")
            report_lines.append(f"> {snippet}...")
            report_lines.append("---\n")

        report_content = "\n".join(report_lines)

        output_path = os.path.join(OUTPUT_DIR, "Forensic_Report.md")
        with open(output_path, "w") as f:
            f.write(report_content)

        print(f"✅ Generated Markdown Report: {output_path}")
        return report_content


if __name__ == "__main__":
    reporter = ForensicReporter()
    data = reporter.generate_json_timeline()
    reporter.generate_report_markdown(data)
