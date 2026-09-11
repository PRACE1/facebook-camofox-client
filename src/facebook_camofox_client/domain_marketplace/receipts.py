"""Marketplace receipt model + file store.

Receipt = metadata + screenshot path (per spec: skip raw HTML — pages are
tens of MB of minified JS DOM with zero verification value). HTML dumps
are still written beside the screenshot for debugging, but are NOT part
of the receipt payload.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel


class MarketplaceReceipt(BaseModel):
    success: bool = False
    action_id: str = ""
    account_id: str = ""
    listing_id: str | None = None
    listing_url: str | None = None
    published_at: str | None = None
    screenshot_path: str | None = None


class ReceiptStore:
    def __init__(self, base_dir: str | Path = "artifacts/receipts",
                 ttl_days: int = 7) -> None:
        self.base_dir = Path(base_dir)
        self.ttl_days = ttl_days
        self.base_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.purge_expired()  # automatic rolling TTL on every entry
        except Exception:
            pass

    def purge_expired(self) -> int:
        """Rolling TTL: delete receipt files older than ttl_days.
        Returns count removed. Screenshots are evidence; hundred-megabyte
        HTML dumps of third-party pages are not — HTML is never written."""
        import time

        cutoff = time.time() - self.ttl_days * 86400
        removed = 0
        for path in self.base_dir.iterdir():
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError:
                continue
        return removed

    async def save_debug(self, page, name: str) -> MarketplaceReceipt | None:
        try:
            png = self.base_dir / f"{name}.png"
            await page.screenshot(path=str(png), full_page=True)
            return MarketplaceReceipt(
                success=False, action_id=name, account_id="",
                screenshot_path=str(png))
        except Exception:
            return None


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
