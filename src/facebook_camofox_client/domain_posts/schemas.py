from __future__ import annotations
from facebook_camofox_client.domain_records.models import NormalizedPostRecord

"""Posts listen action schemas."""
from pydantic import BaseModel, Field
class PostsListenInput(BaseModel):
    group_id: str
    terms: list[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=100)
class PostsListenOutput(BaseModel):
    new_posts: list[NormalizedPostRecord] = Field(default_factory=list)
    cursor_advanced: bool = False
