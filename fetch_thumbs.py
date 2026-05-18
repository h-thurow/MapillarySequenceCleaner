#!/usr/bin/env python3
import argparse
import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone


def fetch_thumb_images(doc_id, user_id, token, after=None):
    variables = {"id": user_id, "first": 200, "after": after, "hide_after": 14}
    params = {
        "doc_id": doc_id,
        "variables": json.dumps(variables, separators=(",", ":")),
        "access_token": token,
    }
    url = "https://graph.mapillary.com/graphql/?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read())


def fetch_sequence(image_id, token):
    params = {"fields": "sequence", "access_token": token}
    url = f"https://graph.mapillary.com/{image_id}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url) as resp:
            return json.loads(resp.read()).get("sequence", "")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} for image_id {image_id}\nURL: {url}\nBody: {body}") from None


def main():
    parser = argparse.ArgumentParser(description="Fetch Mapillary thumb image metadata.")
    parser.add_argument("--doc_id", required=True)
    parser.add_argument("--user_id", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--after", default=None, help="Pagination cursor (end_cursor from previous response)")
    parser.add_argument("--captured_from", default=None, metavar="YYYY-MM-DD[THH:MM:SS]", help="Filter: captured_at >= this date (UTC)")
    parser.add_argument("--captured_to", default=None, metavar="YYYY-MM-DD[THH:MM:SS]", help="Filter: captured_at <= this date (UTC)")
    args = parser.parse_args()

    def parse_dt(s):
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        parser.error(f"Invalid date format: '{s}'. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS.")

    capture_start = parse_dt(args.captured_from) if args.captured_from else None
    capture_end = parse_dt(args.captured_to) if args.captured_to else None

    col_w = (28, 20, 10, 36)
    print(f"{'captured_at (UTC)':<{col_w[0]}} {'image_id':<{col_w[1]}} {'item_count':>{col_w[2]}} {'sequence':<{col_w[3]}}")
    print("-" * (sum(col_w) + 3))

    cursor = args.after
    total_fetched = 0
    total_shown = 0

    while True:
        data = fetch_thumb_images(args.doc_id, args.user_id, args.token, cursor)
        feed = data["data"]["fetch__User"]["feed"]
        nodes = feed["nodes"]
        page_info = feed["page_info"]
        total_fetched += len(nodes)

        filtered = []
        for node in nodes:
            captured_at = datetime.fromtimestamp(node["captured_at_seconds"], tz=timezone.utc)
            if capture_start and captured_at < capture_start:
                continue
            if capture_end and captured_at > capture_end:
                continue
            filtered.append((node, captured_at))

        sequences = {}
        with ThreadPoolExecutor(max_workers=1) as pool:
            futures = {pool.submit(fetch_sequence, node["image_id"], args.token): node["image_id"]
                       for node, _ in filtered}
            for future in as_completed(futures):
                sequences[futures[future]] = future.result()

        for node, captured_at in filtered:
            print(
                f"{captured_at.strftime('%Y-%m-%d %H:%M:%S UTC'):<{col_w[0]}} "
                f"{node['image_id']:<{col_w[1]}} "
                f"{node['item_count']:>{col_w[2]}} "
                f"{sequences.get(node['image_id'], ''):<{col_w[3]}}"
            )
            total_shown += 1

        if not page_info["has_next_page"]:
            break
        cursor = page_info["end_cursor"]

    print()
    print(f"Nodes fetched : {total_fetched}")
    if capture_start or capture_end:
        print(f"Nodes shown   : {total_shown}")


if __name__ == "__main__":
    main()