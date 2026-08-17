---
type: primitive
title: Groups Search
id: groups.search
version: 0.1.0
domain: groups
runtime: camofox
status: extracted
---

# groups.search

## purpose

Find and normalize Facebook group/post results for a configured account.

## input

```json
{
  "group_ids": [],
  "terms": [],
  "limit": 20,
  "cursor": null,
  "since": null
}
```

## output

```json
{
  "results": [],
  "cursor": {},
  "matched_terms": []
}
```

## runtime

The action requests an account-scoped Camofox session. Humanization, profile state, proxy configuration, navigation, interaction, and extraction remain inside the Camofox boundary.

## persistence

Write normalized post records before advancing the cursor.

## events

- `groups.search_started`
- `groups.result_found`
- `groups.search_completed`
- `groups.search_failed`

## failure states

- authentication required
- membership required
- content unavailable
- timeout
- extraction failure
