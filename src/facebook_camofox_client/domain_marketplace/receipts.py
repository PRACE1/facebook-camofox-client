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
    def __init__(self, base_dir: str | Path = "artifacts/receipts") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save_debug(self, page, name: str) -> MarketplaceReceipt | None:
        try:
            png = self.base_dir / f"{name}.png"
            await page.screenshot(path=str(png), full_page=True)
            try:  # debug-only sidecar, never in the receipt payload
                (self.base_dir / f"{name}.html").write_text(
                    await page.content(), encoding="utf-8")
            except Exception:
                pass
            return MarketplaceReceipt(
                success=False, action_id=name, account_id="",
                screenshot_path=str(png))
        except Exception:
            return None


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
