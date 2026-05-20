# Authentication

See also [Token definitions according to Mapillary](https://www.mapillary.com/developer/api-documentation/#glossary).

## Three token types at a glance

| Config key | Token | Mapillary name                   | Confidentiality | Usage |
|---|---|----------------------------------|---|---|
| `app_token` | `MLY\|4223665974375089\|...` | Client Token (Mapillary app)     | semi-public | GraphQL feed endpoint + delete mutation |
| `user_token` | `MLY\|27053225000963327\|...` | Client Access Token (own app)    | private | Image REST API |
| `auth_header` | `OAuth MLY\|...` | Web session Authorization Bearer | private | Delete mutation (as header) |

### Mapillary app client token (`app_token`)

```
MLY|4223665974375089|d62822dd792b6a823d0794ef26450398
```

- Hardcoded in the Mapillary JavaScript bundle (`main.*.js`) — **not a personal user token**
- Identical for all visitors of `www.mapillary.com`, even without login
- Survives browser logout and storage clears completely
- Used for the internal GraphQL feed endpoint (thumbnail feed, map queries)
- Format: `MLY|{app_id}|{client_secret}`

**Passing it**: As query parameter `access_token=MLY|...` — the `|` character must **not** be URL-encoded (`%7C`). The REST endpoint `graph.mapillary.com/{image_id}` rejects percent-encoded tokens with OAuthException 368. The GraphQL endpoint `/graphql/` accepts both variants.


### Mapillary client access token (`user_token`)

```
MLY|...|...
```

- Issued via `mapillary.com/dashboard/developers` after registering your own app
- Created with scopes **read, write, upload**
- Own rate-limit quota (60,000 req/min), **independent** of the shared Mapillary quota
- Used for: Image REST API

**Passing it**: As query parameter `access_token=MLY|...` (token literal, no URL-encoding of `|`)

See also [Client access token, User access token](https://www.mapillary.com/developer/api-documentation/#glossary).

### Web session authorization token (`auth_header`)

- Bearer token of the logged-in user from the Mapillary web app
- Only available in the browser session after login
- Required for the delete mutation: `Authorization: OAuth {token}` header

**How to obtain**: Open [mapillary.com](https://www.mapillary.com), log in, open DevTools → Network tab, filter for `fetch__user`, copy the `Authorization` request header value (e.g. `OAuth MLY|...`).

**Usage in the delete workflow:**
- `app_token` as `access_token` + web session token as `Authorization` header

## Rate limiting

### Internal GraphQL API (`/graphql/`)

- Endpoint: `https://graph.mapillary.com/graphql/`
- Used for both the internal feed (doc_id-based) and the delete mutation (`requestImagesDeletion`)
- Apparently a **shared quota** across all Mapillary web app users — same app client token
- Limits are **not documented**; exceeding them returns `{"errors":[{"message":"Rate limit exceeded","code":1675004}]}`
- Recovery time after exceeding: unknown, empirically several hours (~5)

### Official entity API (`/{image_id}`)

- Endpoint: `https://graph.mapillary.com/{image_id}?fields=...`
- Documented limit: 60,000 requests/minute per app
- Error on exceeding: OAuthException 368 ("Please log in")
- Limit is token-bound — own `user_token` has a separate quota, independent of the shared `app_token`

## Sources

- Mapillary API documentation: https://www.mapillary.com/developer/api-documentation#rate-limits
- Mapillary Forum: https://forum.mapillary.com/t/mapillary-v4-api-map-feature-search-oauthexception/5793