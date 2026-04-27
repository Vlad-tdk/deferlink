# Backend modules

This is the per-file map of `app/`. Every module is described in terms of its public surface and the contracts it relies on. Cross-cutting concerns (cloaking, SKAN, CAPI) have their own deep-dives.

## `app/main.py`

Entry point for the ASGI app. Builds the FastAPI instance, registers routers from `app/api/*`, and owns the `lifespan` handler that:

* runs `Config.validate_config()`;
* opens the SQLite database via `db_manager` and applies all migrations from `app/migrations/`;
* loads cloaking rules into `CloakingEngine` and decoders/configs into `SKANService`;
* loads CAPI configs (`CAPIService.load_configs`);
* spawns three asyncio tasks (cleanup, optimisation, CAPI retry) and tears them down on shutdown.

It also defines four "public" endpoints not under `/api/v1/`: `GET /`, `GET /dl`, `POST /resolve`, `GET /safari-resolve`. Bot detection happens at this layer so cloaking can short-circuit before any DB writes. Reverse-proxy IP extraction respects `TRUST_PROXY_HEADERS` (when true, `X-Forwarded-For`'s first entry wins).

## `app/config.py`

Single `Config` class — all fields read from environment with sensible dev defaults. Notable groups:

* **Database / API** — `DATABASE_PATH`, `API_HOST`, `API_PORT`, `API_WORKERS`.
* **Security** — `SECRET_KEY` (must be ≥32 chars and not match weak-pattern blacklist when `ENVIRONMENT=production`), `COOKIE_SECURE`, `COOKIE_SAMESITE` (`lax|strict|none`), `CORS_ORIGINS`.
* **Deep linking** — `DEFAULT_TTL_HOURS` (browser session TTL, 1–168), `MAX_FINGERPRINT_DISTANCE`, `CLEANUP_INTERVAL_MINUTES`.
* **Apple DeviceCheck** — `DEVICECHECK_ENABLED`, `DEVICECHECK_TEAM_ID`, `DEVICECHECK_KEY_ID`, `DEVICECHECK_KEY_PATH`, `DEVICECHECK_SANDBOX`.
* **IAB escape** — `APP_STORE_ID`, `APP_NAME`, `CLIPBOARD_TOKEN_PREFIX` (must match SDK), `APP_URL_SCHEME`.
* **Background workers** — `CAPI_RETRY_INTERVAL_SECONDS` (>0), `AUTO_OPTIMIZE_WEIGHTS`.

`validate_config()` raises `ValueError` on bad combinations. `generate_secure_secret_key()` returns `secrets.token_urlsafe(32)`.

## `app/database.py` and migrations

`db_manager` exposes a context manager `get_connection()` (per-request, WAL mode) and `execute_query(sql, params)` returning a list of `Row` dicts. SQLite is fine for moderate single-host load; replace with a proper engine if you need horizontal scale.

Migrations in `app/migrations/` add tables and columns idempotently. Order:

1. `add_enhanced_fields.py` — extra fingerprint columns on `browser_sessions`.
2. `add_events_table.py` — `user_events` (analytics).
3. `add_devicecheck_fields.py` — DeviceCheck token hash + verification status.
4. `add_cloaking_tables.py` — `cloaking_ip_rules`, `cloaking_ua_rules`, `cloaking_decision_log`.
5. `add_skadnetwork_tables.py` — `skan_postbacks`, `skan_campaign_decoders`, `skan_cv_configs`, `skan_cv_distribution`.
6. `add_capi_tables.py` — `capi_configs`, `capi_delivery_log`.
7. `enforce_capi_unique_app_platform.py` — uniqueness on `(app_id, platform)`.

## `app/deeplink_handler.py`

The orchestrator that ties browser sessions to app resolves.

* `create_session(promo_id, domain, user_agent, fingerprint=None, ttl_hours=Config.DEFAULT_TTL_HOURS)` — inserts a row into `browser_sessions` and returns `session_id`.
* `resolve_matching_session(fingerprint, device_check_token_b64=None)` — runs the four-tier match in order, returning `None` or a dict that includes `session_id`, `promo_id`, `domain`, `match_method` and `match_confidence`.
* `cleanup_expired()` — drops sessions older than TTL (called by background task and `POST /api/v1/cleanup`).

Implementation detail worth noting: the function-local parameter `timezone` was previously shadowing `datetime.timezone`; the module now imports it as `from datetime import … timezone as _tz` and uses `_tz.utc`. If you fork this module, keep that alias.

## `app/core/intelligent_matcher.py`

`IntelligentMatcher` produces a `MatchResult` from one app fingerprint and a list of candidate browser sessions.

* Weighted score over `timezone (0.35)`, `screen_dimensions (0.25)`, `language (0.20)`, `device_model (0.15)`, `user_agent (0.05)`. Weights are mutable through `update_weights(...)` (the optional optimisation task uses this).
* Per-component sub-scoring is sophisticated: equivalent IANA zones, UTC offset fallback, screen aspect-ratio comparison, fuzzy device-model jaccard with curated mappings (`iPhone14,2 ↔ iPhone 13 Pro`), language family relations.
* `_validate_temporal_patterns` multiplies the score by a time-since-session factor — too soon (<10 s) or too late (>24 h) penalises the match.
* `_get_dynamic_threshold` picks a threshold in `[0.50, 0.90]` based on hour of day and `_assess_fingerprint_quality(...)` — sparser fingerprints need more confidence to win.
* All sub-scores are cached per `(browser_value, app_value)` pair.

## `app/core/devicecheck.py`

Server-side `DeviceCheck` verifier.

* `DeviceCheckVerifier.verify(token)` is `async`. Returns `DeviceCheckResult(valid, status, reason, bit0, bit1, last_update_time, is_new_device)`.
* In "degraded mode" (no Apple credentials or missing `PyJWT`/`httpx`/`cryptography`) the verifier returns `status="indeterminate"` so the handler will not trust the token but doesn't crash.
* `hash_token(token)` returns SHA-256 hex — the only form ever stored.
* Module-level `get_verifier()` / `init_verifier(...)` singleton.

## `app/core/safari_escape.py`

`generate_escape_page(session_token, app_store_url, app_name, app_store_id, redirect_delay_ms=400)` returns the full HTML for the IAB-escape bridge. Three clipboard strategies in series — modern Clipboard API, `execCommand('copy')`, `localStorage` — followed by `setTimeout(redirect, delay_ms)`.

`build_app_store_url(app_store_id)` returns `https://apps.apple.com/app/id<id>`.

The clipboard payload is `f"{CLIPBOARD_PREFIX}:{session_token}"` (default prefix `"deferlink"`). The SDK side parses with the same prefix and validates that the suffix is at least 32 chars before trusting it.

## `app/core/iab_detector.py`

`detect_browser(user_agent)` returns a `BrowserDetectionResult` with:

* `context` — one of `BrowserContext.{SAFARI, FACEBOOK_IAB, INSTAGRAM_IAB, TIKTOK_IAB, TWITTER_IAB, WECHAT_IAB, SNAPCHAT_IAB, GENERIC_IAB, CHROME_IOS, UNKNOWN}`.
* `is_iab` — boolean.
* `clipboard_reliable` — whether `execCommand('copy')` works without a user gesture in this context (Facebook/Instagram/Twitter: yes; TikTok/WeChat/Snapchat: no).
* `escape_strategy` — `EscapeStrategy.{NONE, CLIPBOARD_THEN_APPSTORE, APPSTORE_REDIRECT, UNIVERSAL_LINK}`.

`should_escape_to_safari(result)` returns the convenience boolean.

## `app/core/event_tracker.py`

Pure DB layer for `user_events`.

* `STANDARD_EVENTS` — set of `af_*` names mirroring AppsFlyer.
* `insert_event(...)` — single insert with `INSERT OR IGNORE`. Returns `"inserted" | "duplicate" | "failed"`.
* `insert_events_batch(events, ip_address)` — pre-checks each `event_id` for duplicates and tallies counts.
* `get_event_stats(start, end, promo_id)` — totals, top 20 events, revenue by currency.
* `get_funnel(steps, start, end, promo_id)` — ordered funnel; per-step user count + conversion vs prev/first.
* `get_cohort_revenue(promo_id, days=30)` — daily revenue per `(promo_id, currency)`.

## `app/core/cloaking/`

See [`cloaking.md`](cloaking.md). Brief summary:

* `engine.py` — `CloakingEngine.decide(...)` aggregates signals via `1 − ∏(1 − cᵢ)` Bayesian accumulation, with `HARD_THRESHOLD = 0.88`, `SOFT_THRESHOLD = 0.65`, `BOT_SUSPICION_BOOST = 0.15`. Behavioural signals can lift confidence on top of an authoritative signal but cannot single-handedly classify as bot/ad-review.
* `ip_detector.py` — exact IP, CIDR (most-specific first), ASN. Custom rules from DB merge with builtins from `known_data.KNOWN_IP_RANGES` / `KNOWN_ASNS`.
* `ua_detector.py` — case-insensitive regex matching, custom rules win over builtins.
* `behavior_detector.py` — header heuristics with weights `no_accept_language=0.50`, `no_sec_fetch_site=0.45`, `no_accept=0.30`, `minimal_accept=0.25`, `no_accept_encoding=0.25`, `connection_close=0.15`, `no_referer=0.10`, `no_cookies=0.10`. All map to `VisitorType.SUSPICIOUS`.
* `models.py` — `VisitorType`, `CloakingAction`, `DetectionSignal`, `CloakingDecision`, `IPRule`, `UARuleRecord`.

## `app/core/skadnetwork/`

See [`skadnetwork.md`](skadnetwork.md). Brief summary:

* `cv_schema.py` — bit-packing helpers `encode_cv` / `decode_cv_bits`, `CVSchema` class with revenue bucketing, engagement tier computation and `decode(cv) → DecodedCV`. Default revenue buckets `[0, 0.01, 1, 5, 20, 50, 100, 300]` USD.
* `models.py` — `CoarseValue`, `FidelityType`, `PostbackSequence` (PB1/PB2/PB3), `SKANPostback`, `SKANConfig`, `DecoderRule` (with `cv_min/cv_max` inclusive range, `static_value` or `value_multiplier`).
* `postback_parser.py` — defensive parser, optional ECDSA P-256 signature verification using Apple's published public key.
* `campaign_decoder.py` — first-rule-wins lookup by `(app_id, campaign_key)`. Coarse-only postbacks are mapped to synthetic CVs (low→0, medium→31, high→63) for rule matching.
* `service.py` — `SKANService.ingest_postback(payload, conn) → (postback, row_id, capi_instruction_or_none)`.

## `app/core/capi/`

See [`capi.md`](capi.md). Brief summary:

* `models.py` — `CAPIPlatform`, `CAPIConfig` (per-app credentials), `CAPIUserData` (PII fields, mostly hashed), `CAPIEventData` (with `event_id` as dedup key), `CAPIDeliveryResult`.
* `facebook.py` — `FacebookCAPIClient.send(config, event)` posts to `graph.facebook.com/{api_version}/{pixel_id}/events?access_token=…`. Hashes `em`, `ph`, `external_id` (idempotent — already-hashed values are passed through unchanged).
* `service.py` — `CAPIService.forward(conn, app_id, event, platform)` with dedup against `capi_delivery_log`. Retry schedule `[60, 300, 1800]` seconds, max 3 attempts.
* `retry_worker.py` — long-running asyncio loop; `start_capi_retry_worker(interval_seconds=300)` factory. Defaults to `300 s` to match the smallest retry slot.

## `app/utils.py`

Small helpers — UA normalisation, IP extraction with proxy-aware fallbacks, ISO time formatting. Read directly if you need to plug in your own bot detection.

## What you typically import

| You want to | Import |
|---|---|
| Validate a request & write a session | `from app.deeplink_handler import DeepLinkHandler` (instantiated in `app/main.py`) |
| Score a UA at runtime | `from app.core.cloaking.engine import get_engine` |
| Submit an Apple postback | `from app.core.skadnetwork.service import skan_service` |
| Forward a custom event to Facebook | `from app.core.capi.service import capi_service` |
| Run analytics | `from app.core.event_tracker import get_event_stats, get_funnel` |
| Generate the escape page | `from app.core.safari_escape import generate_escape_page` |
| Detect IAB | `from app.core.iab_detector import detect_browser` |
