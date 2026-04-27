# Facebook Conversions API

`app/core/capi/` is a self-contained CAPI forwarder. It accepts platform-agnostic event data, dispatches to the configured platform client (currently Facebook only), persists every attempt in `capi_delivery_log`, and runs a background worker that retries failures on a fixed schedule.

## Module layout

| File | Role |
|---|---|
| `models.py` | Data classes — `CAPIPlatform`, `CAPIConfig`, `CAPIUserData`, `CAPIEventData`, `CAPIDeliveryResult`. |
| `facebook.py` | `FacebookCAPIClient` — actual HTTPS POST to `graph.facebook.com`, payload assembly, PII hashing. |
| `service.py` | `CAPIService` — config cache, `forward()`, `retry_pending()`, dedup, persistence. Module singleton `capi_service`. |
| `retry_worker.py` | `CAPIRetryWorker` asyncio task; `start_capi_retry_worker(interval_seconds=…)` factory. |

## Wire flow

```
SDK / SKAN
   │
   ▼
CAPIEventData   ──►  CAPIService.forward(conn, app_id, event, platform)
                          │
                          ├─ dedup vs capi_delivery_log (succeeded=1)
                          ├─ resolve CAPIConfig from cache
                          ├─ FacebookCAPIClient.send(...)
                          │      → POST https://graph.facebook.com/v21.0/{pixel}/events
                          ├─ INSERT INTO capi_delivery_log (...)
                          ▼
                   CAPIDeliveryResult
```

A separate background loop calls `CAPIService.retry_pending(conn)` every `CAPI_RETRY_INTERVAL_SECONDS` (default 300).

## CAPIConfig

Per-app + per-platform credentials, kept in `capi_configs` with a uniqueness constraint on `(app_id, platform)` (see `migrations/enforce_capi_unique_app_platform.py`).

```jsonc
{
  "id":              1,
  "app_id":          "com.example.app",
  "platform":        "facebook",
  "pixel_id":        "1234567890",
  "access_token":    "<long-lived CAPI token>",
  "test_event_code": "TEST12345",   // optional, for FB dashboard verification
  "api_version":     "v21.0",
  "enabled":         true
}
```

`CAPIService.load_configs(conn)` builds an in-memory `(app_id, platform) → CAPIConfig` cache. Admin endpoints under `/api/v1/capi/configs` reload after every mutation.

## CAPIEventData

```python
@dataclass
class CAPIEventData:
    event_name:      str          # "Purchase", "Lead", "CompleteRegistration"
    event_id:        str          # dedup key (UUID for SDK, Apple txn-id for SKAN)
    event_time:      int          # unix seconds
    event_source_url: Optional[str] = None
    action_source:   str = "app"  # "app" | "website" | "email" | …
    user_data:       CAPIUserData = field(default_factory=CAPIUserData)
    value:           Optional[float] = None
    currency:        Optional[str]   = None
    custom_data:     Dict[str, Any]  = {}
    source:          str = "manual"  # "sdk" | "skan" | "manual"
    source_ref_id:   Optional[int] = None
```

`source` and `source_ref_id` are stored in the delivery log so a row in `skan_postbacks.id` or `user_events.id` can always be traced back through CAPI.

## PII hashing

`FacebookCAPIClient._hash_user_data(...)`:

| Field | Hashed? | Notes |
|---|:---:|---|
| `client_ip_address` | no | sent verbatim |
| `client_user_agent` | no | sent verbatim |
| `fbp`, `fbc` | no | already opaque ids |
| `em` (email) | yes | lower-case + `sha256` |
| `ph` (phone) | yes | lower-case + `sha256` |
| `external_id` (app_user_id) | yes | lower-case + `sha256` |

Hashing is idempotent: a value that is already exactly 64 lower-case hex characters is passed through unchanged. This means the SDK can pre-hash on device (recommended for `external_id`) without producing double-hashed garbage on the server.

## Payload shape (Facebook)

```jsonc
POST https://graph.facebook.com/v21.0/{pixel_id}/events?access_token=…
{
  "data": [
    {
      "event_name":    "Purchase",
      "event_time":    1700000000,
      "event_id":      "uuid-or-skan-txn-id",
      "action_source": "app",
      "user_data": {
        "client_ip_address": "203.0.113.7",
        "client_user_agent": "DeferLinkSDK/1.0 …",
        "external_id":       "<sha256>",
        "em":                "<sha256>"
      },
      "custom_data": {
        "value":    9.99,
        "currency": "USD"
      }
    }
  ],
  "test_event_code": "TEST12345"
}
```

`event_source_url`, `value`, `currency` and `custom_data` are only emitted when present. Response bodies are truncated to 2000 chars in the delivery log to keep the table small.

## Deduplication

Before sending, `CAPIService.forward(...)` runs:

```sql
SELECT id FROM capi_delivery_log
 WHERE app_id   = ?
   AND platform = ?
   AND event_id = ?
   AND succeeded = 1
 LIMIT 1
```

If a successful delivery exists, no new request is made; the call returns `success=true, response_body="[dedup] already delivered"` and the existing `delivery_log_id`.

Combined with Facebook's own server-side `event_id` deduplication, this means:

* Repeated SDK retries of the same event ⇒ delivered once.
* SKAN postback that arrives after an SDK `af_purchase` with matching `event_id` ⇒ delivered once.
* SKAN PB1 arriving after PB1 was already retried successfully ⇒ delivered once.

For SKAN, the dedup `event_id` is **Apple's `transaction_id`**.

## Retry semantics

Schedule (`_RETRY_SCHEDULE = [60, 300, 1800]` seconds):

| Attempt | Backoff before next |
|---:|---|
| 1 (initial) | +60 s |
| 2 | +300 s |
| 3 | +1800 s |
| 4+ | parked (`next_retry_at = NULL`) |

`_MAX_ATTEMPTS = 3` — after the third failed attempt the row is left with `succeeded=0, next_retry_at=NULL`. It is visible at `GET /api/v1/capi/log` and can be force-retried via `POST /api/v1/capi/retry/{row_id}`.

The retry worker runs:

```python
async def _tick(self) -> int:
    with self._db_manager.get_connection() as conn:
        return await self._service.retry_pending(conn)
```

`retry_pending(conn)` reads up to 100 due rows ordered by `next_retry_at ASC`, re-POSTs each pre-built payload (saved in `payload_json`), updates `attempts`, `last_error`, `last_attempt_at`, and `next_retry_at`. A fresh DB connection is opened per tick — `sqlite3` connections cannot be shared across tasks.

The default tick interval is 300 s; the worker clamps `interval_seconds` to a minimum of 30 s.

## Failure modes

| `delivery_log` row state | Meaning |
|---|---|
| `succeeded=1` | Done. Will be ignored by all future retries and dedup checks. |
| `succeeded=0, next_retry_at <= now` | Worker will pick it up on the next tick. |
| `succeeded=0, next_retry_at > now` | Backing off; will be retried at scheduled time. |
| `succeeded=0, next_retry_at IS NULL, attempts >= 3` | Parked, requires manual intervention. |
| `succeeded=0, next_retry_at IS NULL, last_error="no config"` | Lost CAPI config — re-create it and force-retry. |

`POST /api/v1/capi/retry/{row_id}` resets `next_retry_at` to "now" and lets the worker pick the row up immediately.

## Test endpoint

`POST /api/v1/capi/test` builds a synthetic `CAPIEventData` from request body, calls `CAPIService.forward(...)` with `source="manual"`, and returns the live `CAPIDeliveryResult`. Used to verify a freshly added pixel + access-token combo before flipping production traffic.

## Lifecycle integration

In `app/main.py:lifespan`:

```python
capi_service.load_configs(conn)
_capi_retry_worker = start_capi_retry_worker(interval_seconds=Config.CAPI_RETRY_INTERVAL_SECONDS)
...
await _capi_retry_worker.stop()
await capi_service.close()
```

`capi_service.close()` shuts down the underlying `httpx.AsyncClient` cleanly so connection pools don't leak across reload cycles.
