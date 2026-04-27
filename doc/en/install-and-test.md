# Install, run and test

This document walks through:

1. Running the backend locally
2. Pointing the iOS SDK at it
3. Running the automated test suites
4. A production checklist

## Prerequisites

* Python 3.10+ (uses `from __future__ import annotations` and PEP 604 unions extensively)
* macOS / Linux (Windows works but is untested)
* Xcode 15+ for the SDK and the test harness app
* iOS 14.0+ on simulator or device

## 1. Backend

```bash
git clone https://github.com/your-org/deferlink.git
cd deferlink

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

`requirements.txt` is intentionally tiny:

```
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
python-multipart==0.0.6
python-dotenv==1.0.0
httpx==0.26.0
cryptography==42.0.5
```

### Run

```bash
python run.py
```

`run.py` validates the config, then launches `uvicorn` with `app.main:app`. Bind address comes from `API_HOST` / `API_PORT` (defaults `0.0.0.0:8000`).

Sanity check:

```bash
curl http://localhost:8000/api/v1/health/quick
# {"status":"ok"}

curl http://localhost:8000/api/v1/health
# {"status":"ok","db":"ok","version":"..."}
```

The first launch creates `data/deeplinks.db` and runs all migrations under `app/migrations/` automatically — they're idempotent, so you can re-run the server safely.

### Configuration

Every setting lives in `app/config.py`. Defaults are dev-friendly. The most common ones:

| Variable | Default | Notes |
|---|---|---|
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8000` | Bind address. From the iOS Simulator point the SDK at `127.0.0.1`. |
| `API_WORKERS` | `1` | Set ≥2 only if you front it with a real DB. SQLite is single-writer. |
| `DATABASE_PATH` | `data/deeplinks.db` | SQLite file. Make sure the directory is writable. |
| `DEFAULT_TTL_HOURS` | `48` | How long browser sessions live before cleanup. Range 1–168. |
| `CLEANUP_INTERVAL_MINUTES` | `5` | Background cleanup tick. |
| `SECRET_KEY` | dev-secret | **Must change for production**, ≥32 chars, not a weak pattern. |
| `ENVIRONMENT` | `development` | Set to `production` to enable strict `validate_config()`. |
| `COOKIE_SECURE` | `false` | `true` once you serve over HTTPS. |
| `COOKIE_SAMESITE` | `lax` | One of `lax|strict|none`. Use `none` only with `COOKIE_SECURE=true`. |
| `CORS_ORIGINS` | `*` | Comma-separated list. |
| `TRUST_PROXY_HEADERS` | `false` | Set `true` behind nginx/Cloudflare so `X-Forwarded-For` is honoured. |
| `LOG_LEVEL` | `INFO` | `DEBUG` enables `uvicorn --reload`. |
| `APP_STORE_ID` | — | iTunes app id used by the escape page meta tags. |
| `APP_NAME` | — | Display name on the escape page. |
| `APP_URL_SCHEME` | `deferlink` | Must match the SDK `appURLScheme` and your `Info.plist`. |
| `CLIPBOARD_TOKEN_PREFIX` | `deferlink` | Must match SDK `clipboardTokenPrefix`. |
| `DEVICECHECK_ENABLED` | `false` | Tier-3 attribution. |
| `DEVICECHECK_TEAM_ID` / `_KEY_ID` / `_KEY_PATH` | — | Apple Developer credentials, `.p8` file. |
| `DEVICECHECK_SANDBOX` | `true` | Set `false` in production. |
| `CAPI_RETRY_INTERVAL_SECONDS` | `300` | CAPI retry worker tick. |
| `AUTO_OPTIMIZE_WEIGHTS` | `false` | Opt-in: periodic recompute of fingerprint matcher weights. |

To customise locally:

```bash
export DATABASE_PATH=./data/dev.db
export DEFAULT_TTL_HOURS=72
export LOG_LEVEL=DEBUG
python run.py
```

## 2. iOS SDK

### As a Swift Package

In Xcode → **File → Add Package Dependencies…** → paste your fork URL of `DeferLinkSDK`, or drag the local `DeferLinkSDK/` folder as a package into your workspace.

### Minimal integration

```swift
// AppDelegate.swift (or @main App init)
import DeferLinkSDK

DeferLink.configure(
    baseURL:      "http://127.0.0.1:8000",   // simulator: 127.0.0.1; device: your LAN IP
    appURLScheme: "myapp",                    // must match Info.plist URL Types
    debugLogging: true
)

DeferLink.shared.resolveOnFirstLaunch { result in
    if let promoId = result?.promoId {
        // navigate to /promo/<promoId>
    }
}

// SceneDelegate.swift
func scene(_ scene: UIScene, openURLContexts URLContexts: Set<UIOpenURLContext>) {
    URLContexts.forEach { DeferLink.shared.handleOpenURL($0.url) }
}
```

Optional events + SKAN:

```swift
DeferLink.shared.logEvent(.purchase(9.99, currency: "USD"))
DeferLink.shared.enableSKAdNetwork(appId: "1234567890")
```

Make sure your `Info.plist` has the URL scheme:

```xml
<key>CFBundleURLTypes</key>
<array>
  <dict>
    <key>CFBundleURLSchemes</key>
    <array><string>myapp</string></array>
  </dict>
</array>
```

The full SDK reference is in [`sdk-ios.md`](sdk-ios.md).

## 3. Tests

### Backend

```bash
pytest                                    # all tests
pytest tests/test_deeplink_handler.py     # one module
pytest -k capi                            # by keyword
pytest -v --tb=short                      # verbose with short tracebacks
```

Suites currently shipped under `tests/`:

| File | Covers |
|---|---|
| `test_main_flow.py` | end-to-end `/dl` → `/resolve` happy paths |
| `test_deeplink_handler.py` | `DeepLinkHandler` four-tier matching |
| `test_event_tracker.py` | events insertion, batch dedup, stats, funnels, cohort revenue |
| `test_capi.py` | `CAPIService.forward`, retry schedule, dedup |
| `test_cv_schema.py` | bit-packing round-trips, bucket boundaries |
| `test_postback_parser.py` | SKAN v3/v4 parsing, signature validation |
| `test_campaign_decoder.py` | decoder rule resolution, coarse-CV mapping |
| `test_skan_service.py` | postback ingestion + dedup + distribution |
| `test_devicecheck.py` | DeviceCheck verifier degraded mode |
| `test_utils.py` | UA / IP helpers |

`tests/conftest.py` builds an isolated SQLite file per test session and runs migrations.

### Testing the iOS SDK

A SwiftUI harness lives in `DeferLinkTestApp/`:

1. Open `DeferLinkTestApp.xcodeproj` in Xcode.
2. Edit `DeferLinkTestApp/NetworkManager.swift` — set `baseURL` to your server. For the iOS Simulator use `http://127.0.0.1:8000`; for a physical device use your machine's LAN IP and ensure your firewall allows it.
3. Run the **DeferLinkTestApp** scheme.
4. Tap **Run All Tests**. The harness drives every endpoint, exercises seeded `/dl` → `/resolve` scenarios with synthetic fingerprints, runs analytics flows, and verifies SKAN CV submission. Each test prints a green/red status row.

Unit tests for the SDK itself live in `DeferLinkSDK/Tests/DeferLinkSDKTests/` — open `DeferLinkSDK/Package.swift` and run the bundled test plan.

### Quick manual smoke test

```bash
# 1) seed a session
curl -X POST http://localhost:8000/api/v1/session \
     -H 'Content-Type: application/json' \
     -d '{"promo_id":"summer_sale","domain":"example.com"}'

# 2) try to resolve with a contrived fingerprint
curl -X POST http://localhost:8000/resolve \
     -H 'Content-Type: application/json' \
     -d '{
       "fingerprint": {
         "model":"iPhone15,2","language":"en-US",
         "timezone":"Europe/Belgrade","platform":"iOS",
         "user_agent":"DeferLinkSDK/1.0 (iPhone; iOS 17.0)",
         "screen_width":1170,"screen_height":2532,
         "is_first_launch":true
       },
       "app_scheme":"myapp://test",
       "fallback_url":"https://apps.apple.com"
     }'
```

## 4. Production checklist

Before exposing the backend to real traffic:

- [ ] **`ENVIRONMENT=production`** + **`SECRET_KEY`** set to a real ≥32-char value (`generate_secure_secret_key()` from `app/config.py` is fine).
- [ ] HTTPS terminator in front (nginx/Caddy/CDN). Set **`COOKIE_SECURE=true`**, **`COOKIE_SAMESITE=none`** (so SFSafariViewController shares the cookie cross-context), **`TRUST_PROXY_HEADERS=true`**.
- [ ] **`CORS_ORIGINS`** restricted to your real ad-domain(s).
- [ ] `DEVICECHECK_ENABLED=true` with `DEVICECHECK_SANDBOX=false` and a real `.p8` key. Verify with `POST /resolve` and a real `device_check_token`.
- [ ] CAPI configs created via `POST /api/v1/capi/configs` for every `(app_id, platform)`. Run `POST /api/v1/capi/test` to confirm.
- [ ] SKAN decoders created via `POST /api/v1/skadnetwork/decoders` for every campaign you intend to forward.
- [ ] Cloaking: review `cloaking_decision_log` after a few hours; tighten / loosen rules through `/api/v1/cloaking/*` as needed.
- [ ] Backups: `data/deeplinks.db` is the entire state. WAL files (`-wal`, `-shm`) live alongside. A periodic `sqlite3 deeplinks.db ".backup '/backup/path.db'"` cron is enough.
- [ ] Logs: `LOG_LEVEL=INFO` is appropriate; `DEBUG` enables `uvicorn --reload` (don't use in prod).
- [ ] Resource limits: SQLite + single uvicorn worker handles thousands of `/dl` per minute on a small VPS. If you outgrow that, run multiple workers behind a single writer (`API_WORKERS=N`) and consider migrating to Postgres — see `app/database.py` for the boundary.

## Help

For commercial integrations, ad-network adapters, custom CV schemas, on-prem deployment help or anything not covered here:

* 📧 **Email** — [tdk@null.net](mailto:tdk@null.net)
* 📨 **Telegram** — [@smail_ios](https://t.me/smail_ios)
