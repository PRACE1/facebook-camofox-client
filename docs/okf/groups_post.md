# groups.post action — behavior contract

## purpose

`GroupPostAction` opens a Facebook group, fills the `Create post` composer
(message + optional photos) and clicks Post. Same lifecycle shape as
`PostsListenAction`: acquire -> auth check -> fill -> receipt ->
emit `groups.post_completed` / `groups.post_failed` -> release.
`dry_run=True` default fills and stops before Post.

## composer findings (verified live 2026-09-10, group 305056891435827)

- Trigger `Write something...` opens a `Create post` dialog (not inline).
- Editor is `div[role=textbox][contenteditable=true]`; trusted
  `keyboard.type` registers it. Blue Post button is `role=button` name `Post`.
- Photo: `input[type=file][accept*=image]`, same as marketplace driver.

## evidence

- Live dry-run receipt `composer_filled_groupdry-20260910_061210.png`:
  dialog open, probe text filled, Post enabled, nothing posted.
- Live post 2026-09-10 (group 305056891435827): `posted=True`;
  `after_post` receipt caught mid-`Posting...` spinner (5s wait too short —
  bump to ~10s with dialog-close check); independent feed check
  (`scripts/check_group_post.py`, chronological sort + scroll) FOUND the
  post text live in Discussion.
- Unit: `tests/domain_groups/test_post.py` — dry-run + composer-miss
  (fakes, no browser). Suite: 9 passed with `tests/domain_marketplace`.

## limitations / follow-up

- Real Post click stays behind `dry_run=False`; needs the exact approved
  message (+ optional image) per run — no auto-posting.
- Anonymous-post toggle left untouched (posts as the account).
