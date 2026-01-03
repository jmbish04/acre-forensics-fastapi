from typing import Dict

from .base import BaseAgentClient


class ForensicJudgeClient(BaseAgentClient):
    def __init__(self, engagement_id: str):
        super().__init__("judge", engagement_id)

    def evaluate(self, findings: Dict) -> Dict:
        """
        Ask the Judge to critique the timeline/profile findings.
        Returns: { approved: bool, confidence_score: number, issues: [], retry_guidance: ... }
        """
        return self._invoke("evaluate", {"findings": findings})


class PsychProfilerClient(BaseAgentClient):
    def __init__(self, engagement_id: str):
        super().__init__("profiler", engagement_id)

    def analyze(self) -> Dict:
        """
        Trigger the profiler to analyze the engagement's messages.
        (Note: The TS implementation fetches messages internally via D1, so no payload needed).
        """
        return self._invoke("analyze", {"engagementId": self.engagement_id})


class TimelineAgentClient(BaseAgentClient):
    def __init__(self, engagement_id: str):
        super().__init__("timeline", engagement_id)

    def generate(self) -> Dict:
        """
        Trigger timeline generation.
        """
        return self._invoke("generate", {"engagementId": self.engagement_id})
