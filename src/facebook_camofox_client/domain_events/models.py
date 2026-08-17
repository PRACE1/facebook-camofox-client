"""Event models."""
from datetime import datetime
from pydantic import BaseModel, Field

class DomainEvent(BaseModel):
    event_type: str
    action_id: str
    record_id: str | None = None
    dedupe_key: str
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    payload: dict = Field(default_factory=dict)