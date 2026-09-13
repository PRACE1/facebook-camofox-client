# twenty CRM write-back contract — as implemented

## direction

Push only. Our side POSTs webhook events to `MARKETPLACE_WEBHOOK_URL`
(Twenty `POST /api/webhooks/marketplace-events` or direct REST).
Unset URL = dev no-op. Delivery failure never crashes an action.

## events (see `domain_marketplace/webhooks.py`)

- `listing.created` — receipt generated (generation 0). Status starts
  `UNDER_REVIEW`; `price` parsed numeric (strips `P50`-style prefixes).
- `listing.health_checked` — every poll, includes `clicksCount` parsed
  from the dashboard card (`N clicks on listing`, else 0).
- `listing.superseded` — duplicate takedown reposted; old → `SUPERSEDED`
  + `supersededById`, new row with `parentListingId`, incremented generation.
- `listing.alert_raised` — `RETRY_EXHAUSTED` (budget spent), fatal safety
  stops (`COMMERCE_BAN` / `POLICY_VIOLATION` / checkpoint), repost failures.

## twenty object (John/CRM side)

`agencyListings`: `listingId` (unique), `status` select (ACTIVE,
UNDER_REVIEW, DUPLICATE, DELETED_BY_FB, SUPERSEDED, RETRY_EXHAUSTED,
POLICY_VIOLATION, UNKNOWN), `generation`, `rootListingId`,
`parentListingId`, `supersededById`, `title`, `locationQuery`, `price`,
`screenshotUrl`, `htmlReceiptUrl`, `clicksCount`, `lastCheckedAt`,
`nextCheckAt`, `lastError`; relations `offerId -> agencyOffer`,
`agencyLeadId -> agencyLead` via `{fieldName}Id` pattern (per dialer README
conventions: base URL ends in `/rest`, bearer auth).

## data-hygiene boundaries (non-target content, enforced in code)

- Twenty: `validate_outbound` blocks anything without a real `offerId`
  and a 10–20 digit Facebook id (mock/test/probe prefixes rejected)
  before any network request.
- Repo: `artifacts/`, `state/`, root dumps gitignored; fixtures stay
  synthetic/stock only, never client photos or scraped media.
- Local: receipts are screenshots + JSON only (HTML dumps cut);
  `ReceiptStore` enforces a 7-day rolling TTL automatically.

## daemon

- `scripts/relist_watcher.py`: one cycle per run; 12min first check,
  4h routine + 60–300s jitter; cooldowns 1h (retry 1) / 3h (retry 2).
- Single-flight via `domain_runtime/locking.py` (msvcrt/fcntl, fd-bound —
  no stale locks). Latecomer skips with exit 0.
- Linux: `deploy/facebook-relist-watcher.{service,timer}` (oneshot +
  4h `OnCalendar`, `RandomizedDelaySec=1800`). Windows: task snippet in
  `deploy/windows-task-scheduler.ps1.txt`.
- `RELIST_LIVE=1` publishes; unset = dry (prints what it would do).

- `scripts/relist_watcher.py`: one cycle per run; 12min first check,
  4h routine + 60–300s jitter; cooldowns 1h (retry 1) / 3h (retry 2).
- Single-flight via `domain_runtime/locking.py` (msvcrt/fcntl, fd-bound —
  no stale locks). Latecomer skips with exit 0.
- Linux: `deploy/facebook-relist-watcher.{service,timer}` (oneshot +
  4h `OnCalendar`, `RandomizedDelaySec=1800`). Windows: task snippet in
  `deploy/windows-task-scheduler.ps1.txt`.
- `RELIST_LIVE=1` publishes; unset = dry (prints what it would do).
