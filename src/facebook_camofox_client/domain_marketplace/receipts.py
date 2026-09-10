"""Marketplace receipt model + file store."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class MarketplaceReceipt(BaseModel):
    action_id: str
    account_id: str
    listing_id: str | None = None
    listing_url: str | None = None
    screenshot_path: str | None = None
    html_path: str | None = None


class ReceiptStore:
    def __init__(self, base_dir: str | Path = "artifacts/receipts") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save_debug(self, page, name: str) -> MarketplaceReceipt | None:
        try:
            png = self.base_dir / f"{name}.png"
            html = self.base_dir / f"{name}.html"
            await page.screenshot(path=str(png), full_page=True)
            html.write_text(await page.content(), encoding="utf-8")
            return MarketplaceReceipt(
                action_id=name, account_id="", screenshot_path=str(png), html_path=str(html))
        except Exception:
            return None
