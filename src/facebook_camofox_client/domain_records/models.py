"""Normalized record models."""
from datetime import datetime
from pydantic import BaseModel, Field

class NormalizedPostRecord(BaseModel):
    record_id: str
    record_type: str = "facebook_post"
    external_id: str
    source: str = "groups.search"
    account_id: str
    group_id: str = ""
    content: str = ""
    url: str = ""
    author: dict = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    metrics: dict = Field(default_factory=dict)
    matched_terms: list[str] = Field(default_factory=list)
    raw_extraction: dict | None = None