"""REST service over the domain actions (FastAPI).

CRM calls us (we serve). Cookies travel per request — no repository
of sessions. Conventions borrowed from open-twenty-dialer: /api/*
routes, /healthz, bearer key optional via FB_API_KEY env.

Endpoints:
  POST /api/listings            marketplace.create (dry_run default true)
  GET  /api/listings/{id}/status marketplace.status
  POST /api/watchlist           add a MonitoredListing (relist watcher input)
  GET  /api/watchlist           list watched entries
  GET  /healthz                  liveness
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_marketplace.create import MarketplaceCreateAction
from facebook_camofox_client.domain_marketplace.receipts import ReceiptStore
from facebook_camofox_client.domain_marketplace.relist import MonitoredListing
from facebook_camofox_client.domain_marketplace.schemas import (
    MarketplaceCreateInput,
    MarketplaceStatusInput,
)
from facebook_camofox_client.domain_marketplace.status import MarketplaceStatusAction

app = FastAPI(title="facebook-camofox-client", version="0.1.0")
_watchlist: dict[str, MonitoredListing] = {}


def _manager(cookies: list[dict] | None) -> CamofoxSessionManager:
    mgr = CamofoxSessionManager()
    real_acquire = mgr.acquire

    async def acquire(account_id, **kwargs):
        if cookies is not None:
            kwargs["cookies"] = cookies
        else:
            kwargs.setdefault(
                "storage_state_path",
                os.getenv("CAMOFOX_STORAGE_STATE_LISTEN_GROUP"),
            )
        return await real_acquire(account_id, **kwargs)

    mgr.acquire = acquire  # type: ignore[assignment]
    return mgr


async def _api_key(authorization: str | None = Header(default=None)) -> None:
    required = os.getenv("FB_API_KEY")
    if not required:
        return
    if authorization != f"Bearer {required}":
        raise HTTPException(status_code=401, detail="missing or invalid bearer key")


class CreateListingBody(BaseModel):
    account_id: str = "default"
    cookies: list[dict] | None = None
    listing: MarketplaceCreateInput


@app.post("/api/listings")
async def create_listing(body: CreateListingBody, _: None = Depends(_api_key)):
    action = MarketplaceCreateAction(
        _manager(body.cookies), InMemoryEventEmitter(), ReceiptStore())
    env = ActionEnvelope(
        action_id=f"api-{uuid.uuid4().hex[:12]}",
        action_type=MarketplaceCreateAction.ACTION_TYPE,
        account_id=body.account_id,
        input=body.listing.model_dump(),
        idempotency_key=f"api-{uuid.uuid4().hex}",
    )
    out = await action.execute(env)
    return {"action_id": env.action_id, **out.model_dump()}


@app.get("/api/listings/{listing_id}/status")
async def listing_status(
    listing_id: str,
    account_id: str = "default",
    _: None = Depends(_api_key),
):
    action = MarketplaceStatusAction(_manager(None), InMemoryEventEmitter())
    env = ActionEnvelope(
        action_id=f"api-{uuid.uuid4().hex[:12]}",
        action_type=MarketplaceStatusAction.ACTION_TYPE,
        account_id=account_id,
        input=MarketplaceStatusInput(listing_id=listing_id).model_dump(),
        idempotency_key=f"api-{uuid.uuid4().hex}",
    )
    out = await action.execute(env)
    return {"action_id": env.action_id, **out.model_dump()}


class WatchEntry(BaseModel):
    crm_offer_id: str
    account_id: str
    current_listing_id: str
    root_listing_id: str
    parent_listing_id: str | None = None
    generation: int = 0


@app.post("/api/watchlist", status_code=201)
async def watch_add(entry: WatchEntry, _: None = Depends(_api_key)):
    item = MonitoredListing(**entry.model_dump())
    _watchlist[item.current_listing_id] = item
    return item.model_dump()


@app.get("/api/watchlist")
async def watch_list(_: None = Depends(_api_key)):
    return [m.model_dump() for m in _watchlist.values()]


@app.get("/api/messages")
async def message_list(limit: int = 20, _: None = Depends(_api_key)):
    from facebook_camofox_client.domain_connectors.messages import MessagesClient

    rows, total = await MessagesClient().list_messages(limit=limit)
    return {"totalCount": total, "rows": rows}


@app.get("/api/messages/{message_id}")
async def message_get(message_id: str, _: None = Depends(_api_key)):
    from facebook_camofox_client.domain_connectors.messages import MessagesClient

    row = await MessagesClient().get_message(message_id)
    if row is None:
        raise HTTPException(status_code=404, detail="unknown message_id")
    return row


@app.get("/healthz")
async def healthz():
    return {"ok": True, "at": datetime.now(UTC).isoformat()}


def _account_store():
    from facebook_camofox_client.domain_accounts.store import SocialAccountStore

    return SocialAccountStore(os.getenv("SOCIAL_ACCOUNTS_DB", "state/social_accounts.db"))


class AccountBody(BaseModel):
    account_id: str
    label: str = ""
    platform: str = "facebook"
    cookies: list[dict] = Field(default_factory=list)


@app.post("/api/accounts", status_code=201)
async def account_save(body: AccountBody, _: None = Depends(_api_key)):
    try:
        _account_store().save(body.account_id, body.cookies,
                              label=body.label, platform=body.platform)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"account_id": body.account_id, "saved": True}


@app.get("/api/accounts")
async def account_list(_: None = Depends(_api_key)):
    return _account_store().metadata()


@app.delete("/api/accounts/{account_id}")
async def account_delete(account_id: str, _: None = Depends(_api_key)):
    if not _account_store().delete(account_id):
        raise HTTPException(status_code=404, detail="unknown account_id")
    return {"account_id": account_id, "deleted": True}


class ActionBody(BaseModel):
    account_id: str = "default"
    cookies: list[dict] | None = None
    idempotency_key: str | None = None
    input: dict = Field(default_factory=dict)


@app.get("/api/actions")
async def action_index(_: None = Depends(_api_key)):
    from facebook_camofox_client.api.actions import action_types

    return {"action_types": action_types()}


@app.post("/api/actions/{action_type}")
async def run_action(action_type: str, body: ActionBody, _: None = Depends(_api_key)):
    from facebook_camofox_client.api.actions import dispatch

    env = ActionEnvelope(
        action_id=f"api-{uuid.uuid4().hex[:12]}",
        action_type=action_type,
        account_id=body.account_id,
        input=body.input,
        idempotency_key=body.idempotency_key or f"api-{uuid.uuid4().hex}",
    )
    try:
        result = await dispatch(
            action_type, _manager(body.cookies), InMemoryEventEmitter(), env)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown action_type: {action_type}")
    return {"action_id": env.action_id, "action_type": action_type, "result": result}
