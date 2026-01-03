from typing import Dict, List

from .base import BaseAgentClient


class ClassifierAgent(BaseAgentClient):
    def __init__(self, engagement_id: str = "global"):
        super().__init__("classifier", engagement_id)

    def classify_batch(self, transcripts: List[Dict]) -> Dict:
        """
        Input: [{'id': '1', 'content': '...'}]
        Output: {'1': ['label_a', 'label_b']}
        """
        return self._invoke("classifyBatch", {"transcripts": transcripts})
