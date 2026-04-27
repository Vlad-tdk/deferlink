# HTTP API reference

All routes are mounted under the FastAPI app in `app/main.py`. The `/api/v1/*` namespace is split across the routers in `app/api/`.

Conventions:

* JSON in / JSON out unless noted.
* `Content-Type: application/json` (forms aren't accepted on POST endpoints).
* Errors are FastAPI's standard `{"detail": "<message>"}` envelope with the matching HTTP status.
* Times are ISO 8601 in UTC.
* All routes are CORS-enabled per `CORS_ORIGINS`.

---

## Public-facing routes (in `app/main.py`)

### `GET /`

Service banner. Returns the app name, version, status string and a list of available endpoints. Useful for liveness probes that need a non-empty body.

### `GET /dl`

Browser-side click handler.

| Query param | Required | Description |
|---|---|---|
| `promo_id` | yes | Logical promo / campaign identifier echoed back in `/resolve`. |
| `domain`   | yes | Source domain — used for analytics and decoder lookup. |
| `timezone`, `language`, `screen_size`, `model` | no | Browser-side hints used by the fingerprint matcher. The escape-page JS pre-fills these from `navigator.*`. |

Behaviour:

1. Cloaking decision — bots/reviewers get `SEO_PAGE` or `COMPLIANT_PAGE`.
2. Real users get an HTML "escape" page (clipboard handoff + redirect to App Store) when the request is from an in-app browser, or a plain `302` to the App Store from real Safari.
3. A `Set-Cookie: dl_session_id=<session_id>; SameSite=…; Secure` is always issued so SFSafariViewController can later resolve via tier 2.

### `POST /resolve`

App first-launch resolve. Body and response shapes are documented in [`architecture.md`](architecture.md#request-flow--app-first-launch-resolve).

`success=true, matched=false` means the request was accepted but no session was found (organic install). Network/server problems return HTTP 5xx with a `detail` body.

### `GET /safari-resolve`

Used internally by the SDK's invisible SFSafariViewController. Reads the `dl_session_id` cookie that was set by `/dl` and `302`s back into the app via `<APP_URL_SCHEME>://resolved?session_id=<id>` (or `…?session_id=none`). The SDK's `handleOpenURL` parses this redirect and unblocks the resolve continuation.

---

## `/api/v1/*` — split per concern

### Health (`app/api/health.py`)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/health/quick` | Liveness — `{"status": "ok"}`. |
| `GET` | `/api/v1/health` | Default health — DB ping + version. |
| `GET` | `/api/v1/health/detailed` | Adds connection counts, queue lengths, last cleanup time. |

### Deep links (`app/api/deeplinks.py`)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/session` | Create a synthetic session for testing. Body: `{"promo_id":"…","domain":"…"}` → `{"session_id":"…","status":"created"}`. |
| `POST` | `/api/v1/resolve` | Same contract as the public `/resolve` (kept for symmetry / future versioning). |
| `GET`  | `/api/v1/instruction/{session_id}` | Static HTML page used as a redirect destination in some adapters; safe to ignore for normal SDK use. |

### Events (`app/api/events.py`)

| Method | Path | Body | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/events` | `EventRequest` (one event) | Insert one event. Returns `{status, event_id}`. |
| `POST` | `/api/v1/events/batch` | `BatchEventRequest` (`events: [...]`, max 100) | Bulk insert with per-event dedup. Returns `{success, inserted, duplicate, failed}`. |
| `GET`  | `/api/v1/events/stats` | — query: `start`, `end`, `promo_id` | Totals, top events, revenue by currency. |
| `POST` | `/api/v1/events/funnel` | `{steps:["af_install","af_complete_registration","af_purchase"]}` | Per-step user counts and conversion rates. |
| `GET`  | `/api/v1/events/cohort-revenue` | query: `promo_id`, `days=30` | Daily revenue per `promo_id` and currency. |

Standard event names and the `DLEventName.*` constants are documented in [`sdk-ios.md`](sdk-ios.md#event-tracking).

### Stats (`app/api/stats.py`)

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/v1/stats` | Aggregated session, install, attribution stats. |
| `GET`  | `/api/v1/stats/detailed` | Breakdown per `promo_id` and per match method. |
| `GET`  | `/api/v1/stats/analytics` | Roll-up combining session and event data. |
| `POST` | `/api/v1/cleanup` | Manual trigger of the same cleanup the background task does. |

### Cloaking admin (`app/api/cloaking_admin.py`)

CRUD for the cloaking rules consumed by `CloakingEngine`.

| Method | Path | Purpose |
|---|---|---|
| `GET` / `POST` / `PUT /{id}` / `DELETE /{id}` | `/api/v1/cloaking/ip-rules[/{id}]` | Custom IP/CIDR/ASN rules. |
| `GET` / `POST` / `PUT /{id}` / `DELETE /{id}` | `/api/v1/cloaking/ua-rules[/{id}]`  | Custom UA regex rules. |
| `POST` | `/api/v1/cloaking/test` | Body `{ip, user_agent, headers?, cookies?}` → live `CloakingDecision` for debugging. |
| `GET`  | `/api/v1/cloaking/log` | Recent decisions (with signals) — paginated. |
| `GET`  | `/api/v1/cloaking/stats` | Counts per `visitor_type` over a window. |

Field shapes match `IPRule` / `UARuleRecord` in `app/core/cloaking/models.py`.

### Facebook CAPI admin (`app/api/capi_admin.py`)

| Method | Path | Purpose |
|---|---|---|
| `GET` / `POST` / `PUT /{id}` / `DELETE /{id}` | `/api/v1/capi/configs[/{id}]` | Per-app pixel/access-token config. Unique on `(app_id, platform)`. |
| `POST` | `/api/v1/capi/test` | Send one synthetic event to verify credentials. |
| `GET`  | `/api/v1/capi/log` | Delivery log with status, last error, retry schedule. |
| `POST` | `/api/v1/capi/retry/{row_id}` | Force-retry a parked row immediately. |

### SKAdNetwork (`app/api/skadnetwork.py`)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/skadnetwork/postback` | Apple's postback endpoint. Verifies signature, persists, decodes, forwards to CAPI. |
| `GET`  | `/api/v1/skan/config?app_id=…` | CV config (revenue buckets, engagement thresholds, conversion window) for the SDK. |
| `GET` / `POST` / `PUT /{id}` / `DELETE /{id}` | `/api/v1/skadnetwork/decoders[/{id}]` | Per-campaign decoder rules. |
| `GET`  | `/api/v1/skadnetwork/postbacks` | Recent postbacks (filterable by app/campaign). |
| `GET`  | `/api/v1/skadnetwork/stats` | CV distribution, postback counts per `(app_id, source_identifier, day)`. |

Bit layout and rule semantics are in [`skadnetwork.md`](skadnetwork.md).

---

## Errors you can expect

| Status | When |
|---|---|
| `400`  | Malformed JSON, missing required field. |
| `404`  | Unknown route or unknown row id on PUT/DELETE. |
| `409`  | Uniqueness violation (e.g. duplicate `(app_id, platform)` CAPI config). |
| `422`  | Pydantic validation error. |
| `500`  | Unexpected exception — body is `{"detail": "..."}` and a stack trace is logged. |

The handler intentionally never returns 500 for "no attribution" — see [`/resolve`](#post-resolve) above.
