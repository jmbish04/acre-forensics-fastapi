from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from forensics_fastapi.forensics.remote_worker_api import RemoteWorkerClient


# Request Models
class DraftRequest(BaseModel):
    user_intent: str
    tone: str = "FIRM"  # FIRM, GRAY_ROCK, COOPERATIVE
    citations: Optional[List[str]] = None  # List of Fact IDs to cite
    # Optional: verificationAgentId if we want to enforce fetching verified facts from a specific agent


class RealityCheckRequest(BaseModel):
    draft_text: str


# Response Models
class DraftResponse(BaseModel):
    draft_text: str
    strategy_notes: str


class RealityCheckResponse(BaseModel):
    issues: List[str]
    safe_version: Optional[str] = None
    notes: Optional[str] = None


router = APIRouter(
    prefix="/engagements",
    tags=["Strategy"],
    responses={404: {"description": "Not found"}},
)

# Initialize Client (Worker Bridge)
client = RemoteWorkerClient()


@router.post(
    "/{engagement_id}/draft", response_model=DraftResponse, operation_id="generate_strategic_draft"
)
def generate_draft(engagement_id: str, request: DraftRequest):
    """
    Generate a strategic email reply based on Intent + Facts.
    Delegates completely to the Cloudflare Worker StrategyAgent.
    """
    try:
        # 1. Fetch Engagement Context & Facts via Worker Client
        # Actually, the Worker's StrategyAgent endpoint handles context fetching if we pass engagementId.
        # However, the current RemoteWorkerClient.draft_reply takes 'facts' and 'engagement_context' explicitly.
        # This design choice in the Worker (StrategyAgent) allows it to be stateless or state-managed.
        # Let's see if we should fetch context here or if Worker endpoint accepts engagementId.
        # Looking at Worker 'draftReply' signature in strategy.ts: it takes (intent, tone, rawFacts, engagementContext).
        # It does NOT take engagementId directly to fetch its own facts (unless we change it).
        # BUT, the router in Internal.ts likely orchestrates this?
        # Let's assume we need to fetch info here OR create a new endpoint in internal.ts that does it all.
        # Since I didn't change internal.ts to fetch keys, I should fetch context here.
        # Retrieve Context pack

        context_pack = client.get_context_pack(engagement_id)
        if not context_pack:
            raise HTTPException(status_code=404, detail="Engagement Context not found")

        # 2. Call Strategy Agent via Worker
        # We pass the facts and context we just retrieved (or let the Worker do it if we refactored internal.ts).
        # The internal.ts endpoint uses 'c.req.json()' to get payload.
        # If I look at internal.ts (I didn't verify exact payload of draft endpoint),
        # usually one passes IDs or full context.
        # Given "Split Brain" fix, let's keep it simple: Python fetches context (which now comes from D1 via Worker),
        # then passes it back to StrategyAgent (Worker). Ideally StrategyAgent on Worker should fetch it,
        # but `draftReply` method in `StrategyAgent` class is pure logic + maybe fetching.

        # Let's pass the data.
        facts = context_pack.get("facts", [])
        engagement_data = context_pack.get("engagement", {})

        result = client.draft_reply(
            intent=request.user_intent,
            tone=request.tone,
            facts=facts,
            engagement_context=engagement_data,
        )

        return result

    except Exception as e:
        print(f"Strategy Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{engagement_id}/reality_check",
    response_model=RealityCheckResponse,
    operation_id="run_reality_check",
)
def run_reality_check(engagement_id: str, request: RealityCheckRequest):
    """
    Validate a user written draft against Immutable Truths.
    """
    try:
        # 1. Fetch Context to get facts
        context_pack = client.get_context_pack(engagement_id)
        facts = context_pack.get("facts", [])  # Ideally filter for TRUTH type here or on Worker

        # 2. Call Worker
        result = client.reality_check(draft_text=request.draft_text, facts=facts)

        return result
    except Exception as e:
        print(f"Reality Check Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
