from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class EvidenceArtifact:
    gmail_message_id: str
    thread_id: str
    sha256_raw: str
    raw_path: str
    raw_size: int
    retrieved_at: datetime = field(default_factory=datetime.now)


@dataclass
class GmailMessageMeta:
    gmail_message_id: str
    history_id: Optional[str] = None
    internal_date: Optional[int] = None
    label_ids: List[str] = field(default_factory=list)
    label_names: List[str] = field(default_factory=list)
    snippet: Optional[str] = None
    size_estimate: Optional[int] = None
    profile_email: Optional[str] = None
    query_context: Optional[str] = None
    source: str = "gmail_api"
    api_version: str = "v1"
