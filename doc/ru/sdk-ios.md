# iOS SDK

`DeferLinkSDK` — лёгкий Swift-пакет для deferred deep linking, AppsFlyer-стиля event tracking и отправки SKAdNetwork CV. Зависимости — только Apple-фреймворки (`UIKit`, `SafariServices`, `StoreKit`, `DeviceCheck`).

* Имя модуля: `DeferLinkSDK`
* Минимальная iOS: **14.0** (мягкие фолбэки для SKAN API из 15.4 и 16.1)
* Потоки: каждый публичный метод `@MainActor`
* Версия: `DeferLinkSDKInfo.version = "1.0.0"`

Структура исходников:

```
DeferLinkSDK/Sources/DeferLinkSDK/
├── DeferLink.swift                — публичный фасад (singleton `DeferLink.shared`)
├── DeferLinkConfiguration.swift   — структура конфига
├── DeferLinkLogger.swift          — debug/warning логирование
├── Models/DeferLinkModels.swift   — DeferLinkResult, MatchMethod, ResolveResponse, FingerprintPayload
├── Network/DeferLinkClient.swift  — async HTTPS-клиент на URLSession
├── Core/
│   ├── FingerprintCollector.swift — собирает FingerprintPayload (clipboard, DeviceCheck, fingerprint)
│   ├── DeviceInfoCollector.swift  — модель, экран, локаль, UA
│   └── DeviceCheckManager.swift   — токен Apple DCDevice
├── Events/
│   ├── DeferLinkEvent.swift       — модель события + константы DLEventName
│   ├── EventQueue.swift           — FIFO-очередь на диске
│   └── EventTracker.swift         — батчинг + flush по lifecycle
└── SKAdNetwork/
    ├── SKANConfig.swift           — пороги CV на приложение
    ├── SKANState.swift            — персистентное состояние SKAN-окна
    ├── CVEncoder.swift            — вычисляет CV (зеркалит `app/core/skadnetwork/cv_schema.py`)
    └── SKANManager.swift          — оркестрация сессий/выручки/отправки CV
```

## Установка

### 1. Добавить пакет

В Xcode → **File → Add Package Dependencies…** → Git URL вашего форка или просто перетащите локальную папку `DeferLinkSDK/` как Swift package.

### 2. Конфигурация один раз на старте

```swift
import DeferLinkSDK

@main
struct MyApp: App {
    init() {
        DeferLink.configure(
            baseURL:      "https://api.your-domain.com",
            appURLScheme: "myapp",      // должен совпадать с Info.plist URL Types и серверным APP_URL_SCHEME
            debugLogging: false
        )
    }

    var body: some Scene {
        WindowGroup { ContentView() }
    }
}
```

Полная конфигурация:

```swift
let cfg = DeferLinkConfiguration(
    baseURL:              "https://api.your-domain.com",
    appURLScheme:         "myapp",
    clipboardTokenPrefix: "deferlink",   // должен совпадать с CLIPBOARD_TOKEN_PREFIX на сервере
    safariResolveTimeout: 3.0,
    networkTimeout:       10.0,
    debugLogging:         true
)
DeferLink.configure(with: cfg)
```

### 3. Resolve при первом запуске

```swift
DeferLink.shared.resolveOnFirstLaunch { result in
    guard let result = result, result.matched else { return }
    if let promoId = result.promoId {
        // переход на /promo/<promoId>
    }
}
```

`async/await` вариант:

```swift
if let r = await DeferLink.shared.resolve(), r.matched {
    routeTo(promoId: r.promoId)
}
```

`DeferLinkResult`: `matched`, `matchMethod (.clipboard | .safariCookie | .deviceCheck | .fingerprint)`, `promoId`, `sessionId`, `redirectUrl`, `appUrl`, `confidence`.

`resolve()` пропускает себя при последующих запусках — `FingerprintCollector.isFirstLaunch` хранится в `UserDefaults`.

### 4. Передача URL-открытий

```swift
// SceneDelegate
func scene(_ scene: UIScene, openURLContexts URLContexts: Set<UIOpenURLContext>) {
    URLContexts.forEach { DeferLink.shared.handleOpenURL($0.url) }
}
```

`DeferLink.shared.handleOpenURL(_:)`:

* Перехватывает `<scheme>://resolved?session_id=...` (callback SFSafariViewController) и снимает блок resolve-continuation.
* Постит `Notification.Name.deferLinkReceived` с URL в `userInfo["url"]` для остальных deep links.
* Возвращает `true`, если URL был для нашей схемы.

## Внутренности resolve

`DeferLink.resolve()` делает (по порядку):

1. Выходит, если не первый запуск.
2. **Сначала Tier 2**: показывает невидимый `SFSafariViewController` на `GET /safari-resolve`. Он попадает в общий cookie jar; сервер читает `dl_session_id` и `302`-редиректит обратно через `<scheme>://resolved?session_id=...`. Continuation, выставленный в шаге 2, резюмируется с session_id или `nil` после `safariResolveTimeout`.
3. **Tiers 1, 3, 4 вместе** — `FingerprintCollector.collect(safariCookieSessionId:)` собирает `FingerprintPayload` с:
   * clipboard-токеном (читается раз с разрешением; кладётся, только если у него нужный `CLIPBOARD_TOKEN_PREFIX`),
   * `safari_cookie_session_id` из шага 2,
   * DeviceCheck-токеном из `DeviceCheckManager.generateToken()` (мягкий nil при отказе Apple),
   * полным fingerprint — модель, язык, timezone, экран, UA, idfv,
   * `is_first_launch=true`.
4. `DeferLinkClient.resolve(payload:appScheme:)` POST-ит на `/resolve`. `matchMethod` ответа скажет, какой tier сработал.

После успешного матча:

* `EventTracker.sessionId` и `EventTracker.promoId` проставляются — каждое последующее `logEvent` несёт контекст атрибуции.
* `FingerprintCollector.markFirstLaunchDone()` переключает persisted-флаг.

## Трекинг событий

```swift
DeferLink.shared.logEvent(.purchase(9.99, currency: "USD"))

DeferLink.shared.logEvent("af_complete_registration",
                          properties: [DLEventParam.registrationMethod: "email"])

DeferLink.shared.logEvent("af_purchase",
                          revenue: 49.99, currency: "EUR",
                          properties: [DLEventParam.orderId: "order_42"])

DeferLink.shared.setUserId("user-123")     // прицепит app_user_id ко всем будущим событиям
```

`DLEventName` зеркалит AppsFlyer (`af_install`, `af_launch`, `af_complete_registration`, `af_login`, `af_purchase`, `af_add_to_cart`, `af_subscribe`, `af_level_achieved`, …) — полный список в `DeferLinkEvent.swift`. Кастомные имена (вне `STANDARD_EVENTS` на сервере) принимаются; серверная аналитика фильтрует свои view-эндпоинты по набору `af_*`.

`DLEventParam` — рекомендуемые ключи свойств (`af_content_id`, `af_revenue`, `af_currency`, `af_quantity`, …). Словарь `properties` идёт через `AnyCodable`, так что разнотипные значения сериализуются нормально.

`DeferLinkEvent`:

```swift
public struct DeferLinkEvent: Encodable {
    public let eventId:    String        // UUID; ключ дедупа
    public let eventName:  String
    public let timestamp:  String        // ISO 8601 от Date()
    public var sessionId:  String?       // авто-проставляется после resolve
    public var appUserId:  String?
    public var promoId:    String?       // авто-проставляется после resolve
    public var revenue:    Double?
    public var currency:   String        // default "USD"
    public var properties: [String: AnyCodable]?
    public var platform:   String        // "iOS"
    public var appVersion: String?       // CFBundleShortVersionString
    public var sdkVersion: String        // DeferLinkSDKInfo.version
}
```

`EventTracker` пишет события в дисковую `EventQueue` и сливает их через `POST /api/v1/events/batch` по `Timer`, на `UIApplication.didEnterBackground` и на `flushEvents()` (для тестов). До 100 событий в батче.

## SKAdNetwork

```swift
DeferLink.shared.enableSKAdNetwork(appId: "1234567890")    // ваш iTunes app id

DeferLink.shared.markSKANCoreAction()                       // engagement-сигнал
DeferLink.shared.recordSKANRevenue(9.99, currency: "USD")   // revenue-сигнал
```

После включения `SKANManager` автоматически:

* при первом запуске тянет `SKANConfig` через `GET /api/v1/skan/config?app_id=…` и кеширует на `cache_ttl_seconds`;
* подписывается на `UIApplication.didBecomeActiveNotification` / `willResignActiveNotification`, считая сессии и общее время;
* на каждое изменение состояния пересчитывает 6-битный CV через `CVEncoder.computeCV(...)` (1:1 с `cv_schema.py`: `(revenue_bucket << 3) | (engagement << 1) | flag`);
* соблюдает правило Apple: внутри окна конверсии CV должен быть монотонно неубывающим;
* отправляет лучшим доступным API:

  | iOS | API |
  |---|---|
  | 16.1+ | `SKAdNetwork.updatePostbackConversionValue(_, coarseValue:, lockWindow:)` (fine + coarse) |
  | 15.4–16.0 | `SKAdNetwork.updatePostbackConversionValue(_:completionHandler:)` (fine only) |
  | 14.0–15.3 | `SKAdNetwork.updateConversionValue(_:)` (fine only) |

  Маппинг coarse (совпадает с серверным синтетическим):

  ```
  cv 0...20  → .low
  cv 21...41 → .medium
  cv 42...63 → .high
  ```

`EventTracker.revenueForwarder` авто-привязывается к `SKANManager.recordRevenue(...)` при включении SKAN — `logEvent(.purchase(...))` уже кормит и Facebook CAPI (на сервере), и SKAN CV (на клиенте).

`SKANState` хранится в `UserDefaults` под одним ключом (`SKANStateStore`). `SKANManager.resetState()` вызывайте только в тестах.

## Логирование

`DeferLinkLogger.isEnabled` берётся из `DeferLinkConfiguration.debugLogging`. Уровни — `debug`, `info`, `warning`. При выключенном дебаге в консоль уходят только warning-и.

## Тестирование

SwiftUI-харнес лежит в `DeferLinkTestApp/`. Откройте `DeferLinkTestApp.xcodeproj`, прицельте `NetworkManager.baseURL` в свой бэкенд (`http://127.0.0.1:8000` для iOS Simulator) и тапните **Run All Tests**, чтобы прогнать каждый эндпоинт и детерминированные seed→resolve сценарии. Пошаговая инструкция — в [`install-and-test.md`](install-and-test.md#тесты-ios-sdk).

## Сводка публичного API

```swift
// MARK: configure
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
