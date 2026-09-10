# listing photo update — behavior notes

## flow (verified live 2026-09-10, listing 1583545526797714)

Dashboard `you/selling` -> card click -> `Your listing` modal ->
`Edit listing` LINK (`<a aria-label="Edit listing">`, NOT a button) ->
edit form -> `input[type=file][accept*=image]` -> wait `2/10` -> Update.

Dead ends found by dumps, do not retry without new evidence:

- Item-page `Edit` pill (`^Edit$` role match): mis-clicks, opens no form
  (`edit_dialog_20260910_062523` dump shows settings panel, zero
  `Edit listing`/`Save changes` markers).
- Seller card click does NOT navigate to `/item/<id>`; it opens the modal.
  IDs come from `a[href*="/marketplace/item/"]` href scans, never the URL.

## evidence

- `edit_dialog_20260910_063048.png`: edit form with 1/10 + Add-photo tile.
- `before_update_20260910_065735` (2/10) -> Update -> `after_update_*`.
- Status after swap: `1583545526797714 -> active`.
