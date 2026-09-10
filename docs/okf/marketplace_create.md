# marketplace.create + marketplace.status actions — behavior contract

## purpose

`MarketplaceCreateAction` fills `/marketplace/create/item` (Category, photos,
Title, Price, Condition, Description, Location) and publishes.
`MarketplaceStatusAction` polls `/marketplace/item/<id>/` and classifies
`active / under-review-duplicate / under-review / sold / removed / login-wall / unknown`.
Unknown stays unknown — never fabricated.

## public interface

`ActionEnvelope` with `input` for create:

```json
{
  "title": "Rubbish Removal in Galway",
  "price": "50",
  "category": "Household",
  "condition": "Used – fair",
  "description": "...",
  "location": "Galway, Ireland",
  "image_paths": ["tests/fixtures/groups_search/group_305056891435827_20260817T204349.png"],
  "dry_run": true
}
```

Status input: `{"listing_id": "38629807913299080"}`.

## DOM findings (verified live 2026-09-09, not guessed)

- Category `label[role=combobox]` has NO `aria-haspopup`; it opens a
  `MarketplaceComposerCategoryDropdown` dialog/popover, not a listbox.
  Chevron `i/svg` click is the reliable opener. Condition/Availability ARE
  listboxes (`aria-haspopup=listbox`).
- Next/Publish are `div[role=button]` with `aria-disabled`; Playwright
  `wait_for(state='enabled')` does not apply — poll the attribute.
- `locator.fill()` does not fire Location typeahead; trusted
  `keyboard.type(delay=30)` + ArrowDown/Enter does.
- Photos gate Next: 0/10 keeps `aria-disabled=true`. Missing image files
  fail loud (`images_not_found`), never silently skip.
- Seller dashboard opens a `Your listing` modal on click (no navigation);
  listing IDs are parsed from `a[href*="/marketplace/item/"]` hrefs.

## evidence

- Spike E2E published live: listing `38629807913299080`
  (`Rubbish Removal in Galway`, BWP50), landed on `you/selling` with
  `Listing published` toast. No ID in URL (dashboard) — captured via href scan.
- Live status check: `38629807913299080 -> under-review-duplicate`
  (matches `This might be a duplicate listing` banner — repeat runs reused
  the same placeholder PNG + title; account now holds 3-4 dupes).
- Live dry-run through the action: `published=False`,
  `marketplace.create_completed(dry_run=True)`, receipts saved.
- Unit: `tests/domain_marketplace` — 7 passed (fakes, no browser).
- Pre-existing failure (not from this change): 3x `tests/domain_posts`
  fail on clean tree too (`FakeNormalizer.normalize() got unexpected
  keyword 'raw'`).

## limitations / follow-up

- Real publish needs a UNIQUE photo + unique title per listing; the
  placeholder re-publish path is in duplicate hold.
- Delete duplicate test listings in `you/selling` before further publishes.
- Group post action not yet built (reuse session + form driver).
- `CamofoxSession.new_page()` added as the write-action seam;
  read actions still use `open_surface`/`execute`.

## addendum 2026-09-10 (all live-verified since)

- `CATEGORY_MAP` (`domain_marketplace/categories.py`): 13 hardcoded
  entries; unknown categories fail loud before any browser launches.
- Receipt = metadata + screenshot path (`success`, `published_at`,
  `listing_id`, `url`, `screenshot_path`); HTML stays a debug sidecar.
- REST: `api/app.py` — `POST /api/listings` (dry_run defaults true),
  `GET /api/listings/{id}/status`, `POST/GET /api/watchlist`,
  `GET /healthz`; served live on :8124, dry-run + status both 200.
- Relist watcher (`relist.py`, `health.py`, `assets.py`,
  `scripts/relist_watcher.py`): dashboard badges are source of truth —
  public item pages cache for hours AND dashboard cards are NOT anchors
  (zero `/item/` hrefs; match by title text, single long-word anchor
  because titles wrap across elements). Live cycle reads ACTIVE correctly.
- `1583545526797714` cleared review to `active`; photo swapped to
  `rubbish_galway_02.jpg` (2/10) via the dashboard modal path.
