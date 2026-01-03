from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class EngagementBase(BaseModel):
    name: str
    entity_domain: str
    description: Optional[str] = None
    status: str = "ACTIVE"
    contract_drive_folder_id: Optional[str] = None
    final_contract_id: Optional[str] = None


class EngagementCreate(EngagementBase):
    pass


class EngagementUpdate(BaseModel):
    name: Optional[str] = None
    entity_domain: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    contract_drive_folder_id: Optional[str] = None
    final_contract_id: Optional[str] = None


class Engagement(EngagementBase):
    id: str
    created_at: datetime

    model_config = ConfigDict(
        populate_by_name=True, arbitrary_types_allowed=True, from_attributes=True
    )


class EngagementFactBase(BaseModel):
    content: str
    type: str = "CONTEXT"
    title: Optional[str] = None
    source_artifact_id: Optional[str] = None
    confidence: float = 1.0


class EngagementFactCreate(EngagementFactBase):
    pass


class EngagementFact(EngagementFactBase):
    id: str
    engagement_id: str
    created_at: datetime

    model_config = ConfigDict(
        populate_by_name=True, arbitrary_types_allowed=True, from_attributes=True
    )


class ContextPack(BaseModel):
    engagement: Engagement
    facts: List[EngagementFact]
    recent_evidence_summary: Optional[str] = None
