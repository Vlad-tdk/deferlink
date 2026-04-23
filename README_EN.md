<div align="center">

# DeferLink

**Self-hosted deferred deep linking — no dependency on Branch, AppsFlyer, or Firebase**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![iOS](https://img.shields.io/badge/iOS-15+-000000?logo=apple&logoColor=white)](https://developer.apple.com)
[![Swift](https://img.shields.io/badge/Swift-5.9-FA7343?logo=swift&logoColor=white)](https://swift.org)
[![License](https://img.shields.io/badge/License-MIT-blue)](LICENSE)

[Quick Start](#quick-start) · [How It Works](#how-it-works) · [iOS SDK](#ios-sdk) · [Event Tracking](#event-tracking) · [API](#api-reference) · [Configuration](#configuration)

</div>

---

## What Is This

DeferLink solves a classic mobile marketing problem: a user clicks an ad → lands in the App Store → installs the app — and after installation the app **remembers** where the user came from and what they wanted to do.

Unlike SaaS solutions (Branch.io, AppsFlyer, Firebase Dynamic Links), DeferLink **runs on your own server**: no data leaves your infrastructure, no event caps, no monthly bills.

```
User                     Server                    App
  │                         │                        │
  │  Click ad               │                        │
  │────────────────────────>│                        │
  │                         │  Create session        │
  │                         │  (fingerprint+cookie)  │
  │  App Store → Install    │                        │
  │                         │                        │
  │                         │       First launch     │
  │                         │<───────────────────────│
  │                         │  Match session         │
  │                         │───────────────────────>│
  │                         │  promoId / deep link   │
```

---

## Key Features

- **4-tier matching** — from 100% accuracy (clipboard token) to intelligent fingerprinting
- **IAB Detection** — automatically detects Facebook / Instagram / TikTok in-app browsers and applies the right escape strategy
- **Safari Escape** — clipboard handoff via `execCommand` inside WKWebView without requiring a user gesture
- **Apple DeviceCheck** — optional device verification via Apple's API, no ATT / IDFA required
- **SFSafariViewController** — shared Safari cookie jar for high-accuracy matching
- **Event Tracking** — built-in AppsFlyer-style analytics: funnels, revenue cohorts, offline queue
- **Self-hosted** — SQLite out of the box, straightforward migration to PostgreSQL
- **iOS Swift Package** — 3 lines of code to integrate

---

## How It Works

### Multi-Tier Matching

On first app launch the SDK works down a priority chain, stopping at the first successful match:

| Tier | Method | Accuracy | When It Works |
|:----:|--------|:--------:|---------------|
| **1** | Clipboard token | **100%** | User arrived from a Facebook / Instagram in-app browser |
| **2** | Safari cookie | **~99%** | Link was opened in real Safari |
| **3** | Apple DeviceCheck | **~97%** | Device token already linked to a session |
| **4** | Fingerprint | **60–90%** | Timezone + screen + language + device model |

The first successful tier short-circuits the chain — no wasted computation.

---

### Tier 1 — Clipboard Handoff (Facebook / Instagram IAB)

Facebook and Instagram open links in an embedded browser (WKWebView) where DeviceCheck is unavailable. DeferLink exploits a WKWebView quirk:

```
1. User clicks ad → Facebook IAB opens /dl
2. Server detects FBAN in User-Agent → returns escape page instead of redirect
3. JavaScript: document.execCommand('copy')
   ─────────────────────────────────────────────────
   In WKWebView, execCommand works WITHOUT a user gesture,
   unlike navigator.clipboard.writeText() in real Safari.
   ─────────────────────────────────────────────────
   Clipboard is now: "deferlink:<session_id>"
4. After 400ms → redirect to App Store
5. User installs the app
6. App reads: UIPasteboard.general.string → "deferlink:<session_id>"
7. POST /resolve with clipboard_token → 100% match
```

---

### Tier 2 — SFSafariViewController Cookie

When the link is opened in real Safari, the server sets a cookie. On first launch the app invisibly presents an `SFSafariViewController`, which shares its cookie jar with Safari:

```
App first launch
  → SFSafariViewController (isHidden = true)
  → GET /safari-resolve
  → Server reads dl_session_id cookie
  → redirect: myapp://resolved?session_id=<uuid>
  → SceneDelegate.scene(_:openURLContexts:)
  → DeferLink.shared.handleOpenURL(url)
  → Match without any fingerprinting
```

---

### Tier 4 — IntelligentMatcher (Fingerprint)

When Tiers 1–3 are unavailable, the algorithm builds a weighted score from five device signals:

```python
weights = {
    'timezone':          0.35,   # highly stable
    'screen_dimensions': 0.25,   # precise characteristic
    'language':          0.20,   # stable signal
    'device_model':      0.15,   # fuzzy matched
    'user_agent':        0.05,   # lowest reliability
}
```

The algorithm handles equivalent timezones (Moscow ≈ Volgograd), screen tolerance ±60 px (iOS system UI variance), related locales (en_US ≈ en_GB), and session timing patterns.

---

## Quick Start

### Server

```bash
git clone https://github.com/your/deferlink && cd deferlink

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload --port 8000
```

Server starts at `http://localhost:8000`.  
Swagger UI: `http://localhost:8000/docs`

### Ad Link

```
https://api.myapp.com/dl?promo_id=SUMMER24&domain=myapp.com
```

Collect additional parameters on your landing page to improve Tier 4 accuracy:

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

1. **Signing & Capabilities → + Capability → DeviceCheck** (Tier 3, real device only)
2. **Info.plist → URL Types** — add your URL scheme:
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
    DeferLink.shared.handleOpenURL(url)   // 3. URL handling
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
    public let promoId:     String?      // promo_id from the link
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
    clipboardTokenPrefix: "deferlink",   // must match CLIPBOARD_TOKEN_PREFIX on the server
    safariResolveTimeout: 3.0,           // SFSafariViewController timeout in seconds
    networkTimeout:       10.0,
    debugLogging:         true           // os.log output, development only
))
```

---

## Event Tracking

DeferLink includes built-in AppsFlyer-style event tracking — no third-party SDK, no monthly fee, all data in your own database.

After a successful `resolveOnFirstLaunch`, every event is **automatically enriched** with attribution context (`session_id`, `promo_id`). There is nothing extra to configure — the SDK handles it transparently.

### Feature Overview

| Feature | Description |
|---------|-------------|
| 18 standard events | `af_purchase`, `af_install`, `af_subscribe`, and more |
| Custom properties | Up to 50 `[String: Any]` key-value pairs per event |
| Revenue tracking | `revenue` field + ISO 4217 currency |
| Offline queue | Persistent buffer — events survive network loss |
| Deduplication | Client-side UUID, `INSERT OR IGNORE` on the server |
| Funnel analysis | Chronological conversion through an ordered sequence of events |
| Revenue cohorts | Daily revenue broken down by promo campaign |
| Automatic attribution | `session_id` and `promo_id` stamped on every event automatically |

---

### Getting Started with Events

```swift
// After configure + resolveOnFirstLaunch, one line is all you need:
DeferLink.shared.logEvent(DLEventName.contentView)

// With revenue
DeferLink.shared.logEvent(DLEventName.purchase, revenue: 29.99, currency: "USD")

// With custom properties
DeferLink.shared.logEvent(DLEventName.purchase, revenue: 29.99, currency: "USD", properties: [
    DLEventParam.orderId:   "ORD-1234",
    DLEventParam.contentId: "pro_annual"
])
```

---

### Setting the User ID

Call this once after authentication. All subsequent events will carry this identifier, enabling cross-session and cross-device user-level analytics.

```swift
DeferLink.shared.setUserId(currentUser.id)
```

---

### logEvent Overloads

The SDK provides three overloads to cover every scenario:

```swift
// 1. Non-revenue event (view, navigation, interaction)
DeferLink.shared.logEvent(_ eventName: String, properties: [String: Any]? = nil)

// 2. Revenue event (purchase, subscription, in-app purchase)
DeferLink.shared.logEvent(_ eventName: String, revenue: Double, currency: String = "USD",
                           properties: [String: Any]? = nil)

// 3. Pre-built DeferLinkEvent object (maximum control)
DeferLink.shared.logEvent(_ event: DeferLinkEvent)
```

---

### Convenience Factories

The most common events have purpose-built constructors:

```swift
// Purchase
DeferLink.shared.logEvent(.purchase(29.99, currency: "USD", properties: [
    DLEventParam.orderId:   "ORD-1234",
    DLEventParam.contentId: "pro_annual"
]))

// Subscription
DeferLink.shared.logEvent(.subscribe(9.99, currency: "EUR"))

// Registration (method: apple | google | email | phone)
DeferLink.shared.logEvent(.registration(method: "apple"))
```

---

### Complete Lifecycle Example

```swift
// ── AppDelegate.swift ────────────────────────────────────────────────────
import DeferLinkSDK

func application(_ application: UIApplication,
                 didFinishLaunchingWithOptions launchOptions: [...]) -> Bool {

    DeferLink.configure(baseURL: "https://api.myapp.com", appURLScheme: "myapp")

    DeferLink.shared.resolveOnFirstLaunch { result in
        // From this point, session_id and promo_id are automatically
        // attached to all events — nothing else to configure
        guard let result = result else { return }

        DeferLink.shared.logEvent(DLEventName.install, properties: [
            "promo_id":     result.promoId ?? "organic",
            "match_method": result.matchMethod?.rawValue ?? "none"
        ])

        AppRouter.handlePromo(result.promoId)
    }

    return true
}

// ── AuthViewController.swift ─────────────────────────────────────────────
func userDidLogin(_ user: User) {
    DeferLink.shared.setUserId(user.id)              // bind all events to this user
    DeferLink.shared.logEvent(.registration(method: user.authProvider))
}

// ── OnboardingViewController.swift ───────────────────────────────────────
func onboardingDidFinish() {
    DeferLink.shared.logEvent(DLEventName.tutorialCompletion)
}

// ── ProductViewController.swift ──────────────────────────────────────────
override func viewDidAppear(_ animated: Bool) {
    super.viewDidAppear(animated)
    DeferLink.shared.logEvent(DLEventName.contentView, properties: [
        DLEventParam.contentId:   product.id,
        DLEventParam.contentType: "product",
        DLEventParam.price:       product.price
    ])
}

func addToCartTapped() {
    DeferLink.shared.logEvent(DLEventName.addToCart, properties: [
        DLEventParam.contentId: product.id,
        DLEventParam.price:     product.price,
        DLEventParam.quantity:  1
    ])
}

// ── CheckoutViewController.swift ─────────────────────────────────────────
func checkoutInitiated() {
    DeferLink.shared.logEvent(DLEventName.initiatedCheckout, properties: [
        DLEventParam.contentId: cart.primaryItemId,
        DLEventParam.revenue:   cart.total
    ])
}

// ── PaymentViewController.swift ──────────────────────────────────────────
func paymentCompleted(order: Order) {
    DeferLink.shared.logEvent(
        DLEventName.purchase,
        revenue:    order.total,
        currency:   order.currency,
        properties: [
            DLEventParam.orderId:   order.id,
            DLEventParam.contentId: order.planId,
            DLEventParam.quantity:  order.quantity
        ]
    )
}
```

---

### Standard Event Names — DLEventName

| Constant | Value | When to Use |
|----------|-------|-------------|
| `DLEventName.install` | `af_install` | First launch after installation |
| `DLEventName.launch` | `af_launch` | App opened |
| `DLEventName.completeRegistration` | `af_complete_registration` | User finished sign-up |
| `DLEventName.login` | `af_login` | User authenticated |
| `DLEventName.purchase` | `af_purchase` | Purchase completed — use with `revenue` |
| `DLEventName.addToCart` | `af_add_to_cart` | Item added to cart |
| `DLEventName.addToWishlist` | `af_add_to_wishlist` | Item saved to wishlist |
| `DLEventName.initiatedCheckout` | `af_initiated_checkout` | Checkout flow started |
| `DLEventName.contentView` | `af_content_view` | Product / article / screen viewed |
| `DLEventName.search` | `af_search` | User performed a search |
| `DLEventName.subscribe` | `af_subscribe` | Subscription purchased — use with `revenue` |
| `DLEventName.levelAchieved` | `af_level_achieved` | Game level reached |
| `DLEventName.tutorialCompletion` | `af_tutorial_completion` | Onboarding completed |
| `DLEventName.rate` | `af_rate` | App rating submitted |
| `DLEventName.share` | `af_share` | Content shared |
| `DLEventName.invite` | `af_invite` | Referral invite sent |
| `DLEventName.reEngage` | `af_re_engage` | Lapsed user returned |
| `DLEventName.update` | `af_update` | App updated to a new version |

---

### Standard Property Keys — DLEventParam

| Constant | Key | Type | Description |
|----------|-----|:----:|-------------|
| `DLEventParam.contentId` | `af_content_id` | `String` | Product, article, or content ID |
| `DLEventParam.contentType` | `af_content_type` | `String` | Content type (`product`, `article`) |
| `DLEventParam.price` | `af_price` | `Double` | Unit price |
| `DLEventParam.revenue` | `af_revenue` | `Double` | Revenue in properties (mirrors the `revenue` field) |
| `DLEventParam.quantity` | `af_quantity` | `Int` | Number of units |
| `DLEventParam.orderId` | `af_order_id` | `String` | Order identifier |
| `DLEventParam.level` | `af_level` | `Int` | Game level |
| `DLEventParam.score` | `af_score` | `Int` | Score or points |
| `DLEventParam.searchString` | `af_search_string` | `String` | User's search query text |
| `DLEventParam.registrationMethod` | `af_registration_method` | `String` | Sign-up method (`apple`, `google`, `email`) |

---

### DeferLinkEvent Model

```swift
public struct DeferLinkEvent: Codable {
    // ── Identity ────────────────────────────────────────────────────────
    public let eventId:    String   // UUID — deduplication key on the server
    public let eventName:  String   // event name (standard or custom string)
    public let timestamp:  String   // ISO 8601, recorded on the client

    // ── Attribution (auto-populated by SDK after resolve) ────────────────
    public var sessionId:  String?  // session_id from resolveOnFirstLaunch
    public var appUserId:  String?  // your app's user identifier
    public var promoId:    String?  // promo_id from the attribution link

    // ── Revenue ─────────────────────────────────────────────────────────
    public var revenue:    Double?  // monetary amount (purchase / subscribe only)
    public var currency:   String   // ISO 4217, defaults to "USD"

    // ── Custom Properties ────────────────────────────────────────────────
    public var properties: [String: AnyCodable]?  // up to 50 key-value pairs

    // ── Device Context (auto-populated) ─────────────────────────────────
    public var platform:   String   // "iOS"
    public var appVersion: String?  // CFBundleShortVersionString
    public var sdkVersion: String   // DeferLinkSDK version string
}
```

> `AnyCodable` is an SDK-internal type that lets you pass `Bool`, `Int`, `Double`, `String`, `Array`, and nested `[String: Any]` dictionaries inside `properties` without loss of type information.

---

### Offline Queue & Delivery Guarantees

The SDK ensures event delivery even under poor or absent network conditions:

```
Event created
      │
      ▼
 In-memory buffer
 (up to 20 events or 15 seconds, whichever comes first)
      │
      ▼  batch flush
 POST /api/v1/events/batch
      │
 ┌────┴────────────────────────────────────────┐
 │ Success (2xx)                               │ Network error / 5xx
 │ ✓ events delivered                         │
 │                                             ▼
 │                                  Exponential back-off retry
 │                                  attempt 1 → wait  1 s
 │                                  attempt 2 → wait  2 s
 │                                  attempt 3 → wait  4 s
 │                                             │
 │                                             │  After 3 failures
 │                                             ▼
 │                                  Persist to disk
 │                                  ~/ApplicationSupport/
 │                                  com.deferlink.sdk.event_queue.json
 │                                  (max 500 events, FIFO eviction)
 │                                             │
 │                                             ▼  next app session
 │                                  Auto-flush on didBecomeActive
 └─────────────────────────────────────────────┘
```

**Parameters at a glance:**

| Parameter | Value |
|-----------|-------|
| In-memory batch size | 20 events |
| Auto-flush interval | 15 seconds |
| Flush on background | ✓ `willResignActive` |
| Flush on foreground | ✓ `didBecomeActive` |
| Max persisted events | 500 (FIFO eviction when full) |
| Retry strategy | Exponential back-off, max 3 attempts |
| Deduplication | `event_id` UUID — `INSERT OR IGNORE` on server |

---

## API Reference

### `GET /dl` — Create Session

The entry point for ad links.

| Parameter | Required | Description |
|-----------|:--------:|-------------|
| `promo_id` | ✓ | Campaign / promotion identifier |
| `domain` | ✓ | Domain for identification |
| `timezone` | — | IANA timezone (`America/New_York`) |
| `language` | — | Language code (`en_US`) |
| `screen_size` | — | Screen resolution (`390x844`) |
| `model` | — | Device model string |
| `ttl` | — | Session lifetime in hours (default: 48) |

**Response by User-Agent:**

| Browser | Response |
|---------|----------|
| Safari (iOS) | `302` → App Store + `Set-Cookie: dl_session_id` |
| Facebook / Instagram IAB | `200` → HTML escape page (clipboard handoff + redirect) |
| TikTok / WeChat IAB | `302` → App Store directly |
| Desktop | `200` → HTML instruction page |

---

### `POST /resolve` — Match Session

Called by the iOS SDK on first app launch.

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

Called by the SDK through an invisible `SFSafariViewController`. Reads the cookie and redirects back to the app:

```
Found:     → myapp://resolved?session_id=<uuid>
Not found: → myapp://resolved?session_id=none
```

---

### `POST /api/v1/events` — Track Single Event

For server-side integrations or diagnostic tooling.

**Request body:**
```json
{
  "event_id":    "550e8400-e29b-41d4-a716-446655440000",
  "event_name":  "af_purchase",
  "timestamp":   "2025-04-22T14:30:00Z",
  "session_id":  "abc-def-123",
  "app_user_id": "user_42",
  "promo_id":    "SUMMER24",
  "revenue":     29.99,
  "currency":    "USD",
  "properties":  {
    "af_order_id":   "ORD-1234",
    "af_content_id": "pro_annual",
    "af_quantity":   1
  },
  "platform":    "iOS",
  "app_version": "2.1.0",
  "sdk_version": "1.0.0"
}
```

**Response:**
```json
{
  "success":  true,
  "message":  "Event tracked",
  "event_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

### `POST /api/v1/events/batch` — Batch Events

Send up to 100 events in a single request. This is the endpoint the iOS SDK uses for all scheduled flushes.

**Request body:**
```json
{
  "events": [
    {
      "event_id":    "uuid-001",
      "event_name":  "af_content_view",
      "timestamp":   "2025-04-22T14:28:00Z",
      "app_user_id": "user_42",
      "promo_id":    "SUMMER24",
      "properties":  { "af_content_id": "product_99", "af_price": 29.99 }
    },
    {
      "event_id":    "uuid-002",
      "event_name":  "af_add_to_cart",
      "timestamp":   "2025-04-22T14:29:10Z",
      "app_user_id": "user_42",
      "promo_id":    "SUMMER24",
      "properties":  { "af_content_id": "product_99", "af_quantity": 1 }
    },
    {
      "event_id":    "uuid-003",
      "event_name":  "af_purchase",
      "timestamp":   "2025-04-22T14:30:45Z",
      "app_user_id": "user_42",
      "promo_id":    "SUMMER24",
      "revenue":     29.99,
      "currency":    "USD",
      "properties":  { "af_order_id": "ORD-1234" }
    }
  ]
}
```

**Response:**
```json
{
  "success":   true,
  "inserted":  3,
  "duplicate": 0,
  "failed":    0
}
```

| Field | Description |
|-------|-------------|
| `inserted` | New events written to the database |
| `duplicate` | Events skipped — `event_id` already exists |
| `failed` | Events rejected due to missing `event_id` or `event_name` |

---

### `GET /api/v1/events/stats` — Event Statistics

Aggregated metrics for any time window, optionally scoped to a single campaign.

**Query parameters:**

| Parameter | Description |
|-----------|-------------|
| `start` | Period start, ISO 8601 (optional) |
| `end` | Period end, ISO 8601 (optional) |
| `promo_id` | Filter by promotion (optional) |

**Example:**
```
GET /api/v1/events/stats?start=2025-04-01T00:00:00Z&end=2025-04-30T23:59:59Z&promo_id=SUMMER24
```

**Response:**
```json
{
  "success":           true,
  "total_events":      1482,
  "unique_users":      347,
  "unique_sessions":   389,
  "total_revenue":     8741.53,
  "revenue_events":    214,
  "top_events": [
    { "event_name": "af_content_view",          "cnt": 612, "revenue": 0.0     },
    { "event_name": "af_add_to_cart",           "cnt": 289, "revenue": 0.0     },
    { "event_name": "af_initiated_checkout",    "cnt": 231, "revenue": 0.0     },
    { "event_name": "af_purchase",              "cnt": 214, "revenue": 8741.53 },
    { "event_name": "af_complete_registration", "cnt": 136, "revenue": 0.0     }
  ],
  "revenue_by_currency": [
    { "currency": "USD", "total": 7210.45 },
    { "currency": "EUR", "total": 1531.08 }
  ]
}
```

---

### `GET /api/v1/events/funnel` — Conversion Funnel

Step-by-step funnel analysis. For each step, only users who completed **all prior steps in chronological order** are counted — ensuring real sequential conversion rates, not just per-event totals.

**Query parameters:**

| Parameter | Description |
|-----------|-------------|
| `steps` | Ordered event names (2–10 steps, repeated query param) |
| `start` | Period start (optional) |
| `end` | Period end (optional) |
| `promo_id` | Filter by promotion (optional) |

**Example:**
```
GET /api/v1/events/funnel
  ?steps=af_content_view
  &steps=af_add_to_cart
  &steps=af_initiated_checkout
  &steps=af_purchase
  &promo_id=SUMMER24
```

**Response:**
```json
{
  "success": true,
  "steps": ["af_content_view", "af_add_to_cart", "af_initiated_checkout", "af_purchase"],
  "funnel": [
    {
      "step":             1,
      "event_name":       "af_content_view",
      "users":            612,
      "conversion_prev":  100.0,
      "conversion_total": 100.0
    },
    {
      "step":             2,
      "event_name":       "af_add_to_cart",
      "users":            289,
      "conversion_prev":  47.2,
      "conversion_total": 47.2
    },
    {
      "step":             3,
      "event_name":       "af_initiated_checkout",
      "users":            231,
      "conversion_prev":  79.9,
      "conversion_total": 37.7
    },
    {
      "step":             4,
      "event_name":       "af_purchase",
      "users":            214,
      "conversion_prev":  92.6,
      "conversion_total": 35.0
    }
  ]
}
```

| Field | Description |
|-------|-------------|
| `conversion_prev` | Conversion rate from the **previous step**, % |
| `conversion_total` | Overall conversion from **step 1**, % |

---

### `GET /api/v1/events/revenue` — Daily Revenue Cohort

Revenue broken down by day, promotion, and currency — useful for tracking LTV curves and campaign ROI.

**Query parameters:**

| Parameter | Default | Description |
|-----------|:-------:|-------------|
| `promo_id` | — | Filter by promotion |
| `days` | `30` | History depth (1–365) |

**Example:**
```
GET /api/v1/events/revenue?promo_id=SUMMER24&days=7
```

**Response:**
```json
{
  "success": true,
  "rows": [
    {
      "day":             "2025-04-22",
      "promo_id":        "SUMMER24",
      "currency":        "USD",
      "purchases":       48,
      "revenue":         1439.52,
      "avg_order_value": 29.99
    },
    {
      "day":             "2025-04-21",
      "promo_id":        "SUMMER24",
      "currency":        "USD",
      "purchases":       61,
      "revenue":         1829.39,
      "avg_order_value": 29.99
    }
  ]
}
```

---

### `GET /api/v1/events/standard-events` — Standard Event List

```json
{
  "standard_events": [
    "af_add_to_cart", "af_add_to_wishlist", "af_complete_registration",
    "af_content_view", "af_initiated_checkout", "af_install", "af_invite",
    "af_launch", "af_level_achieved", "af_login", "af_purchase", "af_rate",
    "af_re_engage", "af_search", "af_share", "af_subscribe",
    "af_tutorial_completion", "af_update"
  ]
}
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
# ── Security (required in production) ────────────────────────────────────
SECRET_KEY=                    # min 32 characters
                               # python3 -c "import secrets; print(secrets.token_urlsafe(32))"
ENVIRONMENT=production         # development | production
CORS_ORIGINS=https://myapp.com
COOKIE_SECURE=true
COOKIE_SAMESITE=lax

# ── Database ──────────────────────────────────────────────────────────────
DATABASE_PATH=data/deeplinks.db

# ── App ───────────────────────────────────────────────────────────────────
APP_STORE_ID=1234567890        # numeric App Store ID
APP_NAME=MyApp                 # shown on the escape page
APP_URL_SCHEME=myapp           # URL scheme (Info.plist)
CLIPBOARD_TOKEN_PREFIX=deferlink

# ── Sessions ──────────────────────────────────────────────────────────────
DEFAULT_TTL_HOURS=48
CLEANUP_INTERVAL_MINUTES=30

# ── API ───────────────────────────────────────────────────────────────────
API_HOST=0.0.0.0
API_PORT=8000
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60

# ── Apple DeviceCheck (Tier 3) ────────────────────────────────────────────
DEVICECHECK_ENABLED=true
DEVICECHECK_TEAM_ID=ABCDE12345
DEVICECHECK_KEY_ID=ABC123DEF456
DEVICECHECK_KEY_PATH=/secrets/AuthKey_ABC123DEF456.p8
DEVICECHECK_SANDBOX=false      # true for dev / staging

# ── Analytics ─────────────────────────────────────────────────────────────
ENABLE_ANALYTICS=true
AUTO_OPTIMIZE_WEIGHTS=false    # auto-tune fingerprint matching weights
LOG_LEVEL=INFO
```

---

## Project Architecture

```
deferlink/
├── app/
│   ├── main.py                    FastAPI app — /dl, /resolve, /safari-resolve
│   ├── config.py                  Environment-based configuration
│   ├── models.py                  Pydantic models (FingerprintData, ResolveResponse)
│   ├── deeplink_handler.py        4-tier matching orchestrator
│   ├── database.py                SQLite manager + auto-migration runner
│   ├── core/
│   │   ├── intelligent_matcher.py Fingerprint matching — Tier 4
│   │   ├── iab_detector.py        IAB detection + escape strategy selector
│   │   ├── safari_escape.py       HTML escape page (clipboard handoff + redirect)
│   │   ├── devicecheck.py         Apple DeviceCheck API client — Tier 3
│   │   └── event_tracker.py       Event storage, stats, funnels, revenue cohorts
│   ├── api/
│   │   ├── deeplinks.py           POST /api/v1/resolve
│   │   ├── stats.py               GET  /api/v1/stats
│   │   ├── health.py              GET  /api/v1/health
│   │   └── events.py              POST /events /events/batch
│   │                              GET  /events/stats /events/funnel /events/revenue
│   └── migrations/
│       ├── add_devicecheck_fields.py
│       └── add_events_table.py    user_events table (15 columns, 6 indexes)
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
│       │   └── DeviceCheckManager.swift   DCDevice token + 1h UserDefaults cache
│       ├── Network/DeferLinkClient.swift  POST /resolve /events/batch, GET /safari-resolve
│       └── Events/
│           ├── DeferLinkEvent.swift   Model + DLEventName + DLEventParam + AnyCodable
│           ├── EventQueue.swift       Offline-first persistence (Application Support JSON)
│           └── EventTracker.swift     Batching + retry + app lifecycle observer
│
└── DeferLinkTestApp/              SDK integration example (SwiftUI)
```

---

## Security

- **No IDFA / ATT** — the system does not use advertising identifiers
- **Clipboard cleared** immediately after reading the token (`UIPasteboard.general.string = ""`)
- **DeviceCheck tokens** stored as SHA-256 hash only — raw tokens are never persisted
- **Sessions with TTL** — expired sessions purged every 30 minutes
- **Rate limiting** — endpoint protection against automated abuse
- **Fraud detection** — blocks more than 100 requests from a single IP per hour
- **Event deduplication** — client UUID prevents double-counting on network retries

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
