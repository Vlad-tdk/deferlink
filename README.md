<div align="center">

# DeferLink

**Self-hosted deferred deep linking — без зависимостей от Branch, AppsFlyer и Firebase**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![iOS](https://img.shields.io/badge/iOS-15+-000000?logo=apple&logoColor=white)](https://developer.apple.com)
[![Swift](https://img.shields.io/badge/Swift-5.9-FA7343?logo=swift&logoColor=white)](https://swift.org)
[![License](https://img.shields.io/badge/License-Apache-blue)](LICENSE)

[Быстрый старт](#быстрый-старт) · [Как работает](#как-работает) · [iOS SDK](#ios-sdk) · [Event Tracking](#отслеживание-событий) · [API](#api-reference) · [Конфигурация](#конфигурация)

</div>

---

## Что это

DeferLink решает классическую задачу мобильного маркетинга: пользователь кликает по рекламе → попадает в App Store → устанавливает приложение — а после установки приложение «помнит» откуда он пришёл и куда хотел попасть.

В отличие от SaaS-решений (Branch.io, AppsFlyer, Firebase Dynamic Links) — DeferLink **разворачивается на вашем сервере**: данные не покидают вашу инфраструктуру, нет лимитов на события, нет ежемесячных платежей.

```
Пользователь              Сервер                    Приложение
     │                       │                           │
     │  Клик по рекламе      │                           │
     │──────────────────────>│                           │
     │                       │  Создать сессию           │
     │                       │  (fingerprint + cookie)   │
     │  App Store → Установка│                           │
     │                       │                           │
     │                       │         Первый запуск     │
     │                       │<──────────────────────────│
     │                       │  Найти сессию             │
     │                       │──────────────────────────>│
     │                       │  promoId / deep link URL  │
```

---

## Ключевые возможности

- **4-уровневый матчинг** — от 100% точности (clipboard token) до интеллектуального fingerprinting
- **IAB Detection** — автоматически определяет Facebook / Instagram / TikTok in-app browser и применяет стратегию обхода
- **Safari Escape** — clipboard handoff через `execCommand` в WKWebView без user gesture
- **Apple DeviceCheck** — опциональная верификация через Apple API без ATT / IDFA
- **SFSafariViewController** — разделяемый cookie jar с Safari для высокоточного матчинга
- **Event Tracking** — встроенная аналитика событий в стиле AppsFlyer: воронки, выручка, офлайн-очередь
- **Self-hosted** — SQLite из коробки, легко мигрировать на PostgreSQL
- **iOS Swift Package** — 3 строки кода для интеграции

---

## Как работает

### Многоуровневый матчинг

При первом запуске приложения SDK последовательно проверяет сигналы — от наиболее к наименее точному:

| Tier | Метод | Точность | Когда работает |
|:----:|-------|:--------:|---------------|
| **1** | Clipboard token | **100%** | Пользователь пришёл из Facebook / Instagram IAB |
| **2** | Safari cookie | **~99%** | Ссылка открыта в настоящем Safari |
| **3** | Apple DeviceCheck | **~97%** | Повторный запуск, токен уже связан с сессией |
| **4** | Fingerprint | **60–90%** | Timezone + экран + язык + модель устройства |

Первый успешный Tier прерывает цепочку — алгоритм не запускается зря.

---

### Tier 1 — Clipboard Handoff (Facebook / Instagram IAB)

Facebook и Instagram открывают ссылки во встроенном браузере (WKWebView), где DeviceCheck недоступен. DeferLink использует следующий трюк:

```
1. Пользователь кликает рекламу → Facebook IAB открывает /dl
2. Сервер видит FBAN в User-Agent → возвращает escape-страницу вместо редиректа
3. JavaScript: document.execCommand('copy')
   ──────────────────────────────────────
   В WKWebView execCommand работает БЕЗ user gesture,
   в отличие от navigator.clipboard.writeText() в Safari.
   ──────────────────────────────────────
   В буфер обмена попадает: "deferlink:<session_id>"
4. Через 400 мс → редирект в App Store
5. Пользователь устанавливает приложение
6. Приложение: UIPasteboard.general.string → "deferlink:<session_id>"
7. POST /resolve с clipboard_token → 100% матч
```

---

### Tier 2 — SFSafariViewController Cookie

Если ссылка открыта в настоящем Safari, сервер устанавливает cookie. При первом запуске приложение невидимо открывает `SFSafariViewController` — он разделяет cookie jar с Safari:

```
App first launch
  → SFSafariViewController (isHidden=true)
  → GET /safari-resolve
  → Сервер читает dl_session_id cookie
  → redirect: myapp://resolved?session_id=<uuid>
  → SceneDelegate.scene(_:openURLContexts:)
  → DeferLink.shared.handleOpenURL(url)
  → Матч без fingerprinting
```

---

### Tier 4 — IntelligentMatcher (Fingerprint)

Когда Tier 1–3 недоступны — алгоритм собирает weighted score по 5 параметрам:

```python
weights = {
    'timezone':          0.35,   # высокая стабильность
    'screen_dimensions': 0.25,   # точная характеристика
    'language':          0.20,   # стабильный параметр
    'device_model':      0.15,   # fuzzy matching
    'user_agent':        0.05,   # низкая надёжность
}
```

Алгоритм учитывает эквивалентные timezone (Moscow ≈ Volgograd), допуск экрана ±60px (системные элементы iOS), родственные локали (en_US ≈ en_GB) и временны́е паттерны сессии.

---

## Быстрый старт

### Сервер

```bash
git clone https://github.com/your/deferlink && cd deferlink

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload --port 8000
```

Сервер запустится на `http://localhost:8000`.  
Swagger UI: `http://localhost:8000/docs`

### Ссылка для рекламы

```
https://api.myapp.com/dl?promo_id=SUMMER24&domain=myapp.com
```

Дополнительные параметры повышают точность Tier 4 — собирайте их на лендинге через JS:

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

### Установка

**Swift Package Manager** — в Xcode:

`File → Add Package Dependencies → Add Local` → выбрать папку `DeferLinkSDK`

Или в `Package.swift`:
```swift
.package(path: "../DeferLinkSDK")
```

### Настройка Xcode

1. **Signing & Capabilities → + Capability → DeviceCheck** (для Tier 3, на реальном устройстве)
2. **Info.plist → URL Types** — добавить URL scheme:
```xml
<key>CFBundleURLSchemes</key>
<array><string>myapp</string></array>
```

### Интеграция

**AppDelegate.swift:**
```swift
import DeferLinkSDK

func application(_ application: UIApplication,
                 didFinishLaunchingWithOptions launchOptions: [...]) -> Bool {

    // 1. Настройка
    DeferLink.configure(
        baseURL: "https://api.myapp.com",
        appURLScheme: "myapp"
    )

    // 2. Resolve при первом запуске
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
    public let promoId:     String?      // параметр promo_id из ссылки
    public let domain:      String?      // параметр domain
    public let sessionId:   String?
    public let appURL:      String?      // параметр app_scheme
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

### Полная конфигурация

```swift
DeferLink.configure(with: DeferLinkConfiguration(
    baseURL:              "https://api.myapp.com",
    appURLScheme:         "myapp",
    clipboardTokenPrefix: "deferlink",   // должен совпадать с CLIPBOARD_TOKEN_PREFIX
    safariResolveTimeout: 3.0,           // таймаут SFSafariViewController (сек)
    networkTimeout:       10.0,
    debugLogging:         true           // os.log, только для разработки
))
```

---

## Отслеживание событий

DeferLink включает встроенную систему аналитики событий в стиле AppsFlyer — без внешних зависимостей и без ежемесячных платежей. Все данные хранятся в вашей базе данных.

После успешного `resolveOnFirstLaunch` каждое событие **автоматически** получает атрибуционный контекст — `session_id` и `promo_id` прикрепляются к нему без дополнительных действий со стороны разработчика.

### Возможности

| Функция | Описание |
|---------|----------|
| 18 стандартных событий | `af_purchase`, `af_install`, `af_subscribe` и др. |
| Произвольные свойства | До 50 пар `[String: Any]` на событие |
| Отслеживание выручки | Поле `revenue` + валюта ISO 4217 |
| Офлайн-очередь | Персистентный буфер, события не теряются без сети |
| Дедупликация | UUID на клиенте, `INSERT OR IGNORE` на сервере |
| Воронки | Конверсия по цепочке событий в хронологическом порядке |
| Когортная выручка | Дневная выручка в разбивке по промо-акциям |
| Автоматическая атрибуция | `session_id` и `promo_id` прикрепляются ко всем событиям |

---

### Быстрый старт с событиями

```swift
// После configure + resolveOnFirstLaunch достаточно одной строки:
DeferLink.shared.logEvent(DLEventName.contentView)

// С выручкой
DeferLink.shared.logEvent(DLEventName.purchase, revenue: 29.99, currency: "USD")

// С произвольными свойствами
DeferLink.shared.logEvent(DLEventName.purchase, revenue: 29.99, currency: "USD", properties: [
    DLEventParam.orderId:   "ORD-1234",
    DLEventParam.contentId: "pro_annual"
])
```

---

### Установка user ID

Вызывайте один раз после авторизации. Все последующие события будут содержать этот идентификатор — это позволяет связывать события одного пользователя между сессиями и устройствами.

```swift
// После успешного входа в аккаунт
DeferLink.shared.setUserId(currentUser.id)
```

---

### Методы logEvent

SDK предоставляет три перегрузки под разные сценарии:

```swift
// 1. Событие без выручки (просмотр, навигация, действие)
DeferLink.shared.logEvent(_ eventName: String, properties: [String: Any]? = nil)

// 2. Событие с выручкой (покупка, подписка, донат)
DeferLink.shared.logEvent(_ eventName: String, revenue: Double, currency: String = "USD",
                           properties: [String: Any]? = nil)

// 3. Готовый объект DeferLinkEvent (максимальный контроль)
DeferLink.shared.logEvent(_ event: DeferLinkEvent)
```

---

### Вспомогательные фабрики

Для наиболее частых событий есть готовые конструкторы с говорящими сигнатурами:

```swift
// Покупка
DeferLink.shared.logEvent(.purchase(29.99, currency: "USD", properties: [
    DLEventParam.orderId: "ORD-1234",
    DLEventParam.contentId: "pro_annual"
]))

// Подписка
DeferLink.shared.logEvent(.subscribe(9.99, currency: "EUR"))

// Регистрация (method: apple | google | email | phone)
DeferLink.shared.logEvent(.registration(method: "apple"))
```

---

### Полный пример жизненного цикла

```swift
// ── AppDelegate.swift ────────────────────────────────────────────────────
import DeferLinkSDK

func application(_ application: UIApplication,
                 didFinishLaunchingWithOptions launchOptions: [...]) -> Bool {

    DeferLink.configure(baseURL: "https://api.myapp.com", appURLScheme: "myapp")

    DeferLink.shared.resolveOnFirstLaunch { result in
        // С этого момента session_id и promo_id автоматически
        // прикрепляются ко всем событиям — ничего настраивать не нужно
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
    DeferLink.shared.setUserId(user.id)          // привязать все события к пользователю
    DeferLink.shared.logEvent(.registration(method: user.authProvider))
}

// ── OnboardingViewController.swift ───────────────────────────────────────
func onboardingDidFinish() {
    DeferLink.shared.logEvent(DLEventName.tutorialCompletion)
}

// ── ProductViewController.swift ──────────────────────────────────────────
func viewDidAppear(_ animated: Bool) {
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

// ── PaymentViewController.swift ──────────────────────────────────────────
func paymentCompleted(order: Order) {
    DeferLink.shared.logEvent(
        DLEventName.purchase,
        revenue:    order.total,
        currency:   order.currency,
        properties: [
            DLEventParam.orderId:   order.id,
            DLEventParam.contentId: order.planId
        ]
    )
}
```

---

### Стандартные имена событий — DLEventName

| Константа | Значение | Описание |
|-----------|----------|----------|
| `DLEventName.install` | `af_install` | Первый запуск после установки |
| `DLEventName.launch` | `af_launch` | Запуск приложения |
| `DLEventName.completeRegistration` | `af_complete_registration` | Завершение регистрации |
| `DLEventName.login` | `af_login` | Авторизация |
| `DLEventName.purchase` | `af_purchase` | Покупка — используйте с `revenue` |
| `DLEventName.addToCart` | `af_add_to_cart` | Добавление товара в корзину |
| `DLEventName.addToWishlist` | `af_add_to_wishlist` | Добавление в список желаний |
| `DLEventName.initiatedCheckout` | `af_initiated_checkout` | Начало оформления заказа |
| `DLEventName.contentView` | `af_content_view` | Просмотр товара / статьи / экрана |
| `DLEventName.search` | `af_search` | Поиск в приложении |
| `DLEventName.subscribe` | `af_subscribe` | Оформление подписки — используйте с `revenue` |
| `DLEventName.levelAchieved` | `af_level_achieved` | Достижение уровня (игры) |
| `DLEventName.tutorialCompletion` | `af_tutorial_completion` | Завершение онбординга |
| `DLEventName.rate` | `af_rate` | Оценка приложения |
| `DLEventName.share` | `af_share` | Поделиться контентом |
| `DLEventName.invite` | `af_invite` | Приглашение друга (реферал) |
| `DLEventName.reEngage` | `af_re_engage` | Возврат пользователя |
| `DLEventName.update` | `af_update` | Обновление приложения |

---

### Стандартные ключи свойств — DLEventParam

| Константа | Ключ | Тип | Описание |
|-----------|------|:---:|----------|
| `DLEventParam.contentId` | `af_content_id` | `String` | ID товара, статьи или контента |
| `DLEventParam.contentType` | `af_content_type` | `String` | Тип контента (`product`, `article`) |
| `DLEventParam.price` | `af_price` | `Double` | Цена единицы |
| `DLEventParam.revenue` | `af_revenue` | `Double` | Выручка в свойствах (дублирует поле `revenue`) |
| `DLEventParam.quantity` | `af_quantity` | `Int` | Количество единиц |
| `DLEventParam.orderId` | `af_order_id` | `String` | ID заказа |
| `DLEventParam.level` | `af_level` | `Int` | Уровень (для игровых событий) |
| `DLEventParam.score` | `af_score` | `Int` | Очки / счёт |
| `DLEventParam.searchString` | `af_search_string` | `String` | Поисковый запрос пользователя |
| `DLEventParam.registrationMethod` | `af_registration_method` | `String` | Метод регистрации (`apple`, `google`, `email`) |

---

### Модель DeferLinkEvent

```swift
public struct DeferLinkEvent: Codable {
    // ── Идентификация ──────────────────────────────────────────────────
    public let eventId:    String   // UUID — ключ дедупликации на сервере
    public let eventName:  String   // имя события (стандартное или произвольное)
    public let timestamp:  String   // ISO 8601, время на клиенте

    // ── Атрибуция (заполняется SDK автоматически) ──────────────────────
    public var sessionId:  String?  // session_id из resolveOnFirstLaunch
    public var appUserId:  String?  // ID пользователя вашего приложения
    public var promoId:    String?  // promo_id из атрибуционной ссылки

    // ── Выручка ────────────────────────────────────────────────────────
    public var revenue:    Double?  // денежная сумма (только для purchase/subscribe)
    public var currency:   String   // ISO 4217, по умолчанию "USD"

    // ── Произвольные свойства ──────────────────────────────────────────
    public var properties: [String: AnyCodable]?  // до 50 пар ключ-значение

    // ── Контекст устройства (заполняется автоматически) ────────────────
    public var platform:   String   // "iOS"
    public var appVersion: String?  // CFBundleShortVersionString
    public var sdkVersion: String   // версия DeferLinkSDK
}
```

> `AnyCodable` — внутренний тип SDK, позволяет передавать `Bool`, `Int`, `Double`, `String`, `Array` и вложенные `[String: Any]` в поле `properties`.

---

### Офлайн-очередь и гарантия доставки

SDK гарантирует доставку событий даже при нестабильной сети:

```
Событие создано
       │
       ▼
  In-memory buffer
  (накапливается до 20 событий или 15 секунд)
       │
       ▼  batch flush
  POST /api/v1/events/batch
       │
  ┌────┴────────────────────────────────────┐
  │ Успех (2xx)                             │ Ошибка сети / 5xx
  │ ✓ события доставлены                   │
  │                                         ▼
  │                              Exponential back-off retry
  │                              попытка 1 →  1 сек
  │                              попытка 2 →  2 сек
  │                              попытка 3 →  4 сек
  │                                         │
  │                                         │ После 3 неудач
  │                                         ▼
  │                              Persist to disk
  │                              ~/ApplicationSupport/
  │                              com.deferlink.sdk.event_queue.json
  │                              (max 500 событий, FIFO-вытеснение)
  │                                         │
  │                                         ▼  при следующем запуске
  │                              Auto-flush on didBecomeActive
  └─────────────────────────────────────────┘
```

**Параметры поведения:**

| Параметр | Значение |
|----------|----------|
| Размер батча (память) | 20 событий |
| Интервал авто-сброса | 15 секунд |
| Flush при уходе в фон | ✓ `willResignActive` |
| Flush при возврате | ✓ `didBecomeActive` |
| Максимум персист. событий | 500 (FIFO-вытеснение старых) |
| Retry-стратегия | Exponential back-off, 3 попытки |
| Дедупликация | `event_id` UUID — `INSERT OR IGNORE` на сервере |

---

## API Reference

### `GET /dl` — Создать сессию

Основная точка входа для рекламных ссылок.

| Параметр | Обязательный | Описание |
|----------|:---:|----|
| `promo_id` | ✓ | ID кампании / промо-акции |
| `domain` | ✓ | Домен для идентификации |
| `timezone` | — | IANA timezone (`Europe/Moscow`) |
| `language` | — | Код языка (`ru_RU`) |
| `screen_size` | — | Разрешение экрана (`390x844`) |
| `model` | — | Модель устройства |
| `ttl` | — | Время жизни сессии в часах (default: 48) |

**Поведение в зависимости от User-Agent:**

| Браузер | Ответ |
|---------|-------|
| Safari (iOS) | `302` → App Store + `Set-Cookie: dl_session_id` |
| Facebook / Instagram IAB | `200` → HTML escape-страница (clipboard + redirect) |
| TikTok / WeChat IAB | `302` → App Store напрямую |
| Desktop | `200` → HTML страница с инструкциями |

---

### `POST /resolve` — Разрешить диплинк

Вызывается iOS SDK при первом запуске приложения.

**Request body:**
```json
{
  "fingerprint": {
    "model":                    "iPhone15,2",
    "language":                 "ru_RU",
    "timezone":                 "Europe/Moscow",
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
  "message":      "Сессия успешно разрешена"
}
```

---

### `GET /safari-resolve` — Cookie resolve

Вызывается SDK через невидимый `SFSafariViewController`. Читает cookie и редиректит в приложение:

```
Найден:     → myapp://resolved?session_id=<uuid>
Не найден:  → myapp://resolved?session_id=none
```

---

### `POST /api/v1/events` — Отправить событие

Отправка одного события. Используется для серверных интеграций или диагностики.

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

### `POST /api/v1/events/batch` — Батч событий

Отправка до 100 событий за один запрос. iOS SDK использует этот эндпоинт для всех плановых сбросов буфера.

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

| Поле | Описание |
|------|----------|
| `inserted` | Новых событий сохранено |
| `duplicate` | Пропущено событий с уже существующим `event_id` |
| `failed` | Отклонено событий (отсутствует `event_id` или `event_name`) |

---

### `GET /api/v1/events/stats` — Статистика событий

Агрегированные показатели за произвольный период с фильтрацией по промо-акции.

**Параметры запроса:**

| Параметр | Описание |
|----------|----------|
| `start` | Начало периода ISO 8601 (необязательно) |
| `end` | Конец периода ISO 8601 (необязательно) |
| `promo_id` | Фильтр по промо-акции (необязательно) |

**Пример:**
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
    { "event_name": "af_content_view",         "cnt": 612, "revenue": 0.0    },
    { "event_name": "af_add_to_cart",          "cnt": 289, "revenue": 0.0    },
    { "event_name": "af_initiated_checkout",   "cnt": 231, "revenue": 0.0    },
    { "event_name": "af_purchase",             "cnt": 214, "revenue": 8741.53},
    { "event_name": "af_complete_registration","cnt": 136, "revenue": 0.0    }
  ],
  "revenue_by_currency": [
    { "currency": "USD", "total": 7210.45 },
    { "currency": "EUR", "total": 1531.08 }
  ]
}
```

---

### `GET /api/v1/events/funnel` — Воронка конверсии

Пошаговый анализ конверсии. Для каждого шага подсчитывается количество пользователей, которые прошли **все предыдущие шаги в хронологическом порядке** — то есть не просто выполнили событие, а выполнили его после прохождения шага N-1.

**Параметры запроса:**

| Параметр | Описание |
|----------|----------|
| `steps` | Список имён событий в порядке воронки (2–10 шагов) |
| `start` | Начало периода (необязательно) |
| `end` | Конец периода (необязательно) |
| `promo_id` | Фильтр по промо-акции (необязательно) |

**Пример:**
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

| Поле | Описание |
|------|----------|
| `conversion_prev` | Конверсия из предыдущего шага, % |
| `conversion_total` | Общая конверсия от первого шага, % |

---

### `GET /api/v1/events/revenue` — Дневная выручка

Когортная выручка с разбивкой по дням, промо-акциям и валютам.

**Параметры запроса:**

| Параметр | По умолчанию | Описание |
|----------|:------:|----------|
| `promo_id` | — | Фильтр по промо-акции |
| `days` | `30` | Глубина истории (1–365 дней) |

**Пример:**
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

### `GET /api/v1/events/standard-events` — Список стандартных событий

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

## Конфигурация

```bash
# ── Безопасность (обязательно в production) ────────────────────────────────
SECRET_KEY=                    # min 32 символа
                               # python3 -c "import secrets; print(secrets.token_urlsafe(32))"
ENVIRONMENT=production         # development | production
CORS_ORIGINS=https://myapp.com
COOKIE_SECURE=true
COOKIE_SAMESITE=lax

# ── База данных ────────────────────────────────────────────────────────────
DATABASE_PATH=data/deeplinks.db

# ── Приложение ─────────────────────────────────────────────────────────────
APP_STORE_ID=1234567890        # числовой ID в App Store
APP_NAME=MyApp                 # отображается на escape-странице
APP_URL_SCHEME=myapp           # URL scheme (Info.plist)
CLIPBOARD_TOKEN_PREFIX=deferlink

# ── Сессии ─────────────────────────────────────────────────────────────────
DEFAULT_TTL_HOURS=48
CLEANUP_INTERVAL_MINUTES=30

# ── API ────────────────────────────────────────────────────────────────────
API_HOST=0.0.0.0
API_PORT=8000
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60

# ── Apple DeviceCheck (Tier 3) ─────────────────────────────────────────────
DEVICECHECK_ENABLED=true
DEVICECHECK_TEAM_ID=ABCDE12345
DEVICECHECK_KEY_ID=ABC123DEF456
DEVICECHECK_KEY_PATH=/secrets/AuthKey_ABC123DEF456.p8
DEVICECHECK_SANDBOX=false      # true для dev / staging

# ── Аналитика ──────────────────────────────────────────────────────────────
ENABLE_ANALYTICS=true
AUTO_OPTIMIZE_WEIGHTS=false    # авто-оптимизация весов алгоритма
LOG_LEVEL=INFO
```

---

## Архитектура проекта

```
deferlink/
├── app/
│   ├── main.py                    FastAPI приложение, /dl, /resolve, /safari-resolve
│   ├── config.py                  Конфигурация из env
│   ├── models.py                  Pydantic модели (FingerprintData, ResolveResponse)
│   ├── deeplink_handler.py        Оркестратор 4-уровневого matching
│   ├── database.py                SQLite менеджер + авторан миграций
│   ├── core/
│   │   ├── intelligent_matcher.py Fingerprint matching — Tier 4
│   │   ├── iab_detector.py        IAB detection + стратегия escape
│   │   ├── safari_escape.py       HTML escape-страница (clipboard + redirect)
│   │   ├── devicecheck.py         Apple DeviceCheck API client — Tier 3
│   │   └── event_tracker.py       Хранение событий, статистика, воронки, когорты
│   ├── api/
│   │   ├── deeplinks.py           POST /api/v1/resolve
│   │   ├── stats.py               GET  /api/v1/stats
│   │   ├── health.py              GET  /api/v1/health
│   │   └── events.py              POST /events /events/batch
│   │                              GET  /events/stats /events/funnel /events/revenue
│   └── migrations/
│       ├── add_devicecheck_fields.py
│       └── add_events_table.py    Таблица user_events (15 колонок, индексы)
│
├── DeferLinkSDK/                  iOS Swift Package
│   ├── Package.swift              swift-tools-version: 5.9, iOS 15+
│   └── Sources/DeferLinkSDK/
│       ├── DeferLink.swift            Публичный фасад (@MainActor singleton)
│       ├── DeferLinkConfiguration.swift
│       ├── DeferLinkLogger.swift      os.log
│       ├── Models/DeferLinkModels.swift
│       ├── Core/
│       │   ├── DeviceInfoCollector.swift  Железо, timezone, язык, экран
│       │   ├── FingerprintCollector.swift Clipboard + DeviceCheck + сборка
│       │   └── DeviceCheckManager.swift   DCDevice token + кэш 1ч
│       ├── Network/DeferLinkClient.swift  POST /resolve /events/batch, GET /safari-resolve
│       └── Events/
│           ├── DeferLinkEvent.swift   Модель + DLEventName + DLEventParam + AnyCodable
│           ├── EventQueue.swift       Offline-first очередь (Application Support JSON)
│           └── EventTracker.swift     Батчинг + retry + lifecycle observer
│
└── DeferLinkTestApp/              Пример интеграции SDK (SwiftUI)
```

---

## Безопасность

- **Без IDFA / ATT** — система не использует рекламные идентификаторы
- **Clipboard очищается** после прочтения токена (`UIPasteboard.general.string = ""`)
- **DeviceCheck токены** хранятся только как SHA-256 хэш, сырые токены не сохраняются
- **Сессии с TTL** — автоочистка каждые 30 минут
- **Rate limiting** — защита эндпоинтов от перебора
- **Fraud detection** — блокировка при > 100 запросов с одного IP в час
- **Event dedup** — UUID на клиенте предотвращает задвоения при ретраях

---

## Требования

| Компонент | Минимум |
|-----------|---------|
| Python | 3.10+ |
| iOS | 15.0+ |
| Xcode | 15+ |
| SQLite | 3.35+ (встроен в Python) |

---

## License

Apache 2.0.