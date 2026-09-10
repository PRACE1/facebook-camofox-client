"""Create the agencyListings object + fields in Twenty via metadata GraphQL.

Dry-printable without credentials (shows exact mutations); live with
TWENTY_BASE_URL + TWENTY_API_KEY set. Follows the dialer README's
metadata patterns (relation joinColumnName {fieldName}Id).

Usage:
  python scripts\\twenty_setup.py --print      # show mutations only
  python scripts\\twenty_setup.py --apply      # create for real
"""
import asyncio
import json
import os
import sys

FIELDS: list[dict] = [
    {"name": "listingId", "label": "Listing ID", "type": "TEXT"},
    {"name": "status", "label": "Status", "type": "SELECT",
     "options": ["ACTIVE", "UNDER_REVIEW", "DUPLICATE", "DELETED_BY_FB",
                 "SUPERSEDED", "RETRY_EXHAUSTED", "POLICY_VIOLATION", "UNKNOWN"]},
    {"name": "generation", "label": "Generation", "type": "NUMBER"},
    {"name": "rootListingId", "label": "Root listing ID", "type": "TEXT"},
    {"name": "parentListingId", "label": "Parent listing ID", "type": "TEXT"},
    {"name": "supersededById", "label": "Superseded by ID", "type": "TEXT"},
    {"name": "title", "label": "Title", "type": "TEXT"},
    {"name": "locationQuery", "label": "Location query", "type": "TEXT"},
    {"name": "price", "label": "Price", "type": "NUMBER"},
    {"name": "screenshotUrl", "label": "Screenshot URL", "type": "TEXT"},
    {"name": "htmlReceiptUrl", "label": "HTML receipt URL", "type": "TEXT"},
    {"name": "clicksCount", "label": "Clicks", "type": "NUMBER"},
    {"name": "lastCheckedAt", "label": "Last checked", "type": "DATE_TIME"},
    {"name": "nextCheckAt", "label": "Next check", "type": "DATE_TIME"},
    {"name": "lastError", "label": "Last error", "type": "TEXT"},
]

CREATE_OBJECT = """mutation {
  createOneObject(input: {object: {
    nameSingular: "agencyListing" namePlural: "agencyListings"
    labelSingular: "Listing" labelPlural: "Listings"
    description: "Facebook Marketplace listings synced from facebook-camofox-client"
    icon: "IconTag"
  }}) { id nameSingular }
}"""


def build_plan() -> dict:
    return {"createObject": CREATE_OBJECT, "fields": FIELDS}


async def apply_plan() -> int:
    import httpx

    base = (os.getenv("TWENTY_BASE_URL") or "").rstrip("/")
    key = os.getenv("TWENTY_API_KEY") or ""
    if not base or not key:
        print("TWENTY_BASE_URL + TWENTY_API_KEY required for --apply")
        return 2
    plan = build_plan()
    async with httpx.AsyncClient(timeout=30) as client:
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        r = await client.post(f"{base}/graphql", json={"query": plan["createObject"]},
                              headers=headers)
        print(f"createObject -> HTTP {r.status_code}")
        print(json.dumps(plan["fields"], indent=1)[:500], "...")
        print("NOTE: create fields via Twenty UI or metadata createOneField per entry above.")
    return 0


def main() -> None:
    if "--print" in sys.argv or len(sys.argv) < 2:
        print(json.dumps(build_plan(), indent=1))
        return
    if "--apply" in sys.argv:
        sys.exit(asyncio.run(apply_plan()))


if __name__ == "__main__":
    main()
