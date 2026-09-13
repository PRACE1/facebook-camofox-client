import asyncio
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from camoufox.async_api import AsyncCamoufox

COOKIE_FILE = Path(os.getenv("CAMOFOX_STORAGE_STATE_LISTEN_GROUP",
                              str(Path.home() / "fb_cookies_playwright.json")))

DIAG = Path("artifacts/diagnostics")
DIAG.mkdir(parents=True, exist_ok=True)


async def main():
    print(f"Using storage state: {COOKIE_FILE}")
    async with AsyncCamoufox(headless=False) as browser:
        context = await browser.new_context(storage_state=str(COOKIE_FILE))
        page = await context.new_page()

        await page.goto("https://www.facebook.com/marketplace/create/item",
                        wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        opener = page.locator('label[role="combobox"]',
                              has_text=re.compile("Category", re.I)).first
        if await opener.count() == 0:
            print("Category opener not found!")
            return

        print("\n=== OPENER OUTER HTML (first 2000 chars) ===")
        print(await opener.evaluate("e=>e.outerHTML.slice(0,2000)"))

        # Click it (force)
        await opener.click(force=True, timeout=8000)
        await page.wait_for_timeout(1500)

        print("\n=== POPUP SCAN AFTER CLICK ===")
        for sel in [
            'div[role="listbox"]',
            'ul[role="listbox"]',
            'div[role="dialog"]',
            'div[role="menu"]',
            '[role="option"]',
            'input[placeholder*="Search"]',
            'input[aria-label*="Search"]',
            'div[aria-modal="true"]',
        ]:
            try:
                n = await page.locator(sel).count()
                print(f"{sel}: {n}")
                if n > 0:
                    try:
                        txt = await page.locator(sel).first.inner_text(timeout=2000)
                        print(f"   first text: {txt[:400]!r}")
                    except Exception as e:
                        print(f"   (no text: {e})")
            except Exception as e:
                print(f"{sel}: probe error {e}")

        # Also list every role=dialog/alertdialog etc with their aria-label
        print("\n=== ANY MODAL-LIKE CONTAINERS ===")
        containers = await page.evaluate("""() => {
            const roles = ['dialog','alertdialog','listbox','menu'];
            const out = [];
            for (const r of roles) {
                for (const el of document.querySelectorAll(`[role="${r}"]`)) {
                    out.push({
                        role: r,
                        ariaLabel: el.getAttribute('aria-label'),
                        ariaModal: el.getAttribute('aria-modal'),
                        text: (el.innerText || '').slice(0, 200),
                    });
                }
            }
            return out;
        }""")
        for c in containers:
            print(c)

        # Save artifacts
        await page.screenshot(path=str(DIAG / "category_after_click.png"), full_page=True)
        (DIAG / "category_after_click.html").write_text(
            await page.content(), encoding="utf-8"
        )
        print(f"\nSaved {DIAG}/category_after_click.png and .html")

        input("\nPress Enter to close browser...")


if __name__ == "__main__":
    asyncio.run(main())