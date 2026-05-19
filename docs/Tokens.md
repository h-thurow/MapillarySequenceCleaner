# Authentication

Siehe auch [Token-Definition entsprechend Mapillary](https://www.mapillary.com/developer/api-documentation/#glossary).

## Drei Token-Typen im Überblick

| Config-Key | Token | Mapillary-Bezeichnung | Vertraulichkeit | Verwendung |
|---|---|---|---|---|
| `app_token` | `MLY\|4223665974375089\|...` | Client Token (Mapillary-App) | halböffentlich | GraphQL Feed-Endpoint + Delete-Mutation |
| `user_token` | `MLY\|27053225000963327\|...` | User Access Token (eigene App) | privat | Image REST API (fetch_sequence) |
| _(noch nicht implementiert)_ | Web-Session-Token nach Login | Authorization Bearer | privat (kurzlebig) | Delete-Mutation (als Header) |

### 1. Mapillary App-Client-Token (`app_token`)

```
MLY|4223665974375089|d62822dd792b6a823d0794ef26450398
```

- Hardcodiert im Mapillary JavaScript-Bundle (`main.*.js`) — **kein persönlicher User-Token**
- Für alle Besucher von `www.mapillary.com` identisch, auch ohne Login
- Überlebt Browser-Logout und Storage-Clears vollständig
- Wird für den internen GraphQL-Feed-Endpoint verwendet (Thumbnail-Feed, Karten-Queries)
- Format: `MLY|{app_id}|{client_secret}`

**Übergabe**: Als Query-Parameter `access_token=MLY|...` — das `|`-Zeichen darf **nicht** URL-kodiert werden (`%7C`). Der REST-Endpoint `graph.mapillary.com/{image_id}` lehnt percent-kodierte Tokens mit OAuthException 368 ab. Der GraphQL-Endpoint `/graphql/` akzeptiert beide Varianten.

### 2. Eigener User Access Token (`user_token`)

```
MLY|27053225000963327|53bb846b894c4b744aacc16ba9c5bf37
```

- Ausgestellt über `mapillary.com/dashboard/developers` nach Registrierung einer eigenen App
- Erstellt mit Scopes **read, write, upload** über `mapillary.com/dashboard/developers`
- Mapillary-Terminologie: **User Access Token**
- **Privat** (wie ein Passwort): Ermöglicht API-Calls im Namen des Nutzers
- Eigenes Rate-Limit-Kontingent (60.000 Req/min), **unabhängig** vom geteilten Mapillary-Kontingent
- Verwendet für: Image REST API (`fetch_sequence`)
- Löst das Rate-Limit-Problem des geteilten `app_token` — verifiziert: Abfrage aller Sequences ohne OAuthException

**Übergabe**: Als Query-Parameter `access_token=MLY|...` (Token-Literal, kein URL-Encoding des `|`)

### 3. Web-Session-Authorization-Token

- Kurzlebiger Bearer-Token des eingeloggten Nutzers aus der Mapillary-Web-App
- Nicht dauerhaft gespeichert — nur nach Login in Browser-Session verfügbar
- Wird für die Delete-Mutation benötigt: `Authorization: Bearer {token}` Header
- Kombiniert mit `app_token` für den internen GraphQL-Endpoint (wie alle internen Web-App-Calls)
- **Noch nicht im Script implementiert** — wird für Schritt 1 des Delete-Workflows benötigt

**Verwendung im Delete-Workflow:**
- Schritte 0–0.5 (lesend): `app_token` als `access_token` für Feed-Endpoint; `user_token` für Image REST API
- Schritte 1–2 (Mutation/Deletion): `app_token` als `access_token` + Web-Session-Token als `Authorization`-Header

## Rate Limiting

### Interne Feed-API (`doc_id`-basiert)

- Endpunkt: `https://graph.mapillary.com/graphql/`
- **Geteiltes Kontingent** über alle Mapillary-Web-App-Nutzer — derselbe App-Client-Token
- Limits sind **nicht dokumentiert**; Überschreitung liefert `{"errors":[{"message":"Rate limit exceeded","code":1675004}]}`
- Wiederherstellungszeit nach Überschreitung: unbekannt, empirisch mehrere Stunden
- **Konsequenz**: Aggressives Scripting legt die Mapillary-Web-App für alle Nutzer lahm — Pausen zwischen Requests sind zwingend erforderlich

### Offizielle Entity-API (`/{image_id}`)

- Endpunkt: `https://graph.mapillary.com/{image_id}?fields=...`
- Dokumentiertes Limit: 60.000 Requests/Minute pro App
- Fehler bei Überschreitung: OAuthException 368 ("Bitte melde dich an")
- Limit ist token-gebunden — eigenes `user_token` hat separates Kontingent, unabhängig vom geteilten `app_token`
- **Lösung**: `user_token` (Developer-Token) statt `app_token` für Image REST API verwenden — verifiziert funktionsfähig

## Quellen

- HAR-Captures: `no_login.har`, `Explore_the_Map.har`
- Mapillary API-Dokumentation: https://www.mapillary.com/developer/api-documentation#rate-limits
- Mapillary Forum: https://forum.mapillary.com/t/mapillary-v4-api-map-feature-search-oauthexception/5793
