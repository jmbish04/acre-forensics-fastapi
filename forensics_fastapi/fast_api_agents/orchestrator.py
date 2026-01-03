from typing import Dict, Optional

from .base import BaseAgentClient


class EngagementOrchestratorClient(BaseAgentClient):
    """
    Client for the Master Engagement Orchestrator.
    Manages the lifecycle: Ingestion -> Analysis -> Strategy.
    """
    def __init__(self, engagement_id: str):
        super().__init__("engagement_orchestrator", engagement_id)

    def start_ingestion(self, total_files: int) -> Dict:
        """Triggers the 'INGESTING' state."""
        return self._invoke("startIngestion", {
            "engagementId": self.engagement_id,
            "totalEstimatedFiles": total_files
        })

    def update_progress(self, increment: int = 1, description: Optional[str] = None) -> Dict:
        """Updates ingestion/analysis progress bar."""
        return self._invoke("updateProgress", {
            "increment": increment,
            "description": description
        })

    def analyze_forensics_result(self, analysis_data: Dict) -> Dict:
        """Pushes a forensic finding to the orchestrator to check triggers."""
        return self._invoke("analyzeForensicsResult", {
            "analysis": analysis_data
        })

    def get_dashboard_state(self) -> Dict:
        """Fetches status, progress, and linked agent IDs."""
        return self._invoke("getDashboardState", {})


class ForensicTeamOrchestratorClient(BaseAgentClient):
    """
    Client for the Forensic Team Lead (Sub-Orchestrator).
    Manages the specific timeline/profile/judge loop.
    """
    def __init__(self, engagement_id: str):
        super().__init__("forensic_team", engagement_id)

    def start_investigation(self) -> Dict:
        """Kicks off the deep dive analysis loop (Timeline + Profiler)."""
        return self._invoke("startInvestigation", {
            "engagementId": self.engagement_id
        })
    
    # Note: Human feedback handling is usually done via WebSocket, 
    # but if exposed via RPC:
    def submit_human_feedback(self, action: str, comments: str = "", edited_findings: Optional[Dict] = None) -> Dict:
        return self._invoke("handleHumanFeedback", {
            "action": action, # APPROVE, REJECT, EDIT
            "comments": comments,
            "editedFindings": edited_findings
        })
