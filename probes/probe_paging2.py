"""
probe_paging2.py
================
Read-only. The page SIZE is fixed at 10 by the server. This probe tests
whether the page can be MOVED (offset/page/cursor forms, headers) or
REVERSED (sort direction). Success is a response whose first id differs
from the default page's first id, not a different count.

Run from the repo root:
    python3 probes/probe_paging2.py 501153
"""

import os
import sys
import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scoreboard"))
import foys  # noqa: E402
from foys import FoysClient  # noqa: E402

QUERY_FORMS = [
    "?page=2", "?pageNumber=2", "?pageIndex=1", "?pageNo=2", "?p=2",
    "?skip=10", "?offset=10", "?start=10", "?from=10", "?$skip=10",
    "?after=820102", "?afterId=820102", "?sinceId=820102", "?lastId=820102",
    "?fromId=820103", "?minId=820103", "?cursor=820102",
    "?sort=desc", "?order=desc", "?orderBy=desc", "?direction=desc",
    "?sortOrder=desc", "?desc=true", "?sort=-id", "?sort=id:desc",
    "?orderBy=id&direction=desc", "?orderBy=matchLogId%20desc",
    "?sortBy=matchLogId&sortDirection=desc",
]

HEADER_FORMS = [
    {"Range": "items=10-19"},
    {"Range": "items=0-99"},
    {"X-Page": "2"},
    {"X-Page-Number": "2"},
    {"X-Page-Size": "100"},
    {"X-Limit": "100"},
    {"X-Offset": "10"},
    {"X-Total-Count": "34"},
]


def ids_of(r):
    items = r["items"] if isinstance(r, dict) and "items" in r else r
    return [x.get("id") for x in items]


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    match_id = int(sys.argv[1])

    client = FoysClient()
    print("authenticating...")
    client.authenticate()
    base = f"/matches/{match_id}/offenses"

    default_ids = ids_of(client._get(base))
    print(f"\ndefault page: {len(default_ids)} items, first id {default_ids[0]}, last id {default_ids[-1]}")

    print("\n--- query forms (success = first id changes) ---")
    for q in QUERY_FORMS:
        try:
            ids = ids_of(client._get(base + q))
            moved = ids[:1] != default_ids[:1]
            mark = "  <-- DIFFERENT PAGE" if moved else ""
            print(f"  {q:<40} n={len(ids):<3} first={ids[0] if ids else None}{mark}")
        except Exception as e:
            print(f"  {q:<40} ERROR {type(e).__name__}: {str(e)[:50]}")

    print("\n--- header forms ---")
    for h in HEADER_FORMS:
        try:
            resp = requests.get(f"{foys.BASE_URL}{base}", headers={**client._headers(), **h})
            resp.raise_for_status()
            ids = ids_of(resp.json())
            moved = ids[:1] != default_ids[:1]
            extra = {k: v for k, v in resp.headers.items()
                     if any(t in k.lower() for t in ("page", "range", "total", "count", "link", "next"))}
            mark = "  <-- DIFFERENT PAGE" if moved else ""
            print(f"  {str(h):<40} n={len(ids):<3} first={ids[0] if ids else None}{mark}")
            if extra:
                print(f"      response headers of interest: {extra}")
        except Exception as e:
            print(f"  {str(h):<40} ERROR {type(e).__name__}: {str(e)[:50]}")

    print("\n--- all response headers on the default request ---")
    resp = requests.get(f"{foys.BASE_URL}{base}", headers=client._headers())
    for k, v in resp.headers.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
