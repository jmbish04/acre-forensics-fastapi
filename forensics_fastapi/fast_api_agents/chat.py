from .base import BaseAgentClient


class RagAgentClient(BaseAgentClient):
    def __init__(self, engagement_id: str = "default"):
        super().__init__("rag", engagement_id)

    def chat(self, query: str, limit: int = 5) -> str:
        """
        Ask the Knowledge Base a question.
        Returns the text response.
        """
        # Matches RagAgent.chat(query, limit) signature
        return self._invoke("chat", {
            "query": query,
            "limit": limit
        })

class TerminalAgentClient(BaseAgentClient):
    """
    Direct access to the Terminal Agent (if RPC enabled).
    """
    def __init__(self, engagement_id: str = "default"):
        super().__init__("terminal", engagement_id)

    # TerminalAgent is currently a Stub in TS, but if it gains methods:
    def execute(self, command: str) -> str:
        return self._invoke("execute", {"command": command})
