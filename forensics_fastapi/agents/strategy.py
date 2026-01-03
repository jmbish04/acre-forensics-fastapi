from typing import Dict, List

from .base import BaseAgentClient


class StrategyAgent(BaseAgentClient):
    def __init__(self, engagement_id: str):
        super().__init__("strategy", engagement_id)

    def draft_reply(self, intent: str, tone: str, facts: List[Dict], context: Dict) -> Dict:
        return self._invoke(
            "draftReply",
            {"intent": intent, "tone": tone, "rawFacts": facts, "engagementContext": context},
        )

    def reality_check(self, draft_text: str, facts: List[Dict]) -> Dict:
        return self._invoke("realityCheck", {"draftText": draft_text, "facts": facts})

    def set_mode(self, mode: str):
        return self._invoke("setStrategyMode", {"mode": mode})
