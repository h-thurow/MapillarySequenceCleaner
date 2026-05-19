# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

This workspace is used to analyze and automate interactions with the **Mapillary API** — a Meta-owned street-level imagery platform. The primary use case documented here is bulk deletion of Mapillary photo sequences via the GraphQL API.

## Key Files

| File | Format | Purpose |
|------|--------|---------|
| `Mapillary_delete_sequence.json` | Paw/RapidAPI collection (v6) | HTTP request chain for deleting sequences |
| `Explore_the_Map.json` | HAR (JSON) | Captured network traffic from `mapillary.com/app` |
| `Explore_the_Map.har` / `Explore_the_Map_02.har` | HAR | Chrome DevTools captures of map browsing session |
| `www.mapillary.com.har` | HAR | Captured traffic from mapillary.com landing page |

## Mapillary API

**GraphQL endpoint**: `https://graph.mapillary.com/graphql/`

**Authentication** — two mechanisms used in parallel:
- Query param: `access_token=${token}`
- Header: `Authorization: ${authorization}` (Bearer token, used for mutations)

**Key variables** referenced in request templates: `user_id`, `token`, `authorization`, `doc_id`, `thumbs_after`, `image_id`, `sequence`

## Sequence Deletion Workflow

The `Mapillary_delete_sequence.json` collection documents a 4-step chain:

1. **`0 Metadata Thumb Images`** — GET paginated user feed via GraphQL (`doc_id` + `variables` with `user_id`, `first: 200`, `after: ${thumbs_after}`)
2. **`0.1 Metadata Thumb Images - next`** — GET next page using `end_cursor` from step 1's response (`data.fetch__User.feed.page_info.end_cursor`)
3. **`0.5 Thumb's sequence`** — GET `/${image_id}?fields=sequence&access_token=...` to resolve sequence key for a given image
4. **`1. requestImagesDeletion`** — POST GraphQL mutation `requestImagesDeletion($user_id, $sequence_key, $reason)` with `Content-Type: application/json`
5. **`2. getSequenceDeletionRequest`** — GET query `getSequenceDeletionRequest` using the `sequence_key` from step 4 to verify deletion status (`is_approved`, `is_completed`)

## Development

Python 3 is the scripting language for this workspace (`python3 *` is allowed). Use it to parse HAR files, automate API calls, or process Mapillary data.

HAR files can be parsed with Python's `json` module — note they may contain embedded control characters, so open with `errors='replace'` or use `ijson` for streaming large files.