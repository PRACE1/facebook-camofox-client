"""Action envelope model."""
from datetime import datetime
from pydantic import BaseModel, Field

class ActionEnvelope(BaseModel):
    action_id: str
    action_type: str
    account_id: str
    session_id: str | None = None
    input: dict = Field(default_factory=dict)
    idempotency_key: str
    status: str = "queued"
    created_at: datetime = Field(default_factory=datetime.utcnow)