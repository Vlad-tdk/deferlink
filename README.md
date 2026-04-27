# DeferLink

**Self-hosted mobile attribution platform** — deferred deep linking, cloaking, SKAdNetwork 4.0 and Facebook Conversions API in one stack. iOS SDK + Python backend, no third-party MMP, full data ownership.

> Languages: **English (this file)** · [Русский](README_RU.md)
> Per-module docs: [`doc/en/`](doc/en/) · [`doc/ru/`](doc/ru/)

---

## What it does

| Capability | What you get |
|---|---|
| **Deferred deep linking** | A user clicks an ad → installs the app → opens it → lands on the *correct* promo screen. No paste, no manual code. |
| **4-tier matching** | Clipboard token (100 %) → SFSafariViewController shared cookie (~99 %) → Apple DeviceCheck (~97 %) → fingerprint (60–90 %). |
| **Cloaking engine** | IP / ASN / UA / behavioural detection of bots, ad reviewers and scrapers. SEO-page or compliant-page response per visitor type. |
| **SKAdNetwork 4.0** | 6-bit conversion-value scheme `[revenue:3][engagement:2][flag:1]` with PB1/PB2/PB3 postback handling and Apple ECDSA signature verification. |
| **Facebook Conversions API** | Auto-forwarding of SKAN postbacks and SDK events to Meta with deduplication and retry. |
| **Event tracking** | AppsFlyer-style standard events (`af_purchase`, `af_complete_registration`, …), funnels, cohort revenue, custom properties. |

---

## Quick start (5 minutes)

### 1. Run the backend

```bash
git clone https://github.com/your-org/deferlink.git
cd deferlink

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Optional: edit env vars (defaults are dev-friendly)
export API_HOST=0.0.0.0
export API_PORT=8000

python run.py
```

Server is now at `http://localhost:8000`. Sanity check:

```bash
curl http://localhost:8000/api/v1/health/quick
# {"status":"ok"}
```

### 2. Add the iOS SDK

In Xcode → **File → Add Package Dependencies…** → paste your fork URL of `DeferLinkSDK`, or drag the local `DeferLinkSDK/` folder as a Swift package.

```swift
// AppDelegate.swift
import DeferLinkSDK

func application(_ app: UIApplication,
                 didFinishLaunchingWithOptions launchOptions: …) -> Bool {
    DeferLink.configure(
        baseURL:      "https://api.your-domain.com",
        appURLScheme: "myapp",
        debugLogging: true
    )

    DeferLink.shared.resolveOnFirstLaunch { result in
        if let promoId = result?.promoId {
            // navigate to /promo/<promoId>
        }
    }
    return true
}

// SceneDelegate.swift
func scene(_ scene: UIScene, openURLContexts URLContexts: Set<UIOpenURLContext>) {
    URLContexts.forEach { DeferLink.shared.handleOpenURL($0.url) }
}
```

### 3. Track events (optional)

```swift
DeferLink.shared.logEvent(.purchase(9.99, currency: "USD"))
DeferLink.shared.logEvent("af_complete_registration",
                          properties: ["method": "email"])
```

### 4. Try it locally

A full SwiftUI test harness lives in `DeferLinkTestApp/` — it drives every endpoint and runs deterministic seed→resolve scenarios. Open `DeferLinkTestApp.xcodeproj`, point its `NetworkManager.baseURL` at your server (`http://127.0.0.1:8000` for the iOS Simulator), and tap *Run All Tests*.

Detailed install / run / test steps live in [`doc/en/install-and-test.md`](doc/en/install-and-test.md).

---

## Architecture at a glance

```
                ┌──────────────────────────────────────────┐
  ad click  →   │  /dl?promo_id=…&domain=…  (cloaking gate) │
                │      ├── bot/reviewer  → SEO_PAGE          │
                │      └── real user     → /escape (Safari)  │
                │           └── clipboard write + App Store  │
                └──────────────────────────────────────────┘
                                     │
                                user installs & opens app
                                     ▼
                ┌──────────────────────────────────────────┐
  app first    │  POST /resolve                              │
  launch  →    │   ├── tier 1: clipboard_token               │
                │   ├── tier 2: safari_cookie_session_id      │
                │   ├── tier 3: device_check_token            │
                │   └── tier 4: fingerprint (timezone + …)    │
                │      → returns promo_id, session_id         │
                └──────────────────────────────────────────┘
                                     │
                ┌──────────────────────────────────────────┐
   in-app     │  POST /api/v1/events/batch                  │
   events →   │   • dedup by event_id                       │
                │   • forward to Facebook CAPI                │
                │  Apple postback → /api/v1/skadnetwork/…     │
                │   • parse + verify signature + decode CV    │
                │   • forward to Facebook CAPI                │
                └──────────────────────────────────────────┘
```

A more detailed walkthrough — including module boundaries, threading model and DB schema — is in [`doc/en/architecture.md`](doc/en/architecture.md).

---

## Module map

| Subsystem | Code | Docs |
|---|---|---|
| HTTP API surface | `app/api/`, `app/main.py` | [`doc/en/api-reference.md`](doc/en/api-reference.md) |
| Deferred deep links | `app/deeplink_handler.py`, `app/core/intelligent_matcher.py`, `app/core/safari_escape.py` | [`doc/en/backend.md`](doc/en/backend.md) |
| Cloaking | `app/core/cloaking/` | [`doc/en/cloaking.md`](doc/en/cloaking.md) |
| SKAdNetwork | `app/core/skadnetwork/` | [`doc/en/skadnetwork.md`](doc/en/skadnetwork.md) |
| Facebook CAPI | `app/core/capi/` | [`doc/en/capi.md`](doc/en/capi.md) |
| iOS SDK | `DeferLinkSDK/Sources/DeferLinkSDK/` | [`doc/en/sdk-ios.md`](doc/en/sdk-ios.md) |

Russian mirror: [`doc/ru/`](doc/ru/).

---

## Configuration cheat-sheet

All settings come from environment variables — see `app/config.py` for the full list.

| Variable | Default | Notes |
|---|---|---|
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8000` | Bind address. For iOS Simulator point the SDK at `127.0.0.1`. |
| `DATABASE_PATH` | `data/deeplinks.db` | SQLite file. |
| `DEFAULT_TTL_HOURS` | `48` | How long browser sessions live before cleanup. |
| `SECRET_KEY` | `dev-secret-key-…` | **Must change in production**, ≥32 chars. |
| `ENVIRONMENT` | `development` | Set to `production` to enable strict validation. |
| `DEVICECHECK_ENABLED` | `false` | Apple DeviceCheck server-side verification. |
| `DEVICECHECK_TEAM_ID` / `_KEY_ID` / `_KEY_PATH` | — | Apple Developer credentials, `.p8` file. |
| `APP_STORE_ID` | — | Used by the `/escape` page meta-tag. |
| `APP_URL_SCHEME` | `deferlink` | Must match SDK `appURLScheme` and `Info.plist`. |
| `CAPI_RETRY_INTERVAL_SECONDS` | `60` | Background CAPI retry tick. |
| `LOG_LEVEL` | `INFO` | `DEBUG` enables `uvicorn --reload`. |

Production checklist is in [`doc/en/install-and-test.md`](doc/en/install-and-test.md#production-checklist).

---

## Running the test suite

```bash
pytest                          # backend unit + integration tests
pytest tests/test_deeplinks.py  # one module
```

For the iOS SDK and the test harness app, open the Xcode workspace and run the bundled test plan — details in [`doc/en/install-and-test.md`](doc/en/install-and-test.md#testing-the-ios-sdk).

---

## Status & versioning

* iOS SDK version: **1.0.0** (see `DeferLinkSDKInfo.version`)
* CV schema: **`rev3_eng2_flag1`** (stable wire contract — never breaks)
* Server: stateless workers + SQLite. Drop-in Postgres support is on the roadmap.

---

## Cooperation, integrations, custom builds

For commercial integrations, ad-network adapters, custom CV schemas, on-prem deployment help or anything not covered by the docs:

* 📧 **Email** — [tdk@null.net](mailto:tdk@null.net)
* 📨 **Telegram** — [@smail_ios](https://t.me/smail_ios)

Issues / PRs that don't need a private discussion are welcome on GitHub.

---

## License

See [`LICENSE`](LICENSE).
