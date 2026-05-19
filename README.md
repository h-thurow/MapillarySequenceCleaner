# Mapillary Sequence Tools

Python scripts to list and bulk-delete your Mapillary sequences.

## Scripts

| Script | Purpose |
|--------|---------|
| `sequences.py` | List and delete sequences via the Mapillary Image API |
| `mapillary_utils.py` | Shared utilities (config, cache, logging) |

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install python-dateutil tzlocal
```

Create `config.json` in the project root (excluded from git):

```json
{
  "creator_username": "your_username",
  "user_id": "your_numeric_user_id",
  "user_token": "MLY|..."
}
```

See `docs/Tokens.md` for how to obtain each token.

## sequences.py

### List sequences

```bash
python3 sequences.py list
python3 sequences.py list --captured_from "2024-12-01" --captured_to "2024-12-31"
python3 sequences.py list --captured_at "Dec 2, 2024 2:58 PM"
```

Output:

```
sequence                   images   first captured (UTC)         last captured (UTC)
-------------------------------------------------------------------------------------------
PA3dpCEZ2gzySibQo6jXnT         44   2024-12-02 13:03:00 UTC      2024-12-02 13:09:29 UTC
...

Sequences found: 34
```

### Delete sequences

```bash
# Dry run first — always recommended
python3 sequences.py delete --dry-run --captured_from "2024-12-01" --captured_to "2024-12-02"

# Delete with confirmation prompt
python3 sequences.py delete --captured_from "2024-12-01" --captured_to "2024-12-02" --auth_header "OAuth MLY|..."

# Target a single sequence by its browser timestamp
python3 sequences.py delete --captured_at "Dec 2, 2024 2:58 PM" --auth_header "OAuth MLY|..."

# Skip confirmation (for scripting)
python3 sequences.py delete --captured_from "2024-12-01" --captured_to "2024-12-02" --force --auth_header "OAuth MLY|..."
```

### Date formats

All date arguments accept:
- ISO format (interpreted as UTC): `2024-12-02`, `2024-12-02T13:58:00`, `2024-12-02 13:58:00`
- Browser display format (interpreted as local time with DST): `Dec 2, 2024 2:58 PM`

### Time window options

| Option | Behaviour |
|--------|-----------|
| `--captured_at DATETIME` | Sets a 1-minute window around the given timestamp. Use when targeting a single sequence by copying its timestamp from the Mapillary browser. |
| `--captured_from` + `--captured_to` | Explicit window. Both must be provided together. Sequences that started before `captured_from` are flagged and require individual confirmation. |
| _(none)_ | All sequences. |

### --auth_header

The `Authorization` header value required for deletion. It is short-lived and must be copied fresh from your browser each time:

1. Open [mapillary.com](https://www.mapillary.com) and log in
2. Open DevTools → Network tab
3. Click any request to `graph.mapillary.com`
4. Copy the `Authorization` request header value (e.g. `OAuth MLY|...`)

### Deletion behaviour

- Sequences with images in the time window are listed and confirmed before deletion.
- Sequences whose first image falls **outside** the window (boundary sequences caused by the browser's minute-precision display) are shown with a note and require explicit individual confirmation.
- `--dry-run` shows what would be deleted without making any changes.
- `--force` skips all confirmation prompts.

## Logging

All runs are logged to `mapillary.log` (excluded from git), including timings, retry events, and deletion records.