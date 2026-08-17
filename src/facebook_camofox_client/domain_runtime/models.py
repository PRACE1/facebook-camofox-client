"""Shared runtime models."""
from __future__ import annotations
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

class DomainEvent(BaseModel):
    event_type: str
    action_id: str
    record_id: str | None = None
    dedupe_key: str
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    payload: dict = Field(default_factory=dict)