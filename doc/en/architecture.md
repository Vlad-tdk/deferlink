# Architecture

This document describes the system as a whole. Per-subsystem deep-dives are linked at the end.

## High-level shape

DeferLink is a Python (FastAPI + SQLite) backend plus a Swift iOS SDK. The backend exposes one public-facing entry point (`/dl`) for ad clicks and one for app first-launch resolution (`/resolve`). All other endpoints live under `/api/v1/` and are split between SDK callbacks (`events`, `skadnetwork/postback`, `skan/config`) and an admin surface (cloaking rules, CAPI configs, decoder rules, stats, health).

```
                        ┌───────────────┐
              ┌────────►│   /api/v1/*   │── admin / SDK
              │         │ (FastAPI)     │
   public ────┤         └───────────────┘
   internet   │
              │         ┌───────────────┐         ┌──────────────┐
              ├────────►│  /dl  /escape │────────►│  cloaking    │
              │         │  /resolve     │         │  engine      │
              │         │  /safari-     │         └──────────────┘
              │         │   resolve     │                │
              │         └───────────────┘         ┌──────────────┐
              │                  │                │ DeepLink     │
              │                  └───────────────►│ Handler      │
              │                                   └──────┬───────┘
              │                                          │
              │                                   ┌──────▼───────┐
              │                                   │   SQLite     │
              │                                   │   (single    │
              │                                   │   process)   │
              │                                   └──────────────┘
              │
              │         ┌───────────────┐         ┌──────────────┐
              └────────►│  Apple SKAN   │────────►│ SKAN service │
                        │   postback    │         │  + decoder   │
                        └───────────────┘         └──────┬───────┘
                                                         │
                                                  ┌──────▼───────┐
                                                  │ CAPI service │──► graph.facebook.com
                                                  │  + retry     │
                                                  │  worker      │
                                                  └──────────────┘
```

## Lifecycle and processes

The HTTP server runs in `uvicorn` (`run.py`). At startup `app.main` opens a FastAPI application with a `lifespan` handler that:

1. Calls `Config.validate_config()` — fails fast on weak `SECRET_KEY` etc. in production.
2. Initialises the SQLite schema and runs all migrations from `app/migrations/`.
3. Loads cloaking IP/UA rules and SKAN decoders from the DB into in-memory caches (`CloakingEngine`, `SKANService`, `CAPIService`).
4. Constructs the `DeepLinkHandler` singleton and wires it into `app/api/deeplinks.py`.
5. Spawns three background asyncio tasks that live for the whole server lifetime:
   * **Cleanup** — drops expired browser sessions (`DEFAULT_TTL_HOURS`, default 48 h) every `CLEANUP_INTERVAL_MINUTES`.
   * **Algorithm optimisation** — opt-in (`AUTO_OPTIMIZE_WEIGHTS=true`) periodic recompute of `IntelligentMatcher.weights`.
   * **CAPI retry worker** — every `CAPI_RETRY_INTERVAL_SECONDS` it scans `capi_delivery_log` for rows with `next_retry_at <= now` and replays the request (see `app/core/capi/retry_worker.py`).

On shutdown the lifespan stops these tasks gracefully and closes the `httpx.AsyncClient` used for outbound CAPI calls.

## Request flow — ad click

1. Ad network redirects the device browser (or in-app browser) to `GET /dl?promo_id=…&domain=…`.
2. `app/main.py` extracts the client IP (with `TRUST_PROXY_HEADERS` honouring `X-Forwarded-For`) and the User-Agent.
3. `CloakingEngine.decide(...)` aggregates IP, UA and behavioural signals into a `CloakingDecision`. See [`cloaking.md`](cloaking.md) for the math.
4. If the visitor is `BOT` or `AD_REVIEW`, the response is the configured cloaking action (`SEO_PAGE`, `COMPLIANT_PAGE`, `BLOCK`).
5. Otherwise `DeepLinkHandler.create_session(promo_id, domain, user_agent, …)` writes a row into `browser_sessions` and produces a `session_id`.
6. The User-Agent is fed into `iab_detector.detect_browser(...)`. If we're inside an in-app browser (Facebook, Instagram, Twitter, …), `safari_escape.generate_escape_page(...)` returns an HTML "bridge" page that:
   * writes `deferlink:<session_id>` into the clipboard via `navigator.clipboard.writeText` (with `execCommand('copy')` fallback and `localStorage` backup);
   * sets a small `Set-Cookie: dl_session_id=…` header (used by the SFSafariViewController shared cookie jar later);
   * redirects to the App Store after `redirect_delay_ms` (default 400 ms).
7. For real Safari we just set the cookie and `302` straight to App Store.

## Request flow — app first launch (`/resolve`)

The iOS SDK calls this once per device, on the very first launch, with a `FingerprintPayload`:

```jsonc
POST /resolve
{
  "fingerprint": {
    "model":            "iPhone15,2",
    "language":         "en-US",
    "timezone":         "Europe/Belgrade",
    "user_agent":       "DeferLinkSDK/1.0 …",
    "screen_width":     1170,
    "screen_height":    2532,
    "platform":         "iOS",
    "app_version":      "1.0",
    "idfv":             "EBC1F1F0-…",

    "clipboard_token":         "deferlink:<session_id>",   // tier 1
    "safari_cookie_session_id": "<session_id>",            // tier 2
    "device_check_token":      "<base64>",                 // tier 3
    "is_first_launch":         true
  },
  "app_scheme":   "myapp://test",
  "fallback_url": "https://apps.apple.com/…"
}
```

`DeepLinkHandler.resolve_matching_session(...)` walks four tiers in this order; the first one that hits short-circuits the rest:

| # | Method | Confidence | Source field |
|---|---|---|---|
| 1 | **Clipboard** | 100 % | `clipboard_token` parsed against `CLIPBOARD_TOKEN_PREFIX` |
| 2 | **Safari cookie** | ~99 % | `safari_cookie_session_id` (from SFSafariViewController) |
| 3 | **DeviceCheck** | ~97 % | `device_check_token` verified at Apple, hash compared |
| 4 | **Fingerprint** | 60–90 % | `IntelligentMatcher.find_best_match(...)` with dynamic threshold |

Response shape (see `app/api/deeplinks.py`):

```jsonc
{
  "success":      true,                  // request was processed (NOT == matched)
  "matched":      true,                  // attribution was found
  "match_method": "clipboard",
  "promo_id":     "summer_sale",
  "session_id":   "f3c2…",
  "domain":       "example.com",
  "redirect_url": "https://apps.apple.com/…",
  "app_url":      "myapp://test",
  "message":      "Сессия успешно разрешена"
}
```

`success=true, matched=false` means "request OK, no attribution found" — that's the expected outcome for organic installs and is **not** an error.

## Event ingestion

The SDK posts batches to `POST /api/v1/events/batch`:

* Each `DeferLinkEvent` carries `event_id` (client UUID, dedup key), `event_name` (`af_purchase` etc.), optional `revenue` + `currency`, optional `properties` (≤50 entries), `session_id` / `promo_id` (auto-stamped after resolve), `app_user_id`, plus device context.
* `app/core/event_tracker.insert_events_batch(...)` writes rows into `user_events` with `INSERT OR IGNORE` — duplicates are silently dropped.
* If a CAPI config exists for the app's `app_id`, `CAPIService.forward(...)` queues a Facebook conversion. PII fields (`em`, `ph`, `external_id`) are SHA-256 hashed; `client_ip_address` and `client_user_agent` go through verbatim.

Failures are written to `capi_delivery_log` with `next_retry_at` set to `now + 60s`. The retry worker doubles up on the schedule `[60s, 300s, 1800s]` for up to three attempts; after that the row is parked (`next_retry_at = NULL`) for manual inspection through `/api/v1/capi/log`.

## SKAdNetwork pipeline

Apple posts conversion data to `POST /api/v1/skadnetwork/postback`. `PostbackParser.parse(...)` decodes versions 2, 3 and 4, validates the ECDSA signature against Apple's published P-256 public key, and returns a `SKANPostback`. `SKANService.ingest_postback(...)`:

1. Persists the row in `skan_postbacks` (`transaction_id` is `UNIQUE`; duplicates are no-ops).
2. Updates the daily distribution table for fast dashboards.
3. If a `CampaignDecoder` rule matches the `(app_id, campaign_key, conversion_value)` triple, returns a `CAPIEventInstruction` with `capi_event`, `value` and `currency`.

The instruction is then dispatched through the same `CAPIService.forward(...)` as SDK events — so a single Facebook pixel sees both client-tracked and SKAN-attributed conversions, deduplicated by Apple's `transaction_id` (used as the CAPI `event_id`).

The SDK side mirrors the bit layout exactly (`CVEncoder.swift`) and submits CV via `SKAdNetwork.updatePostbackConversionValue` — preferring the iOS 16.1 fine+coarse API and falling back through 15.4 and 14.0 SDKs.

## Threading & concurrency

* Backend: a single `uvicorn` worker is fine for moderate load. SQLite is opened with `WAL` and short-lived connections per request (`db_manager.get_connection()`); long-running async tasks (CAPI retry) open their own connection per tick to avoid cross-task sharing.
* iOS SDK: every public method on `DeferLink` and `SKANManager` is `@MainActor`. Network calls go through `DeferLinkClient` (an `URLSession` async API). The event queue uses a serial `DispatchQueue` for file I/O and is drained on a `Timer` plus app-lifecycle hooks.

## Database

SQLite, single file at `DATABASE_PATH`. Migrations in `app/migrations/` add (in order): enhanced fingerprint fields, events table, DeviceCheck fields, cloaking tables, SKAdNetwork tables, CAPI tables, and a uniqueness constraint on `(app_id, platform)` for CAPI configs. Each migration is idempotent (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE … ADD COLUMN`) and safe to re-run.

## Where to read next

* HTTP endpoints, request/response shapes — [`api-reference.md`](api-reference.md)
* All backend modules (matching, IAB detection, escape page, event tracker, DB) — [`backend.md`](backend.md)
* Cloaking math and rule format — [`cloaking.md`](cloaking.md)
* Conversion-value bit layout and decoder rules — [`skadnetwork.md`](skadnetwork.md)
* Facebook CAPI payload, hashing, retry — [`capi.md`](capi.md)
* iOS SDK public surface — [`sdk-ios.md`](sdk-ios.md)
* Step-by-step install + run + test — [`install-and-test.md`](install-and-test.md)
