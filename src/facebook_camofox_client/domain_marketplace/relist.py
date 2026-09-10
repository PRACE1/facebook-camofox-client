"""Auto-relist state machine — mirrored from the Listaro production spec.

Pure logic, no browser: given a detected dashboard health state, decide
whether to auto-fire a replacement. Fatal states NEVER repost.
Adapted to this repo's layout (domain_marketplace, not facebook_client/domain).
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class ListingHealthStatus(str, Enum):
    ACTIVE = "ACTIVE"
    UNDER_REVIEW = "UNDER_REVIEW"
    DUPLICATE_TAKEDOWN = "DUPLICATE_TAKEDOWN"
    DELETED_BY_FB = "DELETED_BY_FB"
    POLICY_VIOLATION = "POLICY_VIOLATION"        # FATAL: never repost
    COMMERCE_BAN = "COMMERCE_BAN"                # FATAL: never repost
    CHECKPOINT_REQUIRED = "CHECKPOINT_REQUIRED"  # FATAL: never repost
    SOLD = "SOLD"                                # TERMINAL: do not repost
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"          # TERMINAL: alert operator
    UNKNOWN = "UNKNOWN"


class RelistPolicyConfig(BaseModel):
    max_repost_attempts: int = 2
    initial_poll_delay_seconds: int = 720       # 12 min (dup filters hit min 3-12)
    routine_poll_interval_seconds: int = 14400  # 4 hours
    cooldown_retry_1_seconds: int = 3600        # 1 hour (spec range 45-90 min)
    cooldown_retry_2_seconds: int = 10800       # 3 hours (spec range 3-4 h)
    jitter_range_seconds: tuple[int, int] = (60, 300)


class MonitoredListing(BaseModel):
    crm_offer_id: str
    account_id: str
    current_listing_id: str
    root_listing_id: str
    parent_listing_id: str | None = None
    generation: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_checked_at: datetime | None = None
    status: ListingHealthStatus = ListingHealthStatus.UNDER_REVIEW


class RelistDecision(BaseModel):
    should_repost: bool
    reason: str
    cooldown_seconds: int = 0
    next_generation: int = 0
    fatal_error: bool = False


def evaluate_relist_trigger(
    listing: MonitoredListing,
    detected_status: ListingHealthStatus,
    config: RelistPolicyConfig = RelistPolicyConfig(),
) -> RelistDecision:
    # 1. hard safety guards: never repost on policy/ban/checkpoint
    if detected_status in (
        ListingHealthStatus.POLICY_VIOLATION,
        ListingHealthStatus.COMMERCE_BAN,
        ListingHealthStatus.CHECKPOINT_REQUIRED,
    ):
        return RelistDecision(
            should_repost=False,
            reason=f"fatal safety stop: detected {detected_status.value}",
            fatal_error=True,
        )
    if detected_status == ListingHealthStatus.SOLD:
        return RelistDecision(
            should_repost=False,
            reason="listing marked sold or archived by operator",
        )
    if detected_status in (ListingHealthStatus.ACTIVE, ListingHealthStatus.UNDER_REVIEW):
        return RelistDecision(
            should_repost=False,
            reason=f"listing is healthy ({detected_status.value})",
        )
    if detected_status == ListingHealthStatus.RETRY_EXHAUSTED:
        return RelistDecision(
            should_repost=False,
            reason="retry budget already exhausted, operator must review",
        )
    # 2. duplicate takedown / FB deletion -> repost within budget
    if detected_status in (
        ListingHealthStatus.DUPLICATE_TAKEDOWN,
        ListingHealthStatus.DELETED_BY_FB,
    ):
        if listing.generation >= config.max_repost_attempts:
            return RelistDecision(
                should_repost=False,
                reason=f"max repost attempts ({config.max_repost_attempts}) reached",
            )
        cooldown = (
            config.cooldown_retry_1_seconds
            if listing.generation == 0
            else config.cooldown_retry_2_seconds
        )
        return RelistDecision(
            should_repost=True,
            reason="takedown confirmed, auto-relist approved",
            cooldown_seconds=cooldown,
            next_generation=listing.generation + 1,
        )
    return RelistDecision(
        should_repost=False,
        reason=f"unrecognized status {detected_status.value}, holding for operator",
    )
