"""Group action schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GroupsSearchInput(BaseModel):
    group_ids: list[str] = Field(default_factory=list)
    terms: list[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = None
    since: str | None = None


class GroupsSearchOutput(BaseModel):
    results: list[dict] = Field(default_factory=list)
    cursor: dict = Field(default_factory=dict)
    matched_terms: list[str] = Field(default_factory=list)


class GroupPostInput(BaseModel):
    group_id: str
    message: str
    image_paths: list[str] = Field(default_factory=list)
    dry_run: bool = True


class GroupPostOutput(BaseModel):
    posted: bool = False
    group_id: str | None = None
