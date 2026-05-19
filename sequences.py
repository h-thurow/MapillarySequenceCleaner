#!/usr/bin/env python3
"""Manage Mapillary sequences via the official Image API."""
import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from mapillary_utils import load_config, elapsed, setup_logging

log = setup_logging()

BASE_URL = "https://graph.mapillary.com"

# TODO Mapillary Anzeigeformat des Thumb timestamp (Dec 2, 2024 2:58 PM) als Zeitangabe akzeptieren.

def api_get(url, retries=3, backoff=5):
    url = url.replace("%7C", "|")
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code >= 500 and attempt < retries - 1:
                wait = backoff * (attempt + 1)
                msg = f"HTTP {e.code} — retrying in {wait}s (attempt {attempt + 1}/{retries})"
                print(f"\n{msg}", flush=True)
                log.warning(msg)
                time.sleep(wait)
            else:
                body = e.read().decode(errors="replace")
                log.error("HTTP %d: %s", e.code, body[:200])
                raise RuntimeError(f"HTTP {e.code}: {body}") from None


def build_url(path, user_token, **params):
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    return f"{BASE_URL}/{path}?{qs}&access_token={user_token}"


def parse_api_dt(s):
    if not s:
        return None
    if isinstance(s, (int, float)):
        return datetime.fromtimestamp(s / 1000, tz=timezone.utc)
    try:
        return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def fmt_dt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC") if dt else ""


def parse_user_dt(s, parser):
    # ISO-like formats → interpret as UTC
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # Any other format (e.g. "May 1, 2026 1:32 PM" from Mapillary browser) → local time → UTC
    try:
        from dateutil import parser as du_parser
        from tzlocal import get_localzone
        dt = du_parser.parse(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=get_localzone())
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    parser.error(f"Invalid date format: '{s}'. Use YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS, or locale format like 'May 1, 2026 1:32 PM'.")


def fetch_sequence_bounds(seq_id, user_token, known_count, known_first_dt, known_last_dt):
    """Return (seq_id, count, first_dt, last_dt) using true sequence extent.

    If true count matches known_count, the sequence is fully within the filter
    window — known_first_dt/known_last_dt are already accurate, no extra calls needed.
    """
    data = api_get(build_url("image_ids", user_token, sequence_id=seq_id))
    ids = [item["id"] for item in data.get("data", [])]
    if not ids:
        return seq_id, 0, None, None
    true_count = len(ids)
    if true_count == known_count:
        return seq_id, true_count, known_first_dt, known_last_dt
    first_data = api_get(build_url(ids[0], user_token, fields="captured_at"))
    first_dt = parse_api_dt(first_data.get("captured_at", ""))
    if len(ids) == 1:
        return seq_id, true_count, first_dt, first_dt
    last_data = api_get(build_url(ids[-1], user_token, fields="captured_at"))
    last_dt = parse_api_dt(last_data.get("captured_at", ""))
    return seq_id, true_count, first_dt, last_dt


def collect_sequences(args, parser):
    """Phase 1 + Phase 2: return (rows, total_images, captured_from, captured_to).

    rows = list of (sid, count, first_dt, last_dt), sorted newest-first.
    """
    if args.captured_at:
        if args.captured_from or args.captured_to:
            parser.error("--captured_at cannot be combined with --captured_from or --captured_to")
        from datetime import timedelta
        captured_from = parse_user_dt(args.captured_at, parser)
        captured_to = captured_from + timedelta(minutes=1)
    else:
        if bool(args.captured_from) != bool(args.captured_to):
            parser.error("--captured_from and --captured_to must be used together")
        captured_from = parse_user_dt(args.captured_from, parser) if args.captured_from else None
        captured_to = parse_user_dt(args.captured_to, parser) if args.captured_to else None

    # Phase 1: collect unique sequence IDs from Image API
    img_params = dict(
        creator_username=args.creator_username,
        fields="id,sequence,captured_at",
        limit=args.limit,
    )
    if captured_from:
        img_params["start_captured_at"] = captured_from.strftime("%Y-%m-%dT%H:%M:%SZ")
    if captured_to:
        img_params["end_captured_at"] = captured_to.strftime("%Y-%m-%dT%H:%M:%SZ")

    url = build_url("images", args.user_token, **img_params)
    seq_seen = {}  # seq_id -> {"count": int, "first_dt": datetime, "last_dt": datetime}
    total_images = 0
    page = 0
    t0 = time.monotonic()

    while url:
        page += 1
        print(f"Fetching images: page {page}, {total_images} images... {elapsed(t0)}", end="\r", flush=True)
        data = api_get(url)
        if "error" in data:
            print()
            raise SystemExit(f"API error: {json.dumps(data['error'], indent=2)}")
        for image in data.get("data", []):
            total_images += 1
            sid = image.get("sequence")
            if not sid:
                continue
            dt = parse_api_dt(image.get("captured_at", ""))
            if sid not in seq_seen:
                seq_seen[sid] = {"count": 0, "first_dt": dt, "last_dt": dt}
            entry = seq_seen[sid]
            entry["count"] += 1
            if dt and (entry["first_dt"] is None or dt < entry["first_dt"]):
                entry["first_dt"] = dt
            if dt and (entry["last_dt"] is None or dt > entry["last_dt"]):
                entry["last_dt"] = dt
        url = data.get("paging", {}).get("next")

    print(f"Fetching images: page {page}, {total_images} images... done {elapsed(t0)}", flush=True)
    log.info("Phase 1 done: %d images, %d sequences (%s)", total_images, len(seq_seen), elapsed(t0))

    # Phase 2: fetch true sequence extent (count + first/last captured_at)
    # Skipped when no time window is set — Phase 1 has seen all images in that case.
    seq_meta = {}
    total_seqs = len(seq_seen)

    if captured_from or captured_to:
        done = 0
        t1 = time.monotonic()
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(fetch_sequence_bounds, sid, args.user_token,
                            entry["count"], entry["first_dt"], entry["last_dt"]): sid
                for sid, entry in seq_seen.items()
            }
            for future in as_completed(futures):
                sid, count, first_dt, last_dt = future.result()
                seq_meta[sid] = (count, first_dt, last_dt)
                done += 1
                # \n on last line so the table header doesn't overwrite the progress line
                print(f"Fetching sequence metadata: {done}/{total_seqs} {elapsed(t1)}",
                      end="\r" if done < total_seqs else "\n", flush=True)
    else:
        for sid, entry in seq_seen.items():
            seq_meta[sid] = (entry["count"], entry["first_dt"], entry["last_dt"])

    rows = [(sid, count, first_dt, last_dt) for sid, (count, first_dt, last_dt) in seq_meta.items()]
    rows.sort(key=lambda r: r[2] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return rows, total_images, captured_from, captured_to


def print_table(rows):
    sep = "   "
    col_w = (22, 8, 26, 26)
    print(f"\n{'sequence':<{col_w[0]}}{sep}{'images':>{col_w[1]}}{sep}{'first captured (UTC)':<{col_w[2]}}{sep}{'last captured (UTC)':<{col_w[3]}}")
    print("-" * (sum(col_w) + len(sep) * 3))

    for sid, count, first_dt, last_dt in rows:
        print(
            f"{sid:<{col_w[0]}}{sep}"
            f"{count:>{col_w[1]}}{sep}"
            f"{fmt_dt(first_dt):<{col_w[2]}}{sep}"
            f"{fmt_dt(last_dt):<{col_w[3]}}"
        )

    print()
    print(f"Sequences found: {len(rows)}")


def cmd_list(args, parser):
    log.info("sequences list: user=%s from=%s to=%s",
             args.creator_username, args.captured_from or "*", args.captured_to or "*")

    rows, total_images, captured_from, captured_to = collect_sequences(args, parser)
    print_table(rows)
    log.info("sequences list done: %d sequences, %d images fetched", len(rows), total_images)


def request_deletion(seq_id, user_id, authorization):
    """POST requestImagesDeletion mutation. Returns parsed response body."""
    mutation = (
        "mutation requestImagesDeletion($user_id: ID!, $sequence_key: String!, $reason: String)"
        " {request_images_deletion(user_id: $user_id sequence_key: $sequence_key reason: $reason)"
        " {id sequence_key reason __typename}}"
    )
    body = json.dumps({
        "operationName": "requestImagesDeletion",
        "variables": {"user_id": user_id, "sequence_key": seq_id, "reason": None},
        "query": mutation,
    }).encode()
    doc_param = urllib.parse.quote(mutation, safe="")
    url = f"{BASE_URL}/graphql/?doc={doc_param}"
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": authorization},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def cmd_delete(args, parser):
    log.info("sequences delete: user=%s from=%s to=%s dry_run=%s",
             args.creator_username, args.captured_from or "*", args.captured_to or "*", args.dry_run)

    rows, total_images, captured_from, captured_to = collect_sequences(args, parser)

    if args.captured_at:
        # Identification mode: all sequences with images in the 1-minute window are candidates.
        to_delete = rows
        outside = [(sid, count, first_dt, last_dt) for sid, count, first_dt, last_dt in rows
                   if captured_from and first_dt and first_dt < captured_from]
    else:
        # Range mode: skip sequences that started before the window.
        to_delete = [r for r in rows if not (captured_from and r[2] and r[2] < captured_from)]
        outside = [r for r in rows if captured_from and r[2] and r[2] < captured_from]

    print_table(rows)

    def print_outside_notes(dry_run=False):
        for sid, count, first_dt, last_dt in outside:
            print(f"Note: sequence {sid} ({count} images) starts at {fmt_dt(first_dt)}, "
                  f"outside the specified window ({fmt_dt(captured_from)} – {fmt_dt(captured_to)}).")
            if dry_run:
                print(f"      Without --dry-run you will be asked to confirm deletion of this sequence individually.")

    if not to_delete:
        print("\nNothing to delete.")
        return

    if args.dry_run:
        print(f"\nDRY RUN — would delete {len(to_delete)} sequence(s).")
        if outside:
            print()
            print_outside_notes(dry_run=True)
        log.info("dry run: would delete %d sequences", len(to_delete))
        return

    deleted = 0
    failed = []
    t2 = time.monotonic()

    if outside:
        print()
        print_outside_notes()

    if not args.force:
        if to_delete:
            if len(to_delete) == 1:
                sid, count, first_dt, last_dt = to_delete[0]
                prompt = f"\nDelete {sid}  ({count} images,  {fmt_dt(first_dt)})? Type 'yes' to confirm: "
            else:
                prompt = f"\nDelete {len(to_delete)} sequence(s) within the time window? Type 'yes' to confirm: "
            if input(prompt).strip().lower() != "yes":
                raise SystemExit("Aborted.")
        for sid, count, first_dt, last_dt in outside:
            answer = input(f"Also delete {sid}  ({count} images,  {fmt_dt(first_dt)})? [y/N] ")
            if answer.strip().lower() != "y":
                print("  Skipped.")
            else:
                to_delete.append((sid, count, first_dt, last_dt))

    for i, (sid, count, first_dt, last_dt) in enumerate(to_delete, 1):
        print(f"Deleting {i}/{len(to_delete)}: {sid}... {elapsed(t2)}", end="\r", flush=True)
        try:
            request_deletion(sid, args.user_id, args.auth_header)
            deleted += 1
            log.info("deleted: %s (images: %d, first: %s)", sid, count, fmt_dt(first_dt))
        except Exception as e:
            failed.append((sid, str(e)))
            log.error("delete failed: %s — %s", sid, e)
        if args.delay > 0 and i < len(to_delete):
            time.sleep(args.delay)

    print(f"\nDeleted {deleted}/{len(to_delete)} sequences. {elapsed(t2)}")
    if failed:
        print(f"\nFailed ({len(failed)}):")
        for sid, err in failed:
            print(f"  {sid}: {err}")
    log.info("sequences delete done: %d deleted, %d failed", deleted, len(failed))


def main():
    config = load_config()

    parser = argparse.ArgumentParser(
        description="Manage Mapillary sequences via the Image API.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(p):
        p.add_argument("--creator_username", default=config.get("creator_username"), help="Mapillary username")
        p.add_argument("--user_token", default=config.get("user_token"), help="Personal OAuth token for Image API")
        p.add_argument("--captured_at", default=None, metavar="DATETIME",
                       help="Target a single sequence by its start timestamp (sets a 1-minute window); alternative to --captured_from/--captured_to")
        p.add_argument("--captured_from", default=None, metavar="DATETIME", help="Filter: captured_at >= this datetime")
        p.add_argument("--captured_to", default=None, metavar="DATETIME", help="Filter: captured_at <= this datetime")
        p.add_argument("--limit", type=int, default=config.get("limit", 2000), help="Page size for image query (max 2000)")

    p_list = subparsers.add_parser(
        "list",
        help="List sequences with true first/last captured and range status",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    add_common(p_list)

    p_delete = subparsers.add_parser(
        "delete",
        help="Delete sequences (only 'complete' ones within the time window)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    add_common(p_delete)
    p_delete.add_argument("--user_id", default=config.get("user_id"), help="Mapillary numeric user ID")
    p_delete.add_argument("--auth_header", default=config.get("auth_header"),
                          metavar="BEARER_TOKEN",
                          help="Value of the Authorization header (short-lived, copy from browser DevTools)")
    p_delete.add_argument("--force", "-f", action="store_true", help="Skip confirmation prompt")
    p_delete.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")

    args = parser.parse_args()

    for name in ("creator_username", "user_token"):
        if not getattr(args, name):
            parser.error(f"--{name} is required (set in config.json or pass as argument)")

    if args.command == "delete":
        if not args.user_id:
            parser.error("--user_id is required for delete (set in config.json or pass as argument)")
        if not args.dry_run and not args.auth_header:
            parser.error("--auth_header is required for delete (copy Authorization header value from browser DevTools)")

    if args.command == "list":
        cmd_list(args, parser)
    elif args.command == "delete":
        cmd_delete(args, parser)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
        raise SystemExit(1)