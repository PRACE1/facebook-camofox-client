"""Generic action registry — every domain action passable over REST.

Typed convenience routes stay; this is the future-proof surface the
frontend builds against: POST /api/actions/{action_type}.
"""
from __future__ import annotations

from typing import Any


def _posts_listen(manager, emitter):
    from facebook_camofox_client.domain_cursors.repository import InMemoryCursorRepository
    from facebook_camofox_client.domain_posts.listen import PostsListenAction
    from facebook_camofox_client.domain_records.normalization import PostNormalizer

    collected: list = []

    async def commit(rec):
        collected.append(rec)
        return True

    return PostsListenAction(manager, InMemoryCursorRepository(),
                             PostNormalizer(), emitter, commit), None


def _groups_search(manager, emitter):
    from facebook_camofox_client.domain_cursors.repository import InMemoryCursorRepository
    from facebook_camofox_client.domain_groups.search import GroupsSearchAction
    from facebook_camofox_client.domain_records.normalization import PostNormalizer

    return GroupsSearchAction(manager, InMemoryCursorRepository(),
                              PostNormalizer(), emitter), None


def _groups_post(manager, emitter):
    from facebook_camofox_client.domain_groups.post import GroupPostAction

    return GroupPostAction(manager, emitter), None


def _marketplace_create(manager, emitter):
    from facebook_camofox_client.domain_marketplace.create import MarketplaceCreateAction
    from facebook_camofox_client.domain_marketplace.receipts import ReceiptStore

    return MarketplaceCreateAction(manager, emitter, ReceiptStore()), None


def _marketplace_status(manager, emitter):
    from facebook_camofox_client.domain_marketplace.status import MarketplaceStatusAction

    return MarketplaceStatusAction(manager, emitter), None


REGISTRY: dict[str, Any] = {
    "posts.listen": _posts_listen,
    "groups.search": _groups_search,
    "groups.post": _groups_post,
    "marketplace.create": _marketplace_create,
    "marketplace.status": _marketplace_status,
}


def action_types() -> list[str]:
    return sorted(REGISTRY)


async def dispatch(action_type: str, manager, emitter, envelope):
    try:
        builder = REGISTRY[action_type]
    except KeyError:
        raise KeyError(f"unknown action_type: {action_type}")
    action, _ = builder(manager, emitter)
    out = await action.execute(envelope)
    if hasattr(out, "model_dump"):
        return out.model_dump()
    return out
