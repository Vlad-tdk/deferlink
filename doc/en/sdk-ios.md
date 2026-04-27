# iOS SDK

`DeferLinkSDK` — a lightweight Swift package that does deferred deep linking, AppsFlyer-style event tracking and SKAdNetwork CV submission. Single dependency: Apple frameworks only (`UIKit`, `SafariServices`, `StoreKit`, `DeviceCheck`).

* Module name: `DeferLinkSDK`
* Minimum iOS: **14.0** (graceful fallbacks for SKAN APIs added in 15.4 and 16.1)
* Threading: every public method is `@MainActor`
* Version: `DeferLinkSDKInfo.version = "1.0.0"`

Source layout:

```
DeferLinkSDK/Sources/DeferLinkSDK/
├── DeferLink.swift                — public façade (singleton `DeferLink.shared`)
├── DeferLinkConfiguration.swift   — config struct
├── DeferLinkLogger.swift          — debug/warning logging
├── Models/DeferLinkModels.swift   — DeferLinkResult, MatchMethod, ResolveResponse, FingerprintPayload
├── Network/DeferLinkClient.swift  — URLSession-based async HTTPS client
├── Core/
│   ├── FingerprintCollector.swift — collects FingerprintPayload (clipboard, DeviceCheck, fingerprint)
│   ├── DeviceInfoCollector.swift  — model, screen, locale, UA
│   └── DeviceCheckManager.swift   — Apple DCDevice token
├── Events/
│   ├── DeferLinkEvent.swift       — Event model + DLEventName constants
│   ├── EventQueue.swift           — disk-backed FIFO queue
│   └── EventTracker.swift         — batching + lifecycle flush
└── SKAdNetwork/
    ├── SKANConfig.swift           — per-app CV thresholds
    ├── SKANState.swift            — persisted SKAN window state
    ├── CVEncoder.swift            — computes CV (matches `app/core/skadnetwork/cv_schema.py`)
    └── SKANManager.swift          — orchestrates session/revenue/CV submission
```

## Setup

### 1. Add the package

In Xcode → **File → Add Package Dependencies…** → use your Git URL or drag the local `DeferLinkSDK/` folder as a Swift package.

### 2. Configure once at app start

```swift
import DeferLinkSDK

@main
struct MyApp: App {
    init() {
        DeferLink.configure(
            baseURL:      "https://api.your-domain.com",
            appURLScheme: "myapp",      // must match Info.plist URL Types AND server APP_URL_SCHEME
            debugLogging: false
        )
    }

    var body: some Scene {
        WindowGroup { ContentView() }
    }
}
```

Or with full configuration:

```swift
let cfg = DeferLinkConfiguration(
    baseURL:              "https://api.your-domain.com",
    appURLScheme:         "myapp",
    clipboardTokenPrefix: "deferlink",   // must match server CLIPBOARD_TOKEN_PREFIX
    safariResolveTimeout: 3.0,
    networkTimeout:       10.0,
    debugLogging:         true
)
DeferLink.configure(with: cfg)
```

### 3. Resolve on first launch

```swift
DeferLink.shared.resolveOnFirstLaunch { result in
    guard let result = result, result.matched else { return }
    if let promoId = result.promoId {
        // navigate to /promo/<promoId>
    }
}
```

`async/await` flavour:

```swift
if let r = await DeferLink.shared.resolve(), r.matched {
    routeTo(promoId: r.promoId)
}
```

`DeferLinkResult` has `matched`, `matchMethod (.clipboard | .safariCookie | .deviceCheck | .fingerprint)`, `promoId`, `sessionId`, `redirectUrl`, `appUrl`, `confidence`.

`resolve()` skips itself on subsequent launches — `FingerprintCollector.isFirstLaunch` is persisted in `UserDefaults`.

### 4. Forward URL opens

```swift
// SceneDelegate
func scene(_ scene: UIScene, openURLContexts URLContexts: Set<UIOpenURLContext>) {
    URLContexts.forEach { DeferLink.shared.handleOpenURL($0.url) }
}
```

`DeferLink.shared.handleOpenURL(_:)`:

* Intercepts `<scheme>://resolved?session_id=...` (the SFSafariViewController callback) and resumes the resolve continuation.
* Posts `Notification.Name.deferLinkReceived` with the URL as `userInfo["url"]` for any other deep link.
* Returns `true` if the URL was for our scheme.

## Resolve flow internals

`DeferLink.resolve()` does (in order):

1. Bail if not first launch.
2. **Tier 2 first**: present an invisible `SFSafariViewController` pointed at `GET /safari-resolve`. It hits the shared cookie jar; the server reads `dl_session_id` and `302`s back into the app via `<scheme>://resolved?session_id=...`. The continuation set up in step 2 resumes with the session id, or `nil` after `safariResolveTimeout`.
3. **Tiers 1, 3, 4 together** — `FingerprintCollector.collect(safariCookieSessionId:)` builds a `FingerprintPayload` containing:
   * clipboard token (read once with permission prompt; only kept if it has the configured `CLIPBOARD_TOKEN_PREFIX`),
   * `safari_cookie_session_id` from step 2,
   * DeviceCheck token from `DeviceCheckManager.generateToken()` (graceful nil if Apple rejects),
   * full fingerprint — model, language, timezone, screen, UA, idfv,
   * `is_first_launch=true`.
4. `DeferLinkClient.resolve(payload:appScheme:)` POSTs to `/resolve`. The response's `matchMethod` tells you which tier won.

After a successful match:

* `EventTracker.sessionId` and `EventTracker.promoId` are stamped so every subsequent `logEvent` carries the attribution context.
* `FingerprintCollector.markFirstLaunchDone()` flips the persisted flag.

## Event tracking

```swift
DeferLink.shared.logEvent(.purchase(9.99, currency: "USD"))

DeferLink.shared.logEvent("af_complete_registration",
                          properties: [DLEventParam.registrationMethod: "email"])

DeferLink.shared.logEvent("af_purchase",
                          revenue: 49.99, currency: "EUR",
                          properties: [DLEventParam.orderId: "order_42"])

DeferLink.shared.setUserId("user-123")     // attaches app_user_id to all future events
```

`DLEventName` mirrors AppsFlyer (`af_install`, `af_launch`, `af_complete_registration`, `af_login`, `af_purchase`, `af_add_to_cart`, `af_subscribe`, `af_level_achieved`, …) — full list in `DeferLinkEvent.swift`. Custom names (anything not in `STANDARD_EVENTS` server-side) are accepted; the server filters analytics views by the `af_*` set.

`DLEventParam` exposes recommended property keys (`af_content_id`, `af_revenue`, `af_currency`, `af_quantity`, …). The `properties` dict goes through `AnyCodable` so heterogeneous values are encoded fine.

`DeferLinkEvent`:

```swift
public struct DeferLinkEvent: Encodable {
    public let eventId:    String        // UUID; dedup key
    public let eventName:  String
    public let timestamp:  String        // ISO 8601 from Date()
    public var sessionId:  String?       // auto-stamped after resolve
    public var appUserId:  String?
    public var promoId:    String?       // auto-stamped after resolve
    public var revenue:    Double?
    public var currency:   String        // default "USD"
    public var properties: [String: AnyCodable]?
    public var platform:   String        // "iOS"
    public var appVersion: String?       // CFBundleShortVersionString
    public var sdkVersion: String        // DeferLinkSDKInfo.version
}
```

`EventTracker` writes events to a disk-backed `EventQueue` and flushes them via `POST /api/v1/events/batch` on a `Timer`, on `UIApplication.didEnterBackground`, and on `flushEvents()` (test convenience). Up to 100 events per batch.

## SKAdNetwork

```swift
DeferLink.shared.enableSKAdNetwork(appId: "1234567890")    // your iTunes app id

DeferLink.shared.markSKANCoreAction()                       // engagement signal
DeferLink.shared.recordSKANRevenue(9.99, currency: "USD")   // revenue signal
```

Once enabled, `SKANManager` automatically:

* fetches the per-app `SKANConfig` from `GET /api/v1/skan/config?app_id=…` on first launch and caches it for `cache_ttl_seconds`;
* hooks `UIApplication.didBecomeActiveNotification` / `willResignActiveNotification` to track session count and total seconds;
* on every state change, recomputes the 6-bit CV via `CVEncoder.computeCV(...)` (mirrors `cv_schema.py` byte-for-byte: `(revenue_bucket << 3) | (engagement << 1) | flag`);
* enforces Apple's rule that CV must be monotonically non-decreasing inside the conversion window;
* submits via the best available API:

  | iOS | API |
  |---|---|
  | 16.1+ | `SKAdNetwork.updatePostbackConversionValue(_, coarseValue:, lockWindow:)` (fine + coarse) |
  | 15.4–16.0 | `SKAdNetwork.updatePostbackConversionValue(_:completionHandler:)` (fine only) |
  | 14.0–15.3 | `SKAdNetwork.updateConversionValue(_:)` (fine only) |

  Coarse mapping (matches server-side synthetic mapping):

  ```
  cv 0...20  → .low
  cv 21...41 → .medium
  cv 42...63 → .high
  ```

`EventTracker.revenueForwarder` is auto-wired to `SKANManager.recordRevenue(...)` when SKAN is enabled, so `logEvent(.purchase(...))` already feeds into both Facebook CAPI (server-side) and SKAN CV (client-side).

`SKANState` is persisted in `UserDefaults` under a single key (`SKANStateStore`). Use `SKANManager.resetState()` only in test harnesses.

## Logging

`DeferLinkLogger.isEnabled` is set from `DeferLinkConfiguration.debugLogging`. Three levels: `debug`, `info`, `warning`. When disabled, only warnings reach the console.

## Testing

A SwiftUI test harness lives in `DeferLinkTestApp/`. Open `DeferLinkTestApp.xcodeproj`, point `NetworkManager.baseURL` at your backend (`http://127.0.0.1:8000` for the iOS Simulator), and tap **Run All Tests** to drive every endpoint and run deterministic seed→resolve scenarios. Step-by-step instructions are in [`install-and-test.md`](install-and-test.md#testing-the-ios-sdk).

## Public API summary

```swift
// MARK: configuration
DeferLink.configure(baseURL: "...", appURLScheme: "...", debugLogging: false)
DeferLink.configure(with: DeferLinkConfiguration(...))

// MARK: resolve
DeferLink.shared.resolveOnFirstLaunch { result in ... }
let r: DeferLinkResult? = await DeferLink.shared.resolve()
DeferLink.shared.handleOpenURL(url)            // -> Bool

// MARK: events
DeferLink.shared.logEvent("af_login")
DeferLink.shared.logEvent("af_purchase", revenue: 9.99, currency: "USD")
DeferLink.shared.logEvent(.purchase(9.99))
DeferLink.shared.setUserId("user-123")
DeferLink.shared.flushEvents()

// MARK: SKAN
DeferLink.shared.enableSKAdNetwork(appId: "1234567890")
DeferLink.shared.markSKANCoreAction()
DeferLink.shared.recordSKANRevenue(9.99, currency: "USD")

// MARK: notifications
NotificationCenter.default.addObserver(forName: .deferLinkReceived, ...)
```
