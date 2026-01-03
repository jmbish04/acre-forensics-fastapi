from typing import Dict, List

from .base import BaseAgentClient


class VerificationAgentClient(BaseAgentClient):
    def __init__(self, engagement_id: str):
        super().__init__("verification", engagement_id)

    def submit_for_review(self, items: List[Dict]) -> Dict:
        """
        Submits potential contradictions or facts for human review.
        Items should match VerificationItem interface: {type, content, sourceId, confidence}
        """
        return self._invoke("submitForReview", {"items": items})

    def get_items(self, status: str = "PENDING") -> List[Dict]:
        """Fetch items by status: PENDING, VERIFIED, REJECTED."""
        return self._invoke("getVerificationItems", {"statusFilter": status})

    def approve_item(self, item_id: str) -> Dict:
        """Mark an item as verified/true."""
        return self._invoke("approveItem", {"id": item_id})

    def reject_item(self, item_id: str) -> Dict:
        """Mark an item as false/rejected."""
        return self._invoke("rejectItem", {"id": item_id})

    def get_verified_facts(self) -> List[Dict]:
        """Get only the facts explicitly approved by a human."""
        return self._invoke("getVerifiedFacts", {})
