"""
probe_paging.py
===============
Read-only: find the pagination parameter the DWF /offenses endpoint accepts.

Prints the raw response envelope (the keys beside `items`), then tries the
common query-parameter forms and reports how many items each returns. The
one that returns more than the default page is the one get_offenses() needs.

Run from the repo root:
    python3 probe_paging.py 501153
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scoreboard"))
from foys import FoysClient  # noqa: E402

CANDIDATES = [
    "",
    "?pageSize=100",
    "?page=1&pageSize=100",
    "?page=0&pageSize=100",
    "?pageIndex=0&pageSize=100",
    "?size=100",
    "?limit=100",
    "?take=100",
    "?skip=0&take=100",
    "?offset=0&limit=100",
    "?$top=100",
    "?top=100",
    "?count=100",
    "?perPage=100",
    "?per_page=100",
    "?maxResults=100",
    "?all=true",
]


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    match_id = int(sys.argv[1])

    client = FoysClient()
    print("authenticating...")
    client.authenticate()

    base = f"/matches/{match_id}/offenses"

    raw = client._get(base)
    print("\n--- response envelope (default request) ---")
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k == "items":
                print(f"  items: list of {len(v)}")
            else:
                print(f"  {k}: {v!r}")
    else:
        print(f"  plain list of {len(raw)} (no envelope)")

    print("\n--- trying parameter forms ---")
    for q in CANDIDATES:
        try:
            r = client._get(base + q)
            n = len(r["items"]) if isinstance(r, dict) and "items" in r else len(r)
            total = r.get("totalCount") if isinstance(r, dict) else "-"
            mark = "  <-- more than default" if n > 10 else ""
            print(f"  {q or '(none)':<28} items={n:<4} totalCount={total}{mark}")
        except Exception as e:
            print(f"  {q or '(none)':<28} ERROR {type(e).__name__}: {str(e)[:60]}")


if __name__ == "__main__":
    main()
