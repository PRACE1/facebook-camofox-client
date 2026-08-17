# facebook-camofox-client

Camofox-native Facebook client for OpenMagpie.

## Target Runtime

JSON action envelope -> action runner -> account-scoped Camofox session -> normalized records -> cursors + events + metrics

## Structure

- `domain_actions/` - action envelope, runner, registry, idempotency
- `domain_accounts/` - session management, auth_guard, profiles
- `domain_camofox/` - session manager, launch config, capabilities
- `domain_groups/` - groups.search, groups.get, groups.join, membership
- `domain_posts/` - posts.listen, reply, engagement
- `domain_records/` - normalized record models, repository, normalization
- `domain_cursors/` - cursor models, repository, watermarks
- `domain_events/` - event models, emitter, deduplication
- `domain_connectors/` - OpenMagpie adapter

## First Vertical Slice

`groups.search` -> normalized post record -> persisted cursor -> `posts.new` event
