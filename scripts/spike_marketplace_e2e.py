import asyncio
import os
import re
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from camoufox.async_api import AsyncCamoufox

COOKIE_FILE = Path(os.getenv("CAMOFOX_STORAGE_STATE_LISTEN_GROUP",
                              str(Path.home() / "fb_cookies_playwright.json")))
RECEIPTS_DIR = Path("artifacts/receipts")
RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)

PAYLOAD = {
    "title": "Rubbish Removal & Clearance in Galway",
    "price": "50",
    "category": "Household",
    "condition": "Used – fair",
    "description": "Yard, shed and household rubbish cleared across Galway city and county. Send a photo of the load for a same-day quote.",
    "location": "Galway, Ireland",
    "image_paths": [
        str(Path(__file__).parent.parent / "tests" / "fixtures" / "rubbish_galway_01.jpg"),
    ],
}

LISTBOX = 'div[role="listbox"]'
OPTIONS = 'div[role="listbox"] [role="option"]'
# Category is NOT a listbox (no aria-haspopup in dump 2026-09-09). It is
# MarketplaceComposerCategoryDropdown: label[role=combobox] opens a popover/
# dialog. Condition/Availability ARE listboxes. So wait for either.
PORTAL = 'div[role="listbox"], div[role="dialog"], div[role="menu"], ul[role="listbox"]'

async def dump_debug(page, name: str):
    try:
        await page.screenshot(path=str(RECEIPTS_DIR / f"{name}.png"), full_page=True)
        (RECEIPTS_DIR / f"{name}.html").write_text(await page.content(), encoding="utf-8")
    except Exception:
        pass

async def listbox_options(page, limit=10) -> list[str]:
    try:
        return await page.locator(OPTIONS).all_inner_texts() if await page.locator(OPTIONS).count() else []
    except Exception:
        return []

async def clear_and_type(locator, page, value: str, delay=20):
    await locator.scroll_into_view_if_needed()
    await locator.click(timeout=8000)
    await page.keyboard.press("ControlOrMeta+A")
    await page.keyboard.press("Backspace")
    await page.keyboard.type(str(value), delay=delay)
    try:
        actual = await locator.input_value(timeout=3000)
        if str(value) not in actual and actual not in str(value):
            await locator.fill(str(value), timeout=5000)
            await locator.evaluate("e=>e.dispatchEvent(new Event('input',{bubbles:true}))")
    except Exception:
        await locator.fill(str(value), timeout=5000)

async def open_combobox(page, name: str) -> bool:
    opener = page.locator('label[role="combobox"]', has_text=re.compile(name, re.I)).first
    if await opener.count() == 0:
        print(f"  [combobox] '{name}' not found")
        return False
    await opener.scroll_into_view_if_needed()
    try:
        dbg = (await opener.evaluate("e=>e.outerHTML") or "")[:400]
        print(f"  [combobox] '{name}' html: {dbg}")
    except Exception:
        pass

    async def portal_visible() -> bool:
        # Category dialog mounts outside the form; Condition uses listbox.
        # Accept either, plus aria-expanded flip as signal.
        try:
            await page.locator(PORTAL).first.wait_for(state="visible", timeout=1500)
            return True
        except Exception:
            pass
        try:
            if (await opener.get_attribute("aria-expanded")) == "true":
                return True
        except Exception:
            pass
        return False

    if await portal_visible():
        return True
    # chevron <i> on the right is the real click target on this widget
    try:
        chev = opener.locator('i, svg').first
        if await chev.count() > 0:
            await chev.click(timeout=4000)
            if await portal_visible():
                print(f"  [combobox] '{name}' opened via chevron.click")
                return True
            await page.keyboard.press("Escape")
    except Exception:
        pass
    inners = opener.locator("div, span")
    n_inner = min(await inners.count(), 6)
    for i in range(n_inner):
        try:
            await inners.nth(i).click(timeout=4000)
            if await portal_visible():
                print(f"  [combobox] '{name}' opened via inner[{i}].click")
                return True
        except Exception:
            pass
        await page.keyboard.press("Escape")
    try:
        await opener.click(timeout=5000)
        if await portal_visible():
            print(f"  [combobox] '{name}' opened via label.click")
            return True
    except Exception:
        pass
    await page.keyboard.press("Escape")
    for key in ["ArrowDown", "Enter", "Space"]:
        try:
            await opener.focus(timeout=2000)
            await page.keyboard.press(key)
            if await portal_visible():
                print(f"  [combobox] '{name}' opened via keyboard[{key}]")
                return True
        except Exception:
            pass
        await page.keyboard.press("Escape")
    # final state log — do NOT guess, show what actually mounted
    try:
        exp = await opener.get_attribute("aria-expanded")
        n_p = await page.locator(PORTAL).count()
        n_o = await page.locator(OPTIONS).count()
        print(f"  [combobox] '{name}' failed; aria-expanded={exp} portals={n_p} options={n_o} opts: {await listbox_options(page)}")
    except Exception:
        print(f"  [combobox] '{name}' failed; opts: {await listbox_options(page)}")
    await dump_debug(page, f"combobox_fail_{name.lower()}")
    return False

async def combobox_has_value(page, name: str, want: str) -> bool:
    try:
        t = (await page.locator('label[role="combobox"]', has_text=re.compile(name, re.I)).first.inner_text(timeout=5000) or "")
        return want.strip().lower() in t.strip().lower()
    except Exception:
        return False

async def pick_option(page, want: str) -> bool:
    # Case A: classic listbox options (Condition, Location, Availability)
    if await page.locator(OPTIONS).count() > 0:
        print(f"  [options] {(await listbox_options(page))[:8]}")
        norm = lambda s: re.sub(r"[\u2013\u2014\u2212]", "-", s or "").strip().lower()
        want_n, count = norm(want), await page.locator(OPTIONS).count()
        for i in range(count):
            try:
                if norm(await page.locator(OPTIONS).nth(i).inner_text()) == want_n:
                    await page.locator(OPTIONS).nth(i).click(timeout=5000)
                    return True
            except Exception: continue
        for i in range(count):
            try:
                t = norm(await page.locator(OPTIONS).nth(i).inner_text())
                if want_n in t or t in want_n:
                    await page.locator(OPTIONS).nth(i).click(timeout=5000)
                    return True
            except Exception: continue
        try:
            await page.locator(OPTIONS).first.click(timeout=5000)
            return True
        except Exception: return False
    # Case B: Category taxonomy dialog/popover — search then pick
    try:
        dlg = page.locator('div[role="dialog"]').last
        if await dlg.count() > 0 and await dlg.is_visible():
            search = dlg.locator('input[placeholder*="Search"], input[type="search"], input[type="text"]').first
            if await search.count() > 0:
                await search.click(timeout=4000)
                await search.fill("", timeout=4000)
                await search.type(want, delay=30)
                await page.wait_for_timeout(1500)
            btn = dlg.get_by_role("button", name=re.compile(re.escape(want), re.I)).first
            if await btn.count() == 0:
                btn = page.get_by_role("button", name=re.compile(re.escape(want), re.I)).first
            await btn.wait_for(state="visible", timeout=8000)
            await btn.click(timeout=5000)
            return True
    except Exception as e:
        print(f"  [dialog-pick] miss ({e})")
    try:
        await page.locator(OPTIONS).first.wait_for(state="visible", timeout=3000)
        await page.locator(OPTIONS).first.click(timeout=5000)
        return True
    except Exception:
        return False

async def select_combobox(page, name: str, value: str) -> bool:
    if not value: return True
    if not await open_combobox(page, name): return False
    ok = await pick_option(page, value)
    await page.wait_for_timeout(1000)
    await page.keyboard.press("Escape")
    return ok

async def wait_enabled_and_click(page, name_regex, timeout=15000):
    deadline = asyncio.get_event_loop().time() + timeout / 1000
    btn, last_state = None, "unknown"
    while asyncio.get_event_loop().time() < deadline:
        cands = page.get_by_role("button", name=name_regex)
        picked = None
        for i in range(await cands.count()):
            c = cands.nth(i)
            try:
                if await c.is_visible(): picked = c; break
            except Exception: continue
        if picked is None:
            last_state = "not-visible"; await page.wait_for_timeout(500); continue
        btn = picked
        try:
            aria = await btn.get_attribute("aria-disabled")
            dis = await btn.is_disabled()
            last_state = f"aria-disabled={aria} is_disabled={dis}"
            if aria != "true" and not dis: break
        except Exception as e: last_state = f"probe-error {e}"
        await page.wait_for_timeout(500)
    else:
        await dump_debug(page, "next_publish_disabled")
        raise TimeoutError(f"button {name_regex.pattern} never enabled ({last_state})")
    await btn.scroll_into_view_if_needed()
    await btn.click(timeout=8000)

async def capture_dashboard_listing_id(page, ts: str, timeout=20000) -> str | None:
    """On /you/selling, seller clicks open a 'Your listing' modal (no navigation),
    so parse item hrefs from the hydrated DOM. Returns newest ID or None."""
    try:
        await page.get_by_text(re.compile(r"Your listings", re.I)).first.wait_for(state="visible", timeout=timeout)
    except Exception:
        pass
    # dashboard hydrates links late — poll DOM, not just locator count
    hrefs: list[str] = []
    for _ in range(10):
        try:
            hrefs = await page.evaluate(
                """() => Array.from(document.querySelectorAll('a[href*="/marketplace/item/"]')).map(a=>a.getAttribute('href')||'')""")
            hrefs = [h for h in hrefs if "/item/" in h]
            if hrefs:
                break
        except Exception:
            pass
        await page.wait_for_timeout(1000)
    if hrefs:
        m = re.search(r"/item/(\d+)", hrefs[0])
        if m:
            print(f"  dashboard link ID: {m.group(1)} (of {len(hrefs)} links)")
            try:
                body = (await page.locator("body").inner_text(timeout=5000) or "").lower()
                if "duplicate listing" in body:
                    print("  WARNING: Facebook flags this as a duplicate (same photo/title). Use a unique photo + title per run; delete dupes in you/selling.")
                    await dump_debug(page, f"duplicate_warning_{ts}")
            except Exception:
                pass
            return m.group(1)
    # fallback: click newest card to open modal (proves it published), then re-scan.
    # NOTE: seller click opens a modal, it does NOT navigate to /item/<id>.
    try:
        card = page.get_by_text(re.compile(re.escape(PAYLOAD["title"]), re.I)).first
        await card.scroll_into_view_if_needed()
        await card.click(timeout=8000)
        await page.wait_for_timeout(3000)
        await dump_debug(page, f"listing_captured_{ts}")
        hrefs2 = await page.evaluate(
            """() => Array.from(document.querySelectorAll('a[href*="/marketplace/item/"]')).map(a=>a.getAttribute('href')||'')""")
        for h in hrefs2:
            m2 = re.search(r"/item/(\d+)", h or "")
            if m2:
                print(f"  card-modal scan ID: {m2.group(1)}")
                return m2.group(1)
        print("  modal opened (no navigation expected for seller); ID from href scan above if any.")
        return None
    except Exception as e:
        print(f"  card click miss ({e})")
    await dump_debug(page, f"listing_capture_miss_{ts}")
    return None


async def run_marketplace_spike():
    if not COOKIE_FILE.exists():
        raise FileNotFoundError(f"Cookie file not found at {COOKIE_FILE}")
    print(f"Using storage state: {COOKIE_FILE}")
    browser = context = None
    try:
        browser_ctx = AsyncCamoufox(headless=False)
        browser = await browser_ctx.__aenter__()
        context = await browser.new_context(storage_state=str(COOKIE_FILE))
        page = await context.new_page()
        await page.goto("https://www.facebook.com/marketplace/create/item", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        if "login" in page.url.lower():
            await dump_debug(page, "auth_required")
            raise RuntimeError(f"Auth required, landed on {page.url}")
        cat = page.locator('label[role="combobox"]', has_text=re.compile("Category", re.I)).first
        if await cat.count() > 0:
            if await combobox_has_value(page, "Category", PAYLOAD["category"]):
                print(f"Category already set: {PAYLOAD['category']}")
            elif await select_combobox(page, "Category", PAYLOAD["category"]):
                await page.wait_for_timeout(2000)
            # draft-restore race: dump showed Household present even when open
            # failed earlier — re-check before aborting.
            elif await combobox_has_value(page, "Category", PAYLOAD["category"]):
                print(f"Category now set after attempts: {PAYLOAD['category']}")
            else:
                print("  Category could not be set; aborting."); return
        print("Uploading images...")
        file_input = page.locator('input[type="file"][accept*="image"]').first
        if await file_input.count() == 0:
            await dump_debug(page, "no_file_input")
            print("  ABORT: file input not found."); return
        existing = [p for p in PAYLOAD["image_paths"] if Path(p).exists()]
        missing = [p for p in PAYLOAD["image_paths"] if not Path(p).exists()]
        if missing:
            print(f"  missing files: {missing}")
        if not existing:
            await dump_debug(page, "no_images_found")
            print(f"  ABORT: no image files exist. Photos are required (form shows 0/10, Next stays disabled). Put a .jpg in tests/fixtures/ and update PAYLOAD['image_paths'].")
            return
        await file_input.set_input_files(existing)
        print(f"  uploaded {len(existing)} file(s), waiting for thumbnails...")
        try:
            await page.get_by_text(re.compile(r"1\s*/\s*10|Photos\s*.\s*1", re.I)).first.wait_for(state="visible", timeout=15000)
            print("  photos attached (1/10 seen).")
        except Exception:
            await page.wait_for_timeout(3000)
            print("  WARNING: 1/10 marker not seen — check screenshot, Next may stay disabled.")
        await dump_debug(page, "after_upload")
        text_inputs = page.locator('input[type="text"]:not([role="combobox"])')
        await text_inputs.first.wait_for(state="visible", timeout=10000)
        print("Filling Title...")
        await clear_and_type(text_inputs.nth(0), page, PAYLOAD["title"])
        print("Filling Price...")
        await clear_and_type(text_inputs.nth(1), page, PAYLOAD["price"])
        if PAYLOAD.get("condition"):
            print(f"Selecting Condition: {PAYLOAD['condition']}...")
            if not await select_combobox(page, "Condition", PAYLOAD["condition"]):
                await dump_debug(page, "condition_miss")
        print("Filling Description...")
        desc = page.locator("textarea").first
        await desc.wait_for(state="visible", timeout=10000)
        await clear_and_type(desc, page, PAYLOAD["description"], delay=10)
        print(f"Filling Location: {PAYLOAD['location']}...")
        loc = page.locator('input[role="combobox"][aria-label="Location"]').first
        await loc.wait_for(state="visible", timeout=10000)
        await loc.click(timeout=8000)
        await page.keyboard.press("ControlOrMeta+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(PAYLOAD["location"], delay=30)
        try:
            await page.locator(OPTIONS).first.wait_for(state="visible", timeout=8000)
            if not await pick_option(page, PAYLOAD["location"].split(",")[0].strip()):
                await pick_option(page, PAYLOAD["location"])
            print("  Location selected via listbox.")
        except Exception:
            await page.keyboard.press("ArrowDown"); await page.keyboard.press("Enter")
            await page.wait_for_timeout(1500)
            try:
                val = await loc.input_value(timeout=3000)
                print(f"  Location confirmed via Enter (value={val!r}).")
            except Exception:
                print("  Location fallback ArrowDown+Enter (unverified).")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        await page.screenshot(path=str(RECEIPTS_DIR / f"marketplace_form_filled_{ts}.png"), full_page=True)
        (RECEIPTS_DIR / f"marketplace_form_filled_{ts}.html").write_text(await page.content(), encoding="utf-8")
        print("Clicking Next...")
        await wait_enabled_and_click(page, re.compile(r"^Next$", re.I))
        await page.wait_for_timeout(3000)
        await dump_debug(page, f"after_next_{ts}")
        print(f"  after Next URL: {page.url}")
        print("Clicking Publish...")
        try:
            await wait_enabled_and_click(page, re.compile(r"^(Publish|Share|Post)$", re.I), timeout=15000)
            await page.wait_for_timeout(5000)
        except Exception as e:
            await dump_debug(page, f"publish_blocked_{ts}")
            print(f"  Publish blocked ({e}).")
            if os.getenv("MANUAL_PUBLISH") == "1":
                input("Press Enter after clicking Publish...")
            else: raise
        await dump_debug(page, f"after_publish_{ts}")
        # step=audience is an intermediate cross-post screen, not the listing.
        # Try one more confirm if we are still on create/item.
        if "create/item" in page.url:
            print(f"  still on create flow: {page.url} — trying final confirm...")
            try:
                await wait_enabled_and_click(page, re.compile(r"^(Publish|Share|Post|Done)$", re.I), timeout=10000)
                await page.wait_for_timeout(5000)
                await dump_debug(page, f"after_confirm_{ts}")
            except Exception as e:
                print(f"  no final confirm clickable ({e}). Inspect after_publish shot.")
        final_url = page.url
        m = re.search(r"/item/(\d+)", final_url)
        listing_id = m.group(1) if m else None
        # Better: dashboard URL (/you/selling) has no ID. Click newest card.
        if not listing_id and "you/selling" in final_url:
            print("  on selling dashboard — capturing newest listing ID...")
            listing_id = await capture_dashboard_listing_id(page, ts)
            final_url = page.url
        print(f"\n--- SPIKE COMPLETE ---\nListing ID: {listing_id}\nURL: {final_url}")
    finally:
        try:
            if context: await context.close()
        finally:
            if browser:
                try: await browser_ctx.__aexit__(None, None, None)
                except Exception: pass

if __name__ == "__main__":
    asyncio.run(run_marketplace_spike())