"""Posts listen action schemas."""
from __future__ import annotations
from pydantic import BaseModel, Field


class PostsListenInput(BaseModel):
    group_id: str
    terms: list[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=100)


class PostsListenOutput(BaseModel):
    new_posts: list[dict] = Field(default_factory=list)
    cursor_advanced: bool = False