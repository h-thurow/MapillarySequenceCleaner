#!/usr/bin/env python3
import argparse
import json
import pathlib
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

CONFIG_FILE = pathlib.Path(__file__).parent / "config.json"
SEQUENCE_CACHE_FILE = pathlib.Path(__file__).parent / "sequence_cache.json"


def load_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def load_cache():
    if SEQUENCE_CACHE_FILE.exists():
        return json.loads(SEQUENCE_CACHE_FILE.read_text())
    return {}


def save_cache(cache):
    SEQUENCE_CACHE_FILE.write_text(json.dumps(cache, indent=2))


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


def fetch_sequence(image_id, user_token):
    # user_token contains '|' which must not be percent-encoded for this endpoint
    url = f"https://graph.mapillary.com/{image_id}?fields=sequence&access_token={user_token}"
    try:
        with urllib.request.urlopen(url) as resp:
            return json.loads(resp.read()).get("sequence", "")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} for image_id {image_id}\nBody: {body}") from None


def main():
    config = load_config()

    parser = argparse.ArgumentParser(
        description="Fetch Mapillary thumb image metadata.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--doc_id", default=config.get("doc_id"), help="GraphQL doc_id for feed query")
    parser.add_argument("--user_id", default=config.get("user_id"), help="Mapillary user ID")
    parser.add_argument("--app_token", default=config.get("app_token"), help="Mapillary app client token (access_token)")
    parser.add_argument("--user_token", default=config.get("user_token"), help="Personal OAuth token for Image API")
    parser.add_argument("--after", default=None, help="Pagination cursor (end_cursor from previous response)")
    parser.add_argument("--captured_from", default=None, metavar="YYYY-MM-DD[THH:MM:SS]", help="Filter: captured_at >= this date (UTC)")
    parser.add_argument("--captured_to", default=None, metavar="YYYY-MM-DD[THH:MM:SS]", help="Filter: captured_at <= this date (UTC)")
    parser.add_argument("--sort-by", dest="sort_by", default="captured_at", choices=["captured_at", "created_at"], help="Sort output by field")
    args = parser.parse_args()

    for name in ("doc_id", "user_id", "app_token"):
        if not getattr(args, name):
            parser.error(f"--{name} is required (set in config.json or pass as argument)")
    if not args.user_token:
        parser.error("--user_token is required (set in config.json or pass as argument)")

    def parse_dt(s):
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        parser.error(f"Invalid date format: '{s}'. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS.")

    capture_start = parse_dt(args.captured_from) if args.captured_from else None
    capture_end = parse_dt(args.captured_to) if args.captured_to else None

    sort_key = args.sort_by + "_seconds"

    cursor = args.after
    total_fetched = 0
    all_filtered = []

    while True:
        data = fetch_thumb_images(args.doc_id, args.user_id, args.app_token, cursor)
        feed = data["data"]["fetch__User"]["feed"]
        nodes = feed["nodes"]
        page_info = feed["page_info"]
        total_fetched += len(nodes)

        for node in nodes:
            captured_at = datetime.fromtimestamp(node["captured_at_seconds"], tz=timezone.utc)
            if capture_start and captured_at < capture_start:
                continue
            if capture_end and captured_at > capture_end:
                continue
            all_filtered.append(node)

        if not page_info["has_next_page"]:
            break
        cursor = page_info["end_cursor"]

    all_filtered.sort(key=lambda n: n[sort_key], reverse=True)

    cache = load_cache()
    to_fetch = [n for n in all_filtered if n["image_id"] not in cache]
    cache_hits = len(all_filtered) - len(to_fetch)

    if to_fetch:
        with ThreadPoolExecutor(max_workers=1) as pool:
            futures = {pool.submit(fetch_sequence, node["image_id"], args.user_token): node["image_id"]
                       for node in to_fetch}
            for future in as_completed(futures):
                image_id = futures[future]
                cache[image_id] = future.result()
                save_cache(cache)

    sequences = cache

    col_w = (28, 20, 10, 36)
    sort_label = "captured_at (UTC)" if args.sort_by == "captured_at" else "created_at (UTC)"
    print(f"{sort_label:<{col_w[0]}} {'image_id':<{col_w[1]}} {'item_count':>{col_w[2]}} {'sequence':<{col_w[3]}}")
    print("-" * (sum(col_w) + 3))

    for node in all_filtered:
        dt = datetime.fromtimestamp(node[sort_key], tz=timezone.utc)
        print(
            f"{dt.strftime('%Y-%m-%d %H:%M:%S UTC'):<{col_w[0]}} "
            f"{node['image_id']:<{col_w[1]}} "
            f"{node['item_count']:>{col_w[2]}} "
            f"{sequences.get(node['image_id'], ''):<{col_w[3]}}"
        )

    print()
    print(f"Nodes fetched  : {total_fetched}")
    print(f"Sequences cache: {cache_hits} hits, {len(to_fetch)} fetched")
    if capture_start or capture_end:
        print(f"Nodes shown    : {len(all_filtered)}")


if __name__ == "__main__":
    main()
