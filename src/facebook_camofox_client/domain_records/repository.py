"""Record repository — persists normalized post records before cursors advance.

Dedupe key: account_id + group_id + post_id.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from facebook_camofox_client.domain_records.models import NormalizedPostRecord


class RecordRepository(ABC):
    """Abstract record storage interface."""

    @abstractmethod
    async def save(self, record: NormalizedPostRecord) -> None:
        """Persist a normalized record. Must complete before cursor.save()."""

    @abstractmethod
    async def exists(self, dedupe_key: str) -> bool:
        """Return True if a record with this dedupe key already exists."""


class InMemoryRecordRepository(RecordRepository):
    """Dev/test implementation — not durable across restarts."""

    def __init__(self) -> None:
        self._records: dict[str, NormalizedPostRecord] = {}

    def _dedupe_key(self, record: NormalizedPostRecord) -> str:
        # account_id + group_id + post_id
        return f"{record.account_id}:{record.group_id}:{record.external_id}"

    async def save(self, record: NormalizedPostRecord) -> None:
        key = self._dedupe_key(record)
        self._records[key] = record

    async def exists(self, dedupe_key: str) -> bool:
        return dedupe_key in self._records
