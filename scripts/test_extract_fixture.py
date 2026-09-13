"""Validate PostExtractor.extract_from_relay against the real saved fixture.

No browser needed — reads the HTML already captured on disk.

Run from the repo root:
    python scripts\\test_extract_fixture.py
"""
import sys
from pathlib import Path

sys.path.insert(0, "src")

from facebook_camofox_client.domain_extraction.post_extractor import extract_from_relay

FIXTURE = Path(r"tests\fixtures\groups_search\group_305056891435827_20260818T015237.html")
GROUP_ID = "305056891435827"


def main():
    html = FIXTURE.read_text(encoding="utf-8")
    print(f"Loaded fixture: {len(html)} chars")

    result = extract_from_relay(html, expected_group_id=GROUP_ID, min_records=3, debug=True)

    print(f"\nOK: {result.ok}")
    print(f"Failure reason: {result.failure_reason}")
    print(f"Warning: {result.warning}")
    print(f"Records found: {len(result.records)}\n")

    for rec in result.records:
        print(f"--- post_id={rec.post_id} ---")
        print(f"  group_id:   {rec.group_id}")
        print(f"  author:     {rec.author_name} ({rec.author_id})")
        print(f"  created_at: {rec.created_at}")
        print(f"  text:       {(rec.text or '')[:100]!r}")
        print(f"  permalink:  {rec.permalink}")
        print(f"  source:     {rec.source}")
        print()


if __name__ == "__main__":
    main()
