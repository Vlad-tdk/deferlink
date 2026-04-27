# SKAdNetwork 4.0

DeferLink ships a complete server-side SKAdNetwork pipeline:

* a 6-bit conversion-value (CV) schema shared 1:1 between the backend and the iOS SDK;
* an Apple postback receiver with version 2/3/4 parsing and ECDSA signature verification;
* a per-campaign decoder that maps `(app_id, campaign_key, conversion_value)` to a Facebook-CAPI event;
* a fast aggregate distribution table for dashboards.

All code lives under `app/core/skadnetwork/`. The Swift mirror lives in `DeferLinkSDK/Sources/DeferLinkSDK/SKAN/`.

## CV bit layout — schema `rev3_eng2_flag1`

```
 bit 5 4 3 │ 2 1 │ 0
 └─revenue─┘ └─eng─┘ flag

 revenue_bucket ∈ [0..7]   3 bits — log-scale USD buckets
 engagement     ∈ [0..3]   2 bits — bounce / active / deep / power
 event_flag     ∈ [0..1]   1 bit  — 1 = a real conversion event happened
```

Encoding:

```
cv = (revenue_bucket << 3) | (engagement << 1) | event_flag
```

`schema_name = "rev3_eng2_flag1"` is part of the wire contract and never changes; if you ever need a different layout, ship it under a new name and keep the old one for legacy installs.

### Default revenue buckets

| Bucket | Floor (USD) | Notes |
|---:|---:|---|
| 0 | 0.00     | Free user / no purchase |
| 1 | 0.01     | Micro / ads |
| 2 | 1.00     | Low |
| 3 | 5.00     | Standard |
| 4 | 20.00    | Mid (trial → sub) |
| 5 | 50.00    | High |
| 6 | 100.00   | Whale-track |
| 7 | 300.00   | Whale (open-ended) |

Per-app overrides are stored in `skan_cv_configs` and exposed to the SDK at `GET /api/v1/skan/config?app_id=…`.

### Engagement tiers

`CVSchema.engagement_tier(...)` is deterministic:

| Tier | Code | Trigger |
|---|---:|---|
| `bounce` | 0 | Default — short / single session |
| `active` | 1 | `sessions ≥ active_min_sessions` (default 2), or `total_seconds ≥ bounce_max_seconds × 4` |
| `deep`   | 2 | `sessions ≥ deep_min_sessions` (default 5), or `core_actions ≥ deep_min_core_actions` |
| `power`  | 3 | `power_requires_retention=true` AND returned next day AND retained day-2 AND core actions met |

Same constants are defined Swift-side in `SKANConfig.swift` so simulator and backend agree exactly.

## Postback parsing

`POST /api/v1/skadnetwork/postback` accepts Apple's JSON. `PostbackParser.parse(...)` does:

1. Pulls all known fields defensively (string casts, integer ranges, enum lookups). Unknown fields are kept inside `raw_json`.
2. Requires `transaction-id` and `ad-network-id` — anything else missing yields an `Optional`.
3. If `verify_signature=True` (default), runs `cryptography.hazmat` ECDSA-P256 SHA-256 verification with Apple's published public key (`APPLE_SKADNETWORK_PUBLIC_KEY_PEM`).
   * On success → `signature_verified=1`.
   * On failure → `signature_verified=2` (postback still stored, never silently dropped).
   * If `cryptography` isn't installed → verification is disabled at startup, all rows get `signature_verified=0`.

The signed-string composition is documented in `_build_signed_fields(...)`:

* **v4.x** — `version | ad-network-id | source-identifier | app-id | transaction-id | redownload | source-app-id|source-domain | fidelity-type | did-win | postback-sequence-index`
* **v3.0** — `version | ad-network-id | campaign-id | app-id | transaction-id | redownload | source-app-id | (fidelity-type)`

Fields are joined with the U+2063 invisible separator (Apple's spec).

## Postback sequences

```
PostbackSequence.PB1 = 0   # day 0–2  — fine CV available
PostbackSequence.PB2 = 1   # day 3–7  — coarse CV only
PostbackSequence.PB3 = 2   # day 8–35 — coarse CV only
```

Coarse-only postbacks are mapped to synthetic CVs for rule matching:

```
low    → cv = 0
medium → cv = 31
high   → cv = 63
```

This lets a single decoder rule list cover both PB1 (fine) and PB2/PB3 (coarse) without separate config.

## Persistence

`SKANService.ingest_postback(payload, conn)` returns `(SKANPostback, row_id, capi_instruction|None)`:

1. Parse + verify (above).
2. `INSERT INTO skan_postbacks (...)`. `transaction_id` has a `UNIQUE` constraint — duplicate Apple retries are no-ops, the existing `row_id` is returned with `inserted_new=False` and no instruction is produced.
3. `INSERT … ON CONFLICT … DO UPDATE` on `skan_cv_distribution(date, app_id, source_identifier, campaign_id, conversion_value)` — increments `postback_count` for fast charting.
4. If `app_id` is present, `CampaignDecoder.decode(pb, schema=CVSchema(config))` is consulted. If a rule matches → returns a `CAPIEventInstruction`. The route handler then forwards it through `CAPIService.forward(...)` (see [`capi.md`](capi.md)).
5. After CAPI dispatch, the route updates `capi_forwarded`, `capi_forwarded_at`, `capi_last_error` via `SKANService.mark_forwarded(...)`.

## Decoder rules

`DecoderRule` (in `models.py`):

```jsonc
{
  "cv_min":           20,        // inclusive 0..63
  "cv_max":           63,        // inclusive 0..63
  "capi_event":       "Purchase",
  "forward":          true,      // false silences this CV range
  "static_value":     null,      // when set: CAPI value = this (USD)
  "value_multiplier": 1.0,       // when static_value is null:
                                 //   value = midpoint(revenue_bucket) × multiplier
  "currency":         "USD",
  "description":      "Paid users — full revenue"
}
```

A decoder is an ordered list of rules. **First match wins.** No match → no CAPI event (intentional).

Stored in `skan_campaign_decoders`:

| Column | Notes |
|---|---|
| `app_id` | Bundle id, e.g. `com.example.app`. |
| `source_identifier` | SKAN 4 4-digit string. Use this for new campaigns. |
| `campaign_id` | Legacy SKAN 2/3 integer 0–99. Use only when SKAN 4 source-id is unavailable. |
| `decoder_json` | JSON list of `DecoderRule` objects (above). |
| `enabled` | `0`/`1`. Reload picks up changes immediately. |

The `(app_id, campaign_key)` lookup uses `source_identifier` first and falls back to `str(campaign_id)` — see `SKANPostback.campaign_key`.

## Per-app SKAN config

`GET /api/v1/skan/config?app_id=…` returns the SDK-facing JSON:

```jsonc
{
  "app_id":                  "com.example.app",
  "schema_version":          1,
  "schema_name":             "rev3_eng2_flag1",
  "revenue_buckets_usd":     [0.0, 0.01, 1.0, 5.0, 20.0, 50.0, 100.0, 300.0],
  "bounce_max_seconds":      30,
  "active_min_sessions":     2,
  "deep_min_sessions":       5,
  "deep_min_core_actions":   1,
  "power_requires_retention": true,
  "conversion_window_hours": 48,
  "cache_ttl_seconds":       86400
}
```

The iOS SDK fetches this once per `cache_ttl_seconds`, persists it locally, and computes CV from raw events using the same arithmetic as `CVSchema.compute_cv(...)`. SDK code: `CVEncoder.swift`, `SKANConfig.swift`.

## Admin endpoints

See [`api-reference.md`](api-reference.md#skadnetwork-appapiskadnetworkpy) — full CRUD on decoders, listing of recent postbacks, CV distribution stats per `(app_id, source_identifier, day)`.

## SDK side — submitting CV

```swift
// in your app
SKANManager.shared.recordEvent(.purchase(amount: 9.99, currency: "USD"))

// SKANManager will:
//   1. accumulate session/engagement metrics
//   2. compute fine CV via CVEncoder.computeCV(...)
//   3. call SKAdNetwork.updatePostbackConversionValue(...)
//      preferring the iOS 16.1 fine+coarse API,
//      falling back through 15.4 (coarse) and 14.0 (fine only).
```

The Swift implementation in `CVEncoder.swift` mirrors `cv_schema.py` byte-for-byte; both use `(rev << 3) | (eng << 1) | flag`.

## What you get end-to-end

1. App posts events via `/api/v1/events/batch`.
2. Locally, `SKANManager` rolls those into `(revenue, engagement, flag)` and updates the SKAN window via Apple's API.
3. Apple eventually posts to `/api/v1/skadnetwork/postback`. We persist + decode → optional CAPI event.
4. `CAPIService.forward(...)` dedup-keys on Apple's `transaction_id`, so the same Facebook pixel sees both client-side `af_purchase` events and server-side SKAN-attributed Purchases without double-counting.
