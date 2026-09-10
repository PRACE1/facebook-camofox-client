"""Marketplace action schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class MarketplaceCreateInput(BaseModel):
    title: str
    price: str
    category: str
    description: str = ""
    location: str = ""
    condition: str | None = None
    image_paths: list[str] = Field(default_factory=list)
    dry_run: bool = True
    offer_id: str = ""


class MarketplaceCreateOutput(BaseModel):
    published: bool = False
    success: bool = False
    listing_id: str | None = None
    listing_url: str | None = None
    published_at: str | None = None
    receipt_path: str | None = None  # screenshot only, never raw HTML


class MarketplaceStatusInput(BaseModel):
    listing_id: str
    offer_id: str = ""


class MarketplaceStatusOutput(BaseModel):
    listing_id: str
    listing_url: str
    status: str = "unknown"  # active | under-review-duplicate | sold | removed | login-wall | unknown
    title: str | None = None
