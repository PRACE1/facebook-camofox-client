"""Listen to a Facebook group using two adapters behind one interface:

- PageLoadRelayAdapter (page.content()): catches the initial server-side
  embedded post.
- NativeResponseAdapter (page.on("response")): catches posts loaded via
  scroll, by passively observing the page's own network responses.

Both feed into the same normalize -> validate -> dedupe pipeline
(extract_from_relay's invariants: post_id, associated_group, creation_time).

Run from the repo root:
    python scripts\\listen_group.py
"""
import asyncio
import sys

sys.path.insert(0, "src")

from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager
from facebook_camofox_client.domain_extraction.post_extractor import extract_from_relay
from facebook_camofox_client.domain_extraction.response_capture import NativeResponseAdapter

COOKIES_FILE = r"C:\Users\R5 5600 GT\fb_cookies_playwright.json"
GROUP_ID = "305056891435827"
TARGET_RECORDS = 5
MAX_SCROLL_STEPS = 12
SCROLL_PX = 700
PAUSE_MS = 1800


async def main():
    mgr = CamofoxSessionManager()
    session = await mgr.acquire(
        account_id="listen-group",
        storage_state_path=COOKIES_FILE,
    )

    adapter = NativeResponseAdapter(expected_group_id=GROUP_ID)

    try:
        # Create the page ourselves so we can attach the listener BEFORE
        # navigation, per VIBE BOT's guardrail.
        page = await session.context.new_page()
        adapter.attach(page)
        adapter.start()

        url = f"https://facebook.com/groups/{GROUP_ID}"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # PageLoadRelayAdapter: the initial embedded JSON snapshot.
        initial_html = await page.content()
        initial_result = extract_from_relay(initial_html, expected_group_id=GROUP_ID, min_records=0)
        adapter.merge_external(initial_result.records)
        print(f"Page-load adapter: {len(initial_result.records)} record(s) from embedded HTML")

        for step in range(MAX_SCROLL_STEPS):
            snapshot = adapter.snapshot()
            print(
                f"Step {step + 1}/{MAX_SCROLL_STEPS}: "
                f"{len(snapshot)} unique record(s) so far | counters={adapter.counters}"
            )

            if len(snapshot) >= TARGET_RECORDS:
                print(f"\nReached target of {TARGET_RECORDS} records, stopping scroll.")
                break

            await page.evaluate(f"window.scrollBy(0, {SCROLL_PX})")
            await page.wait_for_timeout(PAUSE_MS)

        # let the queue drain any in-flight responses from the last scroll
        await page.wait_for_timeout(1500)

        final_records = adapter.snapshot()
        print(f"\n=== Final counters === {adapter.counters}")
        print(f"=== Final: {len(final_records)} unique posts extracted ===\n")
        for rec in final_records:
            print(f"--- post_id={rec.post_id} (source={rec.source}) ---")
            print(f"  author:     {rec.author_name}")
            print(f"  created_at: {rec.created_at}")
            print(f"  text:       {(rec.text or '')[:80]!r}")
            print()

    finally:
        await adapter.stop()
        await mgr.release(session)


if __name__ == "__main__":
    asyncio.run(main())
