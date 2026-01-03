from typing import List

from fastapi import APIRouter, HTTPException

from forensics_fastapi.forensics.engagement_models import (
    ContextPack,
    Engagement,
    EngagementCreate,
    EngagementFact,
    EngagementFactCreate,
)
from forensics_fastapi.forensics.remote_worker_api import RemoteWorkerClient

router = APIRouter(
    prefix="/engagements",
    tags=["Engagements"],
    responses={404: {"description": "Not found"}},
)

# Initialize Client
# In prod, this URL should come from env var ACRE_WORKER_URL
client = RemoteWorkerClient()


@router.post("/", response_model=Engagement, status_code=201, operation_id="create_engagement")
def create_engagement(engagement: EngagementCreate):
    """Create a new Engagement (via Worker)."""
    try:
        # Pydantic to Dict
        data = (
            engagement.model_dump(exclude_unset=True)
            if hasattr(engagement, "model_dump")
            else engagement.dict(exclude_unset=True)
        )
        return client.create_engagement(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Worker Error: {str(e)}")


@router.get("/", response_model=List[Engagement], operation_id="list_engagements")
def list_engagements():
    """List all Engagements (via Worker)."""
    try:
        return client.list_engagements()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Worker Error: {str(e)}")


@router.get("/{engagement_id}", response_model=Engagement, operation_id="get_engagement")
def get_engagement(engagement_id: str):
    """Get Engagement details (via Worker)."""
    try:
        eng = client.get_engagement(engagement_id)
        if not eng:
            raise HTTPException(status_code=404, detail="Engagement not found")
        return eng
    except Exception as e:
        if "404" in str(e):
            raise HTTPException(status_code=404, detail="Not Found")
        raise HTTPException(status_code=500, detail=f"Worker Error: {str(e)}")


@router.post(
    "/{engagement_id}/facts",
    response_model=EngagementFact,
    status_code=201,
    operation_id="add_engagement_fact",
)
def add_fact(engagement_id: str, fact: EngagementFactCreate):
    """Add a Fact to an Engagement (via Worker)."""
    try:
        data = (
            fact.model_dump(exclude_unset=True)
            if hasattr(fact, "model_dump")
            else fact.dict(exclude_unset=True)
        )
        return client.add_fact(engagement_id, data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Worker Error: {str(e)}")


@router.get(
    "/{engagement_id}/context_pack", response_model=ContextPack, operation_id="get_context_pack"
)
def get_context_pack(engagement_id: str):
    """Retrieve aggregated context (via Worker)."""
    try:
        return client.get_context_pack(engagement_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Worker Error: {str(e)}")
