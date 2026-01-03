from typing import Dict, List

from .base import BaseAgentClient


class ForensicAnalystAgent(BaseAgentClient):
    def __init__(self, engagement_id: str):
        super().__init__("forensic", engagement_id)

    def analyze_content(self, content: str, context: str = "") -> Dict:
        return self._invoke("analyzeContent", {"content": content, "context": context})

    def enrich_timeline(self, messages: List[Dict]) -> Dict:
        return self._invoke(
            "enrichTimeline",
            {"messages": messages, "metadata": {"engagementId": self.engagement_id}},
        )
