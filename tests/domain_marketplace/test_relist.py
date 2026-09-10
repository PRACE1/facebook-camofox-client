"""Relist state machine + assets tests — pure logic, no browser.

Asset photo tests use a generated bitmap (no real listing data)."""
import random
from datetime import UTC

from PIL import Image

from facebook_camofox_client.domain_marketplace.assets import (
    build_replacement,
    mutate_photo,
    render_spintax,
)
from facebook_camofox_client.domain_marketplace.health import classify_dashboard_card
from facebook_camofox_client.domain_marketplace.relist import (
    ListingHealthStatus,
    MonitoredListing,
    RelistPolicyConfig,
    evaluate_relist_trigger,
    is_due,
)


def base_listing(gen=0):
    return MonitoredListing(crm_offer_id="offer-1", account_id="acc",
                            current_listing_id="111", root_listing_id="111",
                            generation=gen)


def test_healthy_never_reposts():
    cfg = RelistPolicyConfig()
    for st in (ListingHealthStatus.ACTIVE, ListingHealthStatus.UNDER_REVIEW,
               ListingHealthStatus.SOLD, ListingHealthStatus.UNKNOWN):
        d = evaluate_relist_trigger(base_listing(), st, cfg)
        assert d.should_repost is False


def test_fatal_states_lock():
    cfg = RelistPolicyConfig()
    for st in (ListingHealthStatus.POLICY_VIOLATION, ListingHealthStatus.COMMERCE_BAN,
               ListingHealthStatus.CHECKPOINT_REQUIRED):
        d = evaluate_relist_trigger(base_listing(), st, cfg)
        assert d.should_repost is False and d.fatal_error is True


def test_duplicate_reposts_with_cooldown_then_exhausts():
    cfg = RelistPolicyConfig()
    d0 = evaluate_relist_trigger(base_listing(0), ListingHealthStatus.DUPLICATE_TAKEDOWN, cfg)
    assert d0.should_repost and d0.next_generation == 1
    assert d0.cooldown_seconds == cfg.cooldown_retry_1_seconds
    d1 = evaluate_relist_trigger(base_listing(1), ListingHealthStatus.DUPLICATE_TAKEDOWN, cfg)
    assert d1.should_repost and d1.next_generation == 2
    assert d1.cooldown_seconds == cfg.cooldown_retry_2_seconds
    d2 = evaluate_relist_trigger(base_listing(2), ListingHealthStatus.DUPLICATE_TAKEDOWN, cfg)
    assert d2.should_repost is False and "max repost" in d2.reason


def test_dashboard_classifier():
    assert classify_dashboard_card("Active · Listed on 09/09") == ListingHealthStatus.ACTIVE
    assert classify_dashboard_card("This listing is being reviewed") == ListingHealthStatus.UNDER_REVIEW
    assert classify_dashboard_card("This might be a duplicate listing") == ListingHealthStatus.DUPLICATE_TAKEDOWN
    assert classify_dashboard_card("You're unable to buy or sell") == ListingHealthStatus.COMMERCE_BAN
    assert classify_dashboard_card("blah", still_listed=False) == ListingHealthStatus.DELETED_BY_FB
    assert classify_dashboard_card("") == ListingHealthStatus.UNKNOWN


def test_spintax_renders_options(tmp_path=None):
    out = {render_spintax("{Quick|Same-Day} {Junk|Rubbish} Removal", random.Random(i))
           for i in range(20)}
    assert len(out) > 1
    assert all("Removal" in o and "{" not in o for o in out)


def test_mutate_changes_bytes_and_strips(tmp_path):
    src = tmp_path / "pool.jpg"
    Image.new("RGB", (200, 200), (120, 30, 200)).save(src)
    dest, mutated = mutate_photo(str(src), tmp_path / "out", seed=7)
    assert mutated is True
    assert (src.read_bytes() != __import__("pathlib").Path(dest).read_bytes())


def test_build_replacement_picks_pool(tmp_path):
    p1 = tmp_path / "a.jpg"
    Image.new("RGB", (100, 100), (10, 10, 10)).save(p1)
    rep = build_replacement("{Hi|Hello} {A|B}", "d {x|y}", [str(p1)], tmp_path / "out", seed=3)
    assert rep["image_path"].endswith(".jpg") and rep["pixels_mutated"] is True
    assert "{" not in rep["title"]


def test_is_due_gates_cooldown():
    from datetime import datetime, timedelta
    assert is_due(base_listing()) is True
    future = base_listing()
    future.next_eligible_at = datetime.now(UTC) + timedelta(hours=2)
    assert is_due(future) is False
    past = base_listing()
    past.next_eligible_at = datetime.now(UTC) - timedelta(minutes=1)
    assert is_due(past) is True
