import json

from .remote_worker_api import RemoteWorkerClient as ACREClient

# Refactored AILabeler
# Delegates compute to Cloudflare Worker Agents.
# Maintains "Label-Only" contract but moves logic to the Edge.


class AILabeler:
    def __init__(self, provider="worker", model=None, api_key=None):
        # Provider arg is kept for legacy signature compat, but we default to using the Worker Client.
        # Ensure WORKER_API_KEY is in env.
        self.client = ACREClient(secret=api_key)

    def label_transcripts(self, transcripts):
        """
        Takes list of transcript dicts (id, content).
        Returns dict mapping transcript_id -> labels [].
        """
        # 1. Map to structure expected by API {id, content} matches input
        # 2. Call API
        try:
            results = self.client.classify_transcripts_batch(transcripts)
            return results
        except Exception as e:
            print(f"Agent Labeling Failed: {e}")
            # Fallback? For now return empty or raise.
            return {}


if __name__ == "__main__":
    # Mock Test
    mock_data = [
        {"id": "1", "content": "Per CSLB rules you must pay."},
        {"id": "2", "content": "When will you arrive?"},
    ]

    labeler = AILabeler()
    print("Testing Remote Agent Labeler...")
    try:
        res = labeler.label_transcripts(mock_data)
        print("Result:", json.dumps(res, indent=2))
    except Exception as e:
        print(f"Test Failed: {e}")
