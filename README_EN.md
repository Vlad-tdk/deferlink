<div align="center">

# DeferLink

**Self-hosted deferred deep linking — no dependency on Branch, AppsFlyer, or Firebase**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![iOS](https://img.shields.io/badge/iOS-15+-000000?logo=apple&logoColor=white)](https://developer.apple.com)
[![Swift](https://img.shields.io/badge/Swift-5.9-FA7343?logo=swift&logoColor=white)](https://swift.org)
[![Event Tracking](https://img.shields.io/badge/Event_Tracking-Built--in-6c5ce7)](https://github.com/your/deferlink)
[![License](https://img.shields.io/badge/License-MIT-blue)](LICENSE)

[Quick Start](#quick-start) · [How It Works](#how-it-works) · [iOS SDK](#ios-sdk) · [Event Tracking](#event-tracking) · [API Reference](#api-reference) · [Configuration](#configuration)

</div>

---

## What It Is

DeferLink solves a classic mobile marketing challenge: a user clicks an ad, lands in the App Store, installs the app — and after installation the app **remembers** where the user came from and where they wanted to go.

Unlike SaaS solutions (Branch.io, AppsFlyer, Firebase Dynamic Links), DeferLink **runs on your own server**: data never leaves your infrastructure, there are no event caps, and no monthly subscription fees.

```
User                      Server                    App
  │                          │                        │
  │  Click ad                │                        │
  │─────────────────────────>│                        │
  │                          │  Create session        │
  │                          │  (fingerprint+cookie)  │
  │  App Store → Install     │                        │
  │                          │                        │
  │                          │          First launch  │
  │                          │<───────────────────────│
  │                          │  Find session          │
  │                          │───────────────────────>│
  │                          │  promoId / deep link   │
```

---

## Key Features

- **4-tier matching** — from 100% accuracy (clipboard token) to intelligent fingerprinting
- **IAB Detection** — automatically identifies Facebook / Instagram / TikTok in-app browsers and applies an escape strategy
- **Safari Escape** — clipboard handoff via `execCommand` in WKWebView without a user gesture
- **Apple DeviceCheck** — optional device verification through Apple's API without ATT / IDFA
- **SFSafariViewController** — shared cookie jar with Safari for high-accuracy matching
- **Built-in Event Tracking** — AppsFlyer-style analytics with offline queue and attribution auto-stamping; no third-party SDK required
- **Self-hosted** — SQLite out of the box, easy migration to PostgreSQL
- **iOS Swift Package** — 3 lines of code to integrate

---

## How It Works

### Multi-Tier Matching

On the first app launch the SDK checks signals sequentially from most to least accurate — the first successful tier short-circuits the chain:

| Tier | Method | Accuracy | When It Works |
|:----:|--------|:--------:|---------------|
| **1** | Clipboard token | **100%** | User came from the Facebook / Instagram IAB |
| **2** | Safari cookie | **~99%** | Link was opened in real Safari |
| **3** | Apple DeviceCheck | **~97%** | Subsequent launch; token already bound to session |
| **4** | Fingerprint | **60–90%** | Timezone + screen + language + device model |

---

### Tier 1 — Clipboard Handoff (Facebook / Instagram IAB)

Facebook and Instagram open links in an embedded browser (WKWebView) where DeviceCheck is unavailable. DeferLink works around this with the following trick:

```
1. User clicks ad → Facebook IAB opens /dl
2. Server detects FBAN in User-Agent → returns an escape page instead of a redirect
3. JavaScript: document.execCommand('copy')
   ─────────────────────────────────────────
   In WKWebView, execCommand works WITHOUT a user gesture,
   unlike navigator.clipboard.writeText() in Safari.
   ─────────────────────────────────────────
   The clipboard now contains: "deferlink:<session_id>"
4. After 400 ms → redirect to the App Store
5. User installs the app
6. App: UIPasteboard.general.string → "deferlink:<session_id>"
7. POST /resolve with clipboard_token → 100% match
```

---

### Tier 2 — SFSafariViewController Cookie

If the link is opened in real Safari, the server sets a cookie. On first launch the app silently opens `SFSafariViewController` — it shares the cookie jar with Safari:

```
App first launch
  → SFSafariViewController (isHidden=true)
  → GET /safari-resolve
  → Server reads dl_session_id cookie
  → redirect: myapp://resolved?session_id=<uuid>
  → SceneDelegate.scene(_:openURLContexts:)
  → DeferLink.shared.handleOpenURL(url)
  → Match without fingerprinting
```

---

### Tier 4 — IntelligentMatcher (Fingerprint)

When Tiers 1–3 are unavailable, the algorithm computes a weighted score from five signals:

```python
weights = {
    'timezone':          0.35,   # highly stable
    'screen_dimensions': 0.25,   # precise characteristic
    'language':          0.20,   # stable signal
    'device_model':      0.15,   # fuzzy matching
    'user_agent':        0.05,   # low reliability
}
```

The algorithm accounts for equivalent timezones (Moscow ≈ Volgograd), a ±60 px screen tolerance (iOS system elements), related locales (en_US ≈ en_GB), and session timing patterns.

---

## Quick Start

### Server

```bash
git clone https://github.com/your/deferlink && cd deferlink

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload --port 8000
```

The server starts at `http://localhost:8000`.  
Swagger UI: `http://localhost:8000/docs`

### Ad Link

```
https://api.myapp.com/dl?promo_id=SUMMER24&domain=myapp.com
```

Additional parameters improve Tier 4 accuracy — collect them from your landing page via JavaScript:

```javascript
const params = new URLSearchParams({
    promo_id:    "SUMMER24",
    domain:      "myapp.com",
    timezone:    Intl.DateTimeFormat().resolvedOptions().timeZone,
    language:    navigator.language,
    screen_size: `${screen.width}x${screen.height}`,
});
const link = `https://api.myapp.com/dl?${params}`;
```

---

## iOS SDK

### Installation

**Swift Package Manager** — in Xcode:

`File → Add Package Dependencies → Add Local` → select the `DeferLinkSDK` folder

Or in `Package.swift`:
```swift
.package(path: "../DeferLinkSDK")
```

### Xcode Setup

1. **Signing & Capabilities → + Capability → DeviceCheck** (for Tier 3, on a real device)
2. **Info.plist → URL Types** — add a URL scheme:
```xml
<key>CFBundleURLSchemes</key>
<array><string>myapp</string></array>
```

### Integration

**AppDelegate.swift:**
```swift
import DeferLinkSDK

func application(_ application: UIApplication,
                 didFinishLaunchingWithOptions launchOptions: [...]) -> Bool {

    // 1. Configure
    DeferLink.configure(
        baseURL: "https://api.myapp.com",
        appURLScheme: "myapp"
    )

    // 2. Resolve on first launch
    DeferLink.shared.resolveOnFirstLaunch { result in
        guard let result = result else { return }

        print("method: \(result.matchMethod?.rawValue ?? "-")")

        switch result.promoId {
        case "summer24":  AppRouter.showSummerPromo()
        case "referral":  AppRouter.showReferral(code: result.domain)
        default:          break
        }
    }

    return true
}

func application(_ app: UIApplication, open url: URL, options: [...]) -> Bool {
    DeferLink.shared.handleOpenURL(url)    // 3. URL handling
}
```

**SceneDelegate.swift:**
```swift
import DeferLinkSDK

func scene(_ scene: UIScene, openURLContexts contexts: Set<UIOpenURLContext>) {
    if let url = contexts.first?.url {
        DeferLink.shared.handleOpenURL(url)
    }
}
```

### async / await

```swift
let result = await DeferLink.shared.resolve()

if let result, result.matched {
    print("promoId:     \(result.promoId ?? "-")")
    print("matchMethod: \(result.matchMethod?.rawValue ?? "-")")
}
```

### DeferLinkResult

```swift
public struct DeferLinkResult {
    public let matched:     Bool
    public let promoId:     String?      // promo_id parameter from the link
    public let domain:      String?      // domain parameter
    public let sessionId:   String?
    public let appURL:      String?      // app_scheme parameter
    public let matchMethod: MatchMethod?
    public let message:     String?

    public enum MatchMethod: String {
        case clipboard    = "clipboard"
        case safariCookie = "safari_cookie"
        case deviceCheck  = "device_check"
        case fingerprint  = "fingerprint"
    }
}
```

### Full Configuration

```swift
DeferLink.configure(with: DeferLinkConfiguration(
    baseURL:              "https://api.myapp.com",
    appURLScheme:         "myapp",
    clipboardTokenPrefix: "deferlink",   // must match CLIPBOARD_TOKEN_PREFIX
    safariResolveTimeout: 3.0,           // SFSafariViewController timeout (seconds)
    networkTimeout:       10.0,
    debugLogging:         true           // os.log, development only
))
```

---

## Event Tracking

DeferLink ships a built-in AppsFlyer-style event tracking system. No third-party analytics SDK is required. After `resolveOnFirstLaunch` completes, every event automatically carries the attribution context (`session_id`, `promo_id`) — zero extra developer effort.

### Overview

| Capability | Detail |
|------------|--------|
| Attribution auto-stamping | `session_id` + `promo_id` attached to every event |
| Offline-first queue | In-memory buffer with JSON persistence to Application Support |
| Client-side deduplication | Each event carries a UUID (`event_id`) |
| Server-side deduplication | `INSERT OR IGNORE` on `event_id` |
| Standard event names | 18 pre-defined `DLEventName` constants |
| Standard property keys | 10 pre-defined `DLEventParam` constants |

---

### iOS SDK API

```swift
// Set user ID once after authentication
DeferLink.shared.setUserId("user_42")

// Log a standard event
DeferLink.shared.logEvent(DLEventName.contentView, properties: [
    DLEventParam.contentId: "article_42",
    DLEventParam.contentType: "blog_post"
])

// Log a purchase — revenue is tracked automatically
DeferLink.shared.logEvent(
    DLEventName.purchase,
    revenue: 29.99,
    currency: "USD",
    properties: [DLEventParam.orderId: "order_789"]
)

// Convenience factories
DeferLink.shared.logEvent(.purchase(29.99, currency: "EUR"))
DeferLink.shared.logEvent(.registration(method: "apple"))
DeferLink.shared.logEvent(.subscribe(9.99))

// Manual flush (e.g. before a background task completes)
DeferLink.shared.flushEvents()
```

---

### Standard Event Names

| Constant | Raw value | Description |
|----------|-----------|-------------|
| `DLEventName.install` | `af_install` | App installed |
| `DLEventName.launch` | `af_launch` | App launched |
| `DLEventName.completeRegistration` | `af_complete_registration` | User registration complete |
| `DLEventName.login` | `af_login` | User logged in |
| `DLEventName.purchase` | `af_purchase` | Purchase completed |
| `DLEventName.addToCart` | `af_add_to_cart` | Item added to cart |
| `DLEventName.addToWishlist` | `af_add_to_wishlist` | Item added to wishlist |
| `DLEventName.initiatedCheckout` | `af_initiated_checkout` | Checkout started |
| `DLEventName.contentView` | `af_content_view` | Content viewed |
| `DLEventName.search` | `af_search` | Search performed |
| `DLEventName.subscribe` | `af_subscribe` | Subscription started |
| `DLEventName.levelAchieved` | `af_level_achieved` | Game level reached |
| `DLEventName.tutorialCompletion` | `af_tutorial_completion` | Onboarding/tutorial done |
| `DLEventName.rate` | `af_rate` | Rating submitted |
| `DLEventName.share` | `af_share` | Content shared |
| `DLEventName.invite` | `af_invite` | Invite sent |
| `DLEventName.reEngage` | `af_re_engage` | Re-engagement |
| `DLEventName.update` | `af_update` | App updated |

---

### Standard Property Keys (DLEventParam)

| Constant | Raw value | Description |
|----------|-----------|-------------|
| `DLEventParam.contentId` | `af_content_id` | ID of the viewed/purchased content |
| `DLEventParam.contentType` | `af_content_type` | Content category or type |
| `DLEventParam.revenue` | `af_revenue` | Revenue amount |
| `DLEventParam.price` | `af_price` | Unit price |
| `DLEventParam.quantity` | `af_quantity` | Item quantity |
| `DLEventParam.orderId` | `af_order_id` | Order or transaction ID |
| `DLEventParam.level` | `af_level` | Game level number |
| `DLEventParam.score` | `af_score` | Score value |
| `DLEventParam.searchString` | `af_search_string` | Search query text |
| `DLEventParam.registrationMethod` | `af_registration_method` | Registration method (email, apple, google…) |

---

### DeferLinkEvent Struct

```swift
public struct DeferLinkEvent: Codable {
    /// Globally unique event identifier — used for client- and server-side deduplication
    public let eventId: String           // UUID v4

    /// Standard event name (e.g. "af_purchase") or a custom string
    public let eventName: String

    /// ISO 8601 timestamp set at the moment logEvent() is called
    public let timestamp: String

    /// Session ID from resolveOnFirstLaunch — auto-stamped, nil if resolve not yet called
    public let sessionId: String?

    /// Promo/campaign ID from the originating deep link — auto-stamped
    public let promoId: String?

    /// Developer-supplied user ID set via setUserId()
    public let userId: String?

    /// Revenue amount for purchase events
    public let revenue: Double?

    /// ISO 4217 currency code (e.g. "USD", "EUR")
    public let currency: String?

    /// Arbitrary key-value properties (values must be JSON-serialisable)
    public let properties: [String: AnyCodable]?
}
```

---

### Offline Queue Behavior

The event system is offline-first and resilient to network failures:

| Behavior | Detail |
|----------|--------|
| In-memory buffer | Flushed every **15 seconds** or when **20 events** accumulate |
| Persistence path | `ApplicationSupport/com.deferlink.sdk.event_queue.json` |
| Max persisted events | **500** — oldest events dropped (FIFO) when the cap is hit |
| Auto-flush | On `UIApplication.willResignActiveNotification` |
| Auto-retry | On `UIApplication.didBecomeActiveNotification` |
| Retry strategy | Exponential backoff: **1 s → 2 s → 4 s** (max 3 attempts), then persisted |
| Server-side dedup | `INSERT OR IGNORE` on `event_id` UUID |

---

### Attribution Auto-Stamping

After `resolveOnFirstLaunch` resolves successfully, `session_id` and `promo_id` are stored in the SDK and automatically attached to every subsequent event. No additional code is required.

```
resolveOnFirstLaunch
       │
       └── stores session_id + promo_id
                  │
                  └── logEvent(...)
                         │
                         └── event.session_id = stored session_id  ✓
                             event.promo_id   = stored promo_id    ✓
```

---

### Complete Integration Flow

```swift
// AppDelegate.swift

DeferLink.configure(baseURL: "https://api.myapp.com", appURLScheme: "myapp")

DeferLink.shared.resolveOnFirstLaunch { result in
    // Attribution is now stamped on all events automatically
    if let promoId = result?.promoId {
        DeferLink.shared.logEvent(DLEventName.install, properties: ["promo_id": promoId])
    }
}

// After login
DeferLink.shared.setUserId(currentUser.id)
DeferLink.shared.logEvent(.registration(method: "email"))

// In your purchase flow
DeferLink.shared.logEvent(
    DLEventName.purchase,
    revenue: 29.99,
    currency: "USD",
    properties: [
        DLEventParam.orderId: "ORD-1234",
        DLEventParam.contentId: "pro_annual",
        "discount_applied": true
    ]
)
```

---

### Event API Reference

#### `POST /api/v1/events` — Log a Single Event

**Request:**
```json
{
  "event_id":   "550e8400-e29b-41d4-a716-446655440000",
  "event_name": "af_purchase",
  "timestamp":  "2025-06-15T14:23:00Z",
  "session_id": "a1b2c3d4-0000-0000-0000-112233445566",
  "promo_id":   "SUMMER24",
  "user_id":    "user_42",
  "revenue":    29.99,
  "currency":   "USD",
  "properties": {
    "af_order_id":    "ORD-1234",
    "af_content_id":  "pro_annual"
  }
}
```

**Response:**
```json
{
  "success": true,
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "duplicate": false
}
```

---

#### `POST /api/v1/events/batch` — Log a Batch of Events

**Request:**
```json
{
  "events": [
    {
      "event_id":   "aaaaaaaa-0000-0000-0000-000000000001",
      "event_name": "af_content_view",
      "timestamp":  "2025-06-15T14:20:00Z",
      "session_id": "a1b2c3d4-0000-0000-0000-112233445566",
      "promo_id":   "SUMMER24",
      "user_id":    "user_42",
      "properties": { "af_content_id": "article_7", "af_content_type": "blog_post" }
    },
    {
      "event_id":   "aaaaaaaa-0000-0000-0000-000000000002",
      "event_name": "af_add_to_cart",
      "timestamp":  "2025-06-15T14:21:30Z",
      "session_id": "a1b2c3d4-0000-0000-0000-112233445566",
      "promo_id":   "SUMMER24",
      "user_id":    "user_42",
      "properties": { "af_content_id": "pro_annual", "af_price": 29.99 }
    },
    {
      "event_id":   "aaaaaaaa-0000-0000-0000-000000000003",
      "event_name": "af_purchase",
      "timestamp":  "2025-06-15T14:23:00Z",
      "session_id": "a1b2c3d4-0000-0000-0000-112233445566",
      "promo_id":   "SUMMER24",
      "user_id":    "user_42",
      "revenue":    29.99,
      "currency":   "USD",
      "properties": { "af_order_id": "ORD-1234", "af_content_id": "pro_annual" }
    }
  ]
}
```

**Response:**
```json
{
  "success":    true,
  "inserted":   2,
  "duplicate":  1,
  "failed":     0
}
```

---

#### `GET /api/v1/events/stats` — Aggregated Statistics

**Request:**
```
GET /api/v1/events/stats?start=2025-01-01T00:00:00Z&end=2025-12-31T23:59:59Z&promo_id=SUMMER24
```

**Response:**
```json
{
  "total_events":    15240,
  "unique_users":    3812,
  "unique_sessions": 4100,
  "total_revenue":   98432.50,
  "revenue_events":  1847,
  "top_events": [
    { "event_name": "af_content_view", "count": 6321 },
    { "event_name": "af_purchase",     "count": 1847 },
    { "event_name": "af_add_to_cart",  "count": 2910 },
    { "event_name": "af_search",       "count": 1540 },
    { "event_name": "af_login",        "count": 2622 }
  ],
  "revenue_by_currency": [
    { "currency": "USD", "total_revenue": 75210.00, "count": 1401 },
    { "currency": "EUR", "total_revenue": 23222.50, "count": 446  }
  ]
}
```

---

#### `GET /api/v1/events/funnel` — Conversion Funnel

**Request:**
```
GET /api/v1/events/funnel?steps=af_content_view&steps=af_add_to_cart&steps=af_purchase
```

**Response:**
```json
{
  "funnel": [
    {
      "step":              1,
      "event_name":        "af_content_view",
      "users":             6321,
      "conversion_prev":   null,
      "conversion_total":  1.0
    },
    {
      "step":              2,
      "event_name":        "af_add_to_cart",
      "users":             2910,
      "conversion_prev":   0.460,
      "conversion_total":  0.460
    },
    {
      "step":              3,
      "event_name":        "af_purchase",
      "users":             1847,
      "conversion_prev":   0.635,
      "conversion_total":  0.292
    }
  ]
}
```

---

#### `GET /api/v1/events/revenue` — Daily Revenue Cohort

**Request:**
```
GET /api/v1/events/revenue?promo_id=SUMMER24&days=30
```

**Response:**
```json
{
  "cohort": [
    {
      "day":             "2025-06-01",
      "promo_id":        "SUMMER24",
      "currency":        "USD",
      "purchases":       62,
      "revenue":         1849.38,
      "avg_order_value": 29.83
    },
    {
      "day":             "2025-06-02",
      "promo_id":        "SUMMER24",
      "currency":        "USD",
      "purchases":       74,
      "revenue":         2207.26,
      "avg_order_value": 29.83
    }
  ]
}
```

---

#### `GET /api/v1/events/standard-events` — List Standard Events

**Request:**
```
GET /api/v1/events/standard-events
```

**Response:**
```json
{
  "standard_events": [
    "af_install",
    "af_launch",
    "af_complete_registration",
    "af_login",
    "af_purchase",
    "af_add_to_cart",
    "af_add_to_wishlist",
    "af_initiated_checkout",
    "af_content_view",
    "af_search",
    "af_subscribe",
    "af_level_achieved",
    "af_tutorial_completion",
    "af_rate",
    "af_share",
    "af_invite",
    "af_re_engage",
    "af_update"
  ]
}
```

---

## API Reference

### `GET /dl` — Create a Session

The primary entry point for ad links.

| Parameter | Required | Description |
|-----------|:--------:|-------------|
| `promo_id` | Yes | Campaign / promotion ID |
| `domain` | Yes | Domain for identification |
| `timezone` | No | IANA timezone (`Europe/London`) |
| `language` | No | Language code (`en_US`) |
| `screen_size` | No | Screen resolution (`390x844`) |
| `model` | No | Device model |
| `ttl` | No | Session lifetime in hours (default: 48) |

**Behavior by User-Agent:**

| Browser | Response |
|---------|----------|
| Safari (iOS) | `302` → App Store + `Set-Cookie: dl_session_id` |
| Facebook / Instagram IAB | `200` → HTML escape page (clipboard + redirect) |
| TikTok / WeChat IAB | `302` → App Store directly |
| Desktop | `200` → HTML page with instructions |

---

### `POST /resolve` — Resolve a Deep Link

Called by the iOS SDK on the first app launch.

**Request body:**
```json
{
  "fingerprint": {
    "model":                    "iPhone15,2",
    "language":                 "en_US",
    "timezone":                 "America/New_York",
    "user_agent":               "MyApp/1.0 (iOS 17.0; iPhone15,2)",
    "screen_width":             390,
    "screen_height":            844,
    "platform":                 "iOS",
    "app_version":              "2.1.0",
    "idfv":                     "12345678-1234-1234-1234-123456789ABC",
    "clipboard_token":          "deferlink:550e8400-e29b-41d4-a716-446655440000",
    "device_check_token":       "base64encodedtoken==",
    "safari_cookie_session_id": "550e8400-e29b-41d4-a716-446655440000",
    "is_first_launch":          true
  },
  "app_scheme":   "myapp://promo/SUMMER24",
  "fallback_url": "https://apps.apple.com"
}
```

**Response (matched):**
```json
{
  "success":      true,
  "matched":      true,
  "promo_id":     "SUMMER24",
  "domain":       "myapp.com",
  "session_id":   "550e8400-e29b-41d4-a716-446655440000",
  "app_url":      "myapp://promo/SUMMER24",
  "match_method": "clipboard",
  "message":      "Session resolved successfully"
}
```

---

### `GET /safari-resolve` — Cookie Resolve

Called by the SDK through a hidden `SFSafariViewController`. Reads the cookie and redirects back into the app:

```
Found:     → myapp://resolved?session_id=<uuid>
Not found: → myapp://resolved?session_id=none
```

---

### `GET /api/v1/health`

```json
{ "status": "healthy", "database": "ok", "version": "1.0.0" }
```

### `GET /api/v1/stats`

```json
{
  "total_sessions":     1842,
  "active_sessions":    234,
  "resolved_sessions":  1421,
  "success_rate":       77.1,
  "average_confidence": 0.879,
  "sessions_last_hour": 48
}
```

---

## Configuration

```bash
# ── Security (required in production) ─────────────────────────────────────────
SECRET_KEY=                    # min 32 characters
                               # python3 -c "import secrets; print(secrets.token_urlsafe(32))"
ENVIRONMENT=production         # development | production
CORS_ORIGINS=https://myapp.com
COOKIE_SECURE=true
COOKIE_SAMESITE=lax

# ── Database ───────────────────────────────────────────────────────────────────
DATABASE_PATH=data/deeplinks.db

# ── Application ────────────────────────────────────────────────────────────────
APP_STORE_ID=1234567890        # numeric App Store ID
APP_NAME=MyApp                 # shown on the escape page
APP_URL_SCHEME=myapp           # URL scheme (Info.plist)
CLIPBOARD_TOKEN_PREFIX=deferlink

# ── Sessions ───────────────────────────────────────────────────────────────────
DEFAULT_TTL_HOURS=48
CLEANUP_INTERVAL_MINUTES=30

# ── API ────────────────────────────────────────────────────────────────────────
API_HOST=0.0.0.0
API_PORT=8000
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60

# ── Apple DeviceCheck (Tier 3) ─────────────────────────────────────────────────
DEVICECHECK_ENABLED=true
DEVICECHECK_TEAM_ID=ABCDE12345
DEVICECHECK_KEY_ID=ABC123DEF456
DEVICECHECK_KEY_PATH=/secrets/AuthKey_ABC123DEF456.p8
DEVICECHECK_SANDBOX=false      # true for dev / staging

# ── Analytics ──────────────────────────────────────────────────────────────────
ENABLE_ANALYTICS=true
AUTO_OPTIMIZE_WEIGHTS=false    # auto-optimize fingerprint weights
LOG_LEVEL=INFO
```

---

## Architecture

```
deferlink/
├── app/
│   ├── main.py                    FastAPI app: /dl, /resolve, /safari-resolve
│   ├── config.py                  Environment-based configuration
│   ├── models.py                  Pydantic models (FingerprintData, ResolveResponse)
│   ├── deeplink_handler.py        4-tier matching orchestrator
│   ├── database.py                SQLite manager
│   ├── core/
│   │   ├── intelligent_matcher.py Fingerprint matching — Tier 4
│   │   ├── iab_detector.py        IAB detection + escape strategy
│   │   ├── safari_escape.py       HTML escape page (clipboard + redirect)
│   │   ├── devicecheck.py         Apple DeviceCheck API client — Tier 3
│   │   └── event_tracker.py       Event storage & analytics (insert, funnel, cohort)
│   ├── api/
│   │   ├── deeplinks.py           POST /api/v1/resolve
│   │   ├── stats.py               GET  /api/v1/stats
│   │   ├── health.py              GET  /api/v1/health
│   │   └── events.py              POST /events, /batch · GET /stats, /funnel, /revenue
│   └── migrations/
│       ├── add_devicecheck_fields.py
│       └── add_events_table.py    user_events table (15 columns)
│
├── DeferLinkSDK/                  iOS Swift Package
│   ├── Package.swift              swift-tools-version: 5.9, iOS 15+
│   └── Sources/DeferLinkSDK/
│       ├── DeferLink.swift            Public facade (@MainActor singleton)
│       ├── DeferLinkConfiguration.swift
│       ├── DeferLinkLogger.swift      os.log wrapper
│       ├── Models/DeferLinkModels.swift
│       ├── Core/
│       │   ├── DeviceInfoCollector.swift  Hardware, timezone, language, screen
│       │   ├── FingerprintCollector.swift Clipboard + DeviceCheck + assembly
│       │   └── DeviceCheckManager.swift   DCDevice token + 1 h cache
│       ├── Network/DeferLinkClient.swift  POST /resolve, GET /safari-resolve
│       └── Events/
│           ├── DeferLinkEvent.swift       Event model + DLEventName + DLEventParam + AnyCodable
│           ├── EventQueue.swift           Offline-first persistence (Application Support)
│           └── EventTracker.swift         Batching + retry + app lifecycle observer
│
└── DeferLinkTestApp/              Sample SDK integration (SwiftUI)
```

---

## Security

- **No IDFA / ATT** — the system does not use advertising identifiers
- **Clipboard is cleared** after reading the token (`UIPasteboard.general.string = ""`)
- **DeviceCheck tokens** are stored only as SHA-256 hashes; raw tokens are never persisted
- **Sessions with TTL** — automatic cleanup every 30 minutes
- **Rate limiting** — endpoint protection against brute-force requests
- **Fraud detection** — blocks IPs that generate more than 100 requests per hour

---

## Requirements

| Component | Minimum |
|-----------|---------|
| Python | 3.10+ |
| iOS | 15.0+ |
| Xcode | 15+ |
| SQLite | 3.35+ (bundled with Python) |

---

## License

MIT
