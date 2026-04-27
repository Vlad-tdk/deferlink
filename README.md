<div align="center">

# DeferLink

**Self-hosted mobile attribution. Deferred deep linking, cloaking, SKAdNetwork 4.0 and Facebook CAPI — one stack, full data ownership.**

[![iOS](https://img.shields.io/badge/iOS-14.0%2B-000000?logo=apple&logoColor=white)](https://developer.apple.com/ios/)
[![Swift](https://img.shields.io/badge/Swift-5.9-F05138?logo=swift&logoColor=white)](https://swift.org)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![SKAdNetwork](https://img.shields.io/badge/SKAdNetwork-4.0-1d72b8)](https://developer.apple.com/documentation/storekit/skadnetwork)
[![License](https://img.shields.io/badge/license-See%20LICENSE-lightgrey)](LICENSE)

[Quick start](#-quick-start) · [Architecture](#-architecture) · [Modules](#-module-map) · [Docs](doc/en/) · [Русский](README_RU.md)

</div>

---

## Why DeferLink

A drop-in replacement for AppsFlyer / Adjust / Branch — **without the $30k MRR contract** and without sending your install funnel to a third party.

- **Deferred deep linking** that actually works on iOS 17 — clipboard, shared cookie, DeviceCheck, fingerprint.
- **Cloaking engine** with Bayesian scoring — bots, ad reviewers and scrapers see what they should see.
- **SKAdNetwork 4.0** end-to-end — 6-bit CV, PB1/2/3 postback parsing, Apple ECDSA verification.
- **Facebook Conversions API** with deduplication and exponential retries.
- **AppsFlyer-compatible event taxonomy** — `af_purchase`, `af_complete_registration`, funnels, cohort revenue.
- **Single SQLite file. One Python process. One Swift package.** Runs on a $5 VPS.

---

## What it does

| Capability | What you get |
|---|---|
| **Deferred deep linking** | Click ad → install → first launch lands on the *correct* promo screen. No paste, no manual codes. |
| **4-tier matching** | Clipboard token (~100 %) → SFSafariViewController shared cookie (~99 %) → Apple DeviceCheck (~97 %) → fingerprint (60–90 %). |
| **Cloaking engine** | IP / ASN / UA / behavioural detection of bots, ad reviewers, scrapers. SEO-page or compliant-page response per visitor type. |
| **SKAdNetwork 4.0** | 6-bit CV scheme `[revenue:3][engagement:2][flag:1]`, PB1/PB2/PB3 postbacks, Apple ECDSA signature verification. |
| **Facebook CAPI** | Auto-forward of SKAN postbacks and SDK events to Meta, with dedup and retry. |
| **Event tracking** | AppsFlyer-style standard events, funnels, cohort revenue, custom properties. |

---

## Quick start

> **Prereqs:** Python 3.10+, Xcode 15+, iOS 14.0+ simulator or device.

### 1 · Run the backend

```bash
git clone https://github.com/Vlad-tdk/deferlink.git
cd deferlink

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python run.py
```

Server is up on `http://localhost:8000`. Sanity check:

```bash
curl http://localhost:8000/api/v1/health/quick
# {"status":"ok"}
```

### 2 · Add the iOS SDK

In Xcode → **File → Add Package Dependencies…** → URL of your `DeferLinkSDK` fork, or drag the local `DeferLinkSDK/` folder as a Swift package.

```swift
import DeferLinkSDK

@main
struct MyApp: App {
    init() {
        DeferLink.configure(
            baseURL:      "https://api.your-domain.com",
            appURLScheme: "myapp",
            debugLogging: true
        )

        DeferLink.shared.resolveOnFirstLaunch { result in
            if let promoId = result?.promoId {
                // route to /promo/<promoId>
            }
        }
    }

    var body: some Scene { WindowGroup { ContentView() } }
}
```

```swift
// SceneDelegate.swift
func scene(_ scene: UIScene, openURLContexts URLContexts: Set<UIOpenURLContext>) {
    URLContexts.forEach { DeferLink.shared.handleOpenURL($0.url) }
}
```

### 3 · Track events (optional)

```swift
DeferLink.shared.logEvent(.purchase(9.99, currency: "USD"))
DeferLink.shared.logEvent("af_complete_registration",
                          properties: ["method": "email"])
DeferLink.shared.enableSKAdNetwork(appId: "1234567890")
```

### 4 · Try it locally

A full SwiftUI test harness lives in `DeferLinkTestApp/`. It drives every endpoint and runs deterministic seed → resolve scenarios. Open `DeferLinkTestApp.xcodeproj`, point `NetworkManager.baseURL` at your backend (`http://127.0.0.1:8000` for the iOS Simulator), and tap **Run All Tests**.

> Detailed install / run / test guide → [`doc/en/install-and-test.md`](doc/en/install-and-test.md)

---

## Architecture

```
                    ┌─────────────────────────────────────────────┐
   ad click   ──►   │  GET /dl?promo_id=…&domain=…                 │
                    │     │  cloaking engine                        │
                    │     ├── bot / ad reviewer  → SEO_PAGE         │
                    │     └── real user          → /escape          │
                    │                  │                            │
                    │                  └─► clipboard write          │
                    │                       + redirect to App Store │
                    └─────────────────────────────────────────────┘
                                       │
                            user installs and opens app
                                       ▼
                    ┌─────────────────────────────────────────────┐
   first launch ─►  │  POST /resolve                                │
                    │     ├── tier 1  clipboard_token               │
                    │     ├── tier 2  safari shared cookie          │
                    │     ├── tier 3  Apple DeviceCheck             │
                    │     └── tier 4  fingerprint (tz, locale, …)   │
                    │  → returns promo_id, session_id, match_method │
                    └─────────────────────────────────────────────┘
                                       │
                    ┌─────────────────────────────────────────────┐
   in-app   ─►      │  POST /api/v1/events/batch                    │
   events           │     • dedup by event_id                       │
                    │     • forward to Facebook CAPI                │
                    │  Apple postback → /api/v1/skadnetwork/postback│
                    │     • parse + verify ECDSA + decode CV        │
                    │     • forward to Facebook CAPI                │
                    └─────────────────────────────────────────────┘
```

> Detailed walkthrough — module boundaries, threading model, DB schema → [`doc/en/architecture.md`](doc/en/architecture.md)

---

## Module map

| Subsystem | Code | Docs |
|---|---|---|
| HTTP API surface | `app/api/`, `app/main.py` | [`api-reference.md`](doc/en/api-reference.md) |
| Deferred deep links | `app/deeplink_handler.py`, `app/core/intelligent_matcher.py`, `app/core/safari_escape.py` | [`backend.md`](doc/en/backend.md) |
| Cloaking | `app/core/cloaking/` | [`cloaking.md`](doc/en/cloaking.md) |
| SKAdNetwork | `app/core/skadnetwork/` | [`skadnetwork.md`](doc/en/skadnetwork.md) |
| Facebook CAPI | `app/core/capi/` | [`capi.md`](doc/en/capi.md) |
| iOS SDK | `DeferLinkSDK/Sources/DeferLinkSDK/` | [`sdk-ios.md`](doc/en/sdk-ios.md) |
| Install · run · test | — | [`install-and-test.md`](doc/en/install-and-test.md) |

> 🇷Russian mirror: [`doc/ru/`](doc/ru/) · [`README_RU.md`](README_RU.md)

---

## Configuration cheat-sheet

All settings come from environment variables — full list in `app/config.py`.

| Variable | Default | Notes |
|---|---|---|
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8000` | Bind. iOS Simulator → `127.0.0.1`. |
| `DATABASE_PATH` | `data/deeplinks.db` | SQLite file. |
| `DEFAULT_TTL_HOURS` | `48` | Browser-session lifetime before cleanup. |
| `SECRET_KEY` | dev-secret | **Change in prod**, ≥32 chars. |
| `ENVIRONMENT` | `development` | `production` enables strict validation. |
| `DEVICECHECK_ENABLED` | `false` | Apple DeviceCheck server-side verification. |
| `DEVICECHECK_TEAM_ID` / `_KEY_ID` / `_KEY_PATH` | — | Apple Developer creds, `.p8` file. |
| `APP_URL_SCHEME` | `deferlink` | Must match SDK `appURLScheme` and `Info.plist`. |
| `CAPI_RETRY_INTERVAL_SECONDS` | `300` | Background CAPI retry tick. |
| `LOG_LEVEL` | `INFO` | `DEBUG` enables `uvicorn --reload`. |

> Production checklist → [`install-and-test.md`](doc/en/install-and-test.md#4-production-checklist)

---

## Tests

```bash
pytest                                  # all backend tests
pytest tests/test_deeplink_handler.py   # one module
pytest -k capi -v                       # by keyword
```

For the iOS SDK and the test-harness app, open `DeferLinkTestApp.xcodeproj` in Xcode and run the bundled test plan — full instructions in [`install-and-test.md`](doc/en/install-and-test.md#testing-the-ios-sdk).

---

## Status

| | |
|---|---|
| **iOS SDK version** | `1.0.0` (`DeferLinkSDKInfo.version`) |
| **CV schema** | `rev3_eng2_flag1` — stable wire contract, never breaks |
| **Server** | stateless workers + SQLite (Postgres on roadmap) |
| **Min iOS** | 14.0 (soft fallbacks for 15.4 / 16.1 SKAN APIs) |

---

## Cooperation, integrations, custom builds

For commercial integrations, ad-network adapters, custom CV schemas, on-prem deployment help — or anything not covered by the docs:

<div align="center">

**Email** — [tdk@null.net](mailto:tdk@null.net) &nbsp;·&nbsp; 📨 **Telegram** — [@smail_ios](https://t.me/smail_ios)

</div>

Issues and PRs that don't need a private discussion are welcome on GitHub.

---

## License

See [`LICENSE`](LICENSE).

<div align="center">

<sub>Built for indie devs and small studios who want to keep their attribution data.</sub>

</div>
