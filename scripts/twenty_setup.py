"""Create the agencyListings object + fields in Twenty via metadata GraphQL.

Dry-printable without credentials (shows exact mutations); live with
TWENTY_BASE_URL + TWENTY_API_KEY set. Idempotent: existing object/fields
are detected and skipped, so re-running is safe.

Proven live against twenty.inferencesaver.com: metadata endpoint is
POST <base>/metadata (NOT /graphql); object mutation
CreateOneObjectMetadataItem; fields via createOneField(input: {field:
CreateFieldInput}) with objectMetadataId.

Usage:
  python scripts\\twenty_setup.py --print      # show mutations only
  python scripts\\twenty_setup.py --apply      # create for real
"""
import asyncio
import json
import os
import sys

OBJECT_IDENTITY = {
    "nameSingular": "agencyListing",
    "namePlural": "agencyListings",
}

FIELDS: list[dict] = [
    {"name": "listingId", "label": "Listing ID", "type": "TEXT"},
    {"name": "status", "label": "Status", "type": "SELECT",
     "options": ["ACTIVE", "UNDER_REVIEW", "DUPLICATE_TAKEDOWN", "DELETED_BY_FB",
                 "POLICY_VIOLATION", "COMMERCE_BAN", "CHECKPOINT_REQUIRED",
                 "SOLD", "RETRY_EXHAUSTED", "UNKNOWN"]},
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
    {"name": "offerId", "label": "Offer ID", "type": "TEXT"},
    {"name": "agencyLeadId", "label": "Agency lead ID", "type": "TEXT"},
]

CREATE_OBJECT = """mutation CreateOneObjectMetadataItem($input: CreateOneObjectInput!) {
  createOneObject(input: $input) { id nameSingular namePlural }
}"""
CREATE_FIELD = """mutation CreateField($input: CreateOneFieldMetadataInput!) {
  createOneField(input: $input) { id name }
}"""
LIST_OBJECTS = """{
  objects(paging: {first: 200}) { edges { node { id nameSingular namePlural } } } }"""


async def find_object(client, headers: dict, base: str, plural: str) -> dict | None:
    r = await client.post(f"{base}/metadata", json={"query": LIST_OBJECTS},
                          headers=headers)
    edges = (r.json().get("data") or {}).get("objects", {}).get("edges", [])
    for e in edges:
        if e["node"].get("namePlural") == plural:
            return e["node"]
    return None
LIST_FIELDS = """query($objectId: UUID!) {
  object(id: $objectId) { fields { id name } }
}"""

def build_plan() -> dict:
    return {"createObject": CREATE_OBJECT, "fields": FIELDS}


async def apply_plan() -> int:
    import httpx

    base = (os.getenv("TWENTY_BASE_URL") or "").rstrip("/").replace("/rest", "")
    key = os.getenv("TWENTY_API_KEY") or ""
    if not base or not key:
        print("TWENTY_BASE_URL + TWENTY_API_KEY required for --apply")
        return 2
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. find or create the object (paginated: new objects sit past page 1)
        found = await find_object(client, headers, base, OBJECT_IDENTITY["namePlural"])
        if found:
            obj_id = found["id"]
            print(f"object exists: {obj_id}")
        else:
            r = await client.post(
                f"{base}/metadata",
                json={"query": CREATE_OBJECT,
                      "variables": {"input": {"object": {
                          **OBJECT_IDENTITY,
                          "labelSingular": "Agency Listing",
                          "labelPlural": "Agency Listings",
                          "description": ("Facebook Marketplace listings synced "
                                        "from facebook-camofox-client"),
                      }}}},
                headers=headers)
            obj = r.json()["data"]["createOneObject"]
            obj_id = obj["id"]
            print(f"object created: {obj_id}")
        # 2. create missing fields only
        r = await client.post(
            f"{base}/metadata",
            json={"query": LIST_FIELDS, "variables": {"objectId": obj_id}},
            headers=headers)
        have = {f["name"] for f in (r.json().get("data") or {}).get("object", {}).get("fields", [])}
        for spec in FIELDS:
            if spec["name"] in have:
                print(f"field {spec['name']} exists - skipping")
                continue
            field = {"objectMetadataId": obj_id, "name": spec["name"],
                     "label": spec["label"], "type": spec["type"],
                     "description": "facebook-camofox-client sync"}
            if spec.get("options"):
                field["options"] = [
                    {"label": o.title(), "value": o, "color": "blue", "position": i}
                    for i, o in enumerate(spec["options"])]
            r = await client.post(
                f"{base}/metadata",
                json={"query": CREATE_FIELD,
                      "variables": {"input": {"field": field}}},
                headers=headers)
            body = r.text
            if '"errors"' not in body:
                print("OK  ", spec["name"])
            elif "already used" in body or "NOT_AVAILABLE" in body:
                print(f"exists - skipping  {spec['name']}")
            else:
                print("FAIL", spec["name"], r.status_code, body[:200].replace("\n", " "))
    return 0


def main() -> None:
    if "--print" in sys.argv or len(sys.argv) < 2:
        print(json.dumps(build_plan(), indent=1))
        return
    if "--apply" in sys.argv:
        sys.exit(asyncio.run(apply_plan()))


if __name__ == "__main__":
    main()
