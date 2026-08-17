import os

os.makedirs("src/facebook_camofox_client/domain_groups", exist_ok=True)
os.makedirs("docs/okf/primitives", exist_ok=True)

# pyproject.toml
with open("pyproject.toml", "w", encoding="utf-8") as f:
    f.write('[project]\n')
    f.write('name = "facebook-camofox-client"\n')
    f.write('version = "0.1.0"\n')
    f.write('description = "Camofox-native Facebook client for OpenMagpie"\n')
    f.write('requires-python = ">=3.11"\n')
    f.write('dependencies = [\n')
    f.write('    "camofox",\n')
    f.write('    "pydantic>=2.0",\n')
    f.write(']\n')
    f.write('\n')
    f.write('[project.optional-dependencies]\n')
    f.write('dev = ["pytest", "ruff", "mypy"]\n')
    f.write('\n')
    f.write('[tool.ruff]\n')
    f.write('line-length = 100\n')

# README.md
with open("README.md", "w", encoding="utf-8") as f:
    f.write("# facebook-camofox-client\n\n")
    f.write("Camofox-native Facebook client for OpenMagpie.\n\n")
    f.write("## Target Runtime\n\n")
    f.write("JSON action envelope -> action runner -> account-scoped Camofox session -> normalized records -> cursors + events + metrics\n\n")
    f.write("## Structure\n\n")
    f.write("- `domain_actions/` - action envelope, runner, registry, idempotency\n")
    f.write("- `domain_accounts/` - session management, auth_guard, profiles\n")
    f.write("- `domain_camofox/` - session manager, launch config, capabilities\n")
    f.write("- `domain_groups/` - groups.search, groups.get, groups.join, membership\n")
    f.write("- `domain_posts/` - posts.listen, reply, engagement\n")
    f.write("- `domain_records/` - normalized record models, repository, normalization\n")
    f.write("- `domain_cursors/` - cursor models, repository, watermarks\n")
    f.write("- `domain_events/` - event models, emitter, deduplication\n")
    f.write("- `domain_connectors/` - OpenMagpie adapter\n\n")
    f.write("## First Vertical Slice\n\n")
    f.write("`groups.search` -> normalized post record -> persisted cursor -> `posts.new` event\n")

# __init__.py
with open("src/facebook_camofox_client/__init__.py", "w", encoding="utf-8") as f:
    f.write('"""facebook-camofox-client: Camofox-native Facebook client for OpenMagpie."""\n')
    f.write('__version__ = "0.1.0"\n')

# domain_groups/__init__.py
with open("src/facebook_camofox_client/domain_groups/__init__.py", "w", encoding="utf-8") as f:
    f.write('"""Domain: Facebook Groups."""\n')

# domain_groups/schemas.py
with open("src/facebook_camofox_client/domain_groups/schemas.py", "w", encoding="utf-8") as f:
    f.write('"""Group action schemas."""\n\n')
    f.write("from __future__ import annotations\n\n")
    f.write("from pydantic import BaseModel, Field\n\n\n")
    f.write("class GroupsSearchInput(BaseModel):\n")
    f.write('    group_ids: list[str] = Field(default_factory=list)\n')
    f.write('    terms: list[str] = Field(default_factory=list)\n')
    f.write('    limit: int = Field(default=20, ge=1, le=100)\n')
    f.write('    cursor: str | None = None\n')
    f.write('    since: str | None = None\n\n\n')
    f.write("class GroupsSearchOutput(BaseModel):\n")
    f.write('    results: list[dict] = Field(default_factory=list)\n')
    f.write('    cursor: dict = Field(default_factory=dict)\n')
    f.write('    matched_terms: list[str] = Field(default_factory=list)\n')

# groups-search.md - written line by line to avoid quote issues
md_lines = [
    "---",
    "type: primitive",
    "title: Groups Search",
    "id: groups.search",
    "version: 0.1.0",
    "domain: groups",
    "runtime: camofox",
    "status: extracted",
    "---",
    "",
    "# groups.search",
    "",
    "## purpose",
    "",
    "Find and normalize Facebook group/post results for a configured account.",
    "",
    "## input",
    "",
    "```json",
    '{',
    '  "group_ids": [],',
    '  "terms": [],',
    '  "limit": 20,',
    '  "cursor": null,',
    '  "since": null',
    '}',
    "```",
    "",
    "## output",
    "",
    "```json",
    '{',
    '  "results": [],',
    '  "cursor": {},',
    '  "matched_terms": []',
    '}',
    "```",
    "",
    "## runtime",
    "",
    "The action requests an account-scoped Camofox session. Humanization, profile state, proxy configuration, navigation, interaction, and extraction remain inside the Camofox boundary.",
    "",
    "## persistence",
    "",
    "Write normalized post records before advancing the cursor.",
    "",
    "## events",
    "",
    "- `groups.search_started`",
    "- `groups.result_found`",
    "- `groups.search_completed`",
    "- `groups.search_failed`",
    "",
    "## failure states",
    "",
    "- authentication required",
    "- membership required",
    "- content unavailable",
    "- timeout",
    "- extraction failure",
]

with open("docs/okf/primitives/groups-search.md", "w", encoding="utf-8") as f:
    for line in md_lines:
        f.write(line + "\n")

print("All files created.")