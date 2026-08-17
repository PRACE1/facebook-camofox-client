"""Cursor models."""
from datetime import datetime
from pydantic import BaseModel, Field

class Cursor(BaseModel):
    cursor_key: str
    action_type: str
    account_id: str
    scope_key: str
    last_post_id: str = ""
    watermark: datetime | None = None
    opaque_cursor: str = ""
    updated_at: datetime = Field(default_factory=datetime.utcnow)