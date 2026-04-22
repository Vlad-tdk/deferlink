<div align="center">

# DeferLink

**Self-hosted deferred deep linking — без зависимостей от Branch, AppsFlyer и Firebase**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![iOS](https://img.shields.io/badge/iOS-15+-000000?logo=apple&logoColor=white)](https://developer.apple.com)
[![Swift](https://img.shields.io/badge/Swift-5.9-FA7343?logo=swift&logoColor=white)](https://swift.org)
[![License](https://img.shields.io/badge/License-MIT-blue)](LICENSE)

[Быстрый старт](#быстрый-старт) · [Как работает](#как-работает) · [iOS SDK](#ios-sdk) · [API](#api-reference) · [Отслеживание событий](#отслеживание-событий-event-tracking) · [Конфигурация](#конфигурация)

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
    "model":                   "iPhone15,2",
    "language":                "ru_RU",
    "timezone":                "Europe/Moscow",
    "user_agent":              "MyApp/1.0 (iOS 17.0; iPhone15,2)",
    "screen_width":            390,
    "screen_height":           844,
    "platform":                "iOS",
    "app_version":             "2.1.0",
    "idfv":                    "12345678-1234-1234-1234-123456789ABC",
    "clipboard_token":         "deferlink:550e8400-e29b-41d4-a716-446655440000",
    "device_check_token":      "base64encodedtoken==",
    "safari_cookie_session_id":"550e8400-e29b-41d4-a716-446655440000",
    "is_first_launch":         true
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

## Отслеживание событий (Event Tracking)

### Обзор

DeferLink включает встроенную систему отслеживания событий, спроектированную по образцу API AppsFlyer. Это означает, что имена событий и ключи параметров полностью совместимы с AppsFlyer — при необходимости переключить SDK вы не переписываете аналитику.

**Что входит в систему из коробки:**

- **Offline-first очередь** — события не теряются при отсутствии сети; батч отправляется автоматически или вручную
- **Дедупликация** — каждое событие получает уникальный `event_id` (UUID v4); сервер игнорирует повторы через `INSERT OR IGNORE`
- **Автоматическая атрибуция** — после вызова `resolveOnFirstLaunch` поля `session_id` и `promo_id` проставляются во все события без участия разработчика
- **Батчинг** — события накапливаются в памяти и отправляются пачкой (до 20 штук или раз в 15 секунд, в зависимости от того, что наступит раньше)
- **Lifecycle-aware** — автоматический сброс очереди при уходе приложения в фон, автоматический ретрай при возвращении

---

### iOS SDK — logEvent API

#### Базовый вызов

```swift
// Произвольное имя события + произвольные свойства
DeferLink.shared.logEvent("af_content_view", properties: [
    "content_id":   "article_42",
    "content_type": "blog_post",
    "category":     "technology"
])
```

#### Событие с выручкой

```swift
// Покупка с revenue и currency
DeferLink.shared.logEvent(
    "af_purchase",
    revenue:    29.99,
    currency:   "USD",
    properties: [
        "af_order_id":      "ORD-2024-00123",
        "af_content_id":    "premium_plan",
        "af_quantity":      1,
        "af_content_type":  "subscription"
    ]
)
```

#### Convenience factory — предустановленные события

Для стандартных событий доступны типобезопасные фабричные методы через `DLEventName`:

```swift
// Покупка — короткая запись
DeferLink.shared.logEvent(.purchase(29.99, currency: "USD"))

// Регистрация
DeferLink.shared.logEvent(.registration(method: "apple"))

// Вход
DeferLink.shared.logEvent(.login(method: "google"))

// Просмотр контента
DeferLink.shared.logEvent(.contentView(contentId: "article_42", contentType: "blog_post"))

// Добавление в корзину
DeferLink.shared.logEvent(.addToCart(contentId: "sku_7890", price: 9.99, currency: "USD"))

// Начало оформления заказа
DeferLink.shared.logEvent(.initiatedCheckout(totalPrice: 59.97, currency: "USD", numItems: 3))

// Поиск
DeferLink.shared.logEvent(.search(query: "swift programming"))

// Достижение уровня
DeferLink.shared.logEvent(.levelAchieved(level: 15, score: 4200))

// Завершение обучения
DeferLink.shared.logEvent(.tutorialCompletion(success: true))
```

#### Установка user ID

После авторизации пользователя передайте его идентификатор один раз — он будет автоматически включаться во все последующие события:

```swift
// Вызывается один раз после логина / регистрации
DeferLink.shared.setUserId("user_42")
```

#### Принудительный сброс очереди

```swift
// Немедленно отправить все накопленные события на сервер
DeferLink.shared.flushEvents()

// async-вариант с ожиданием результата
await DeferLink.shared.flushEvents()
```

---

### Стандартные имена событий (DLEventName)

`DLEventName` — перечисление, значения которого соответствуют стандартным именам событий AppsFlyer. Использование констант исключает опечатки в строках.

| Константа | Строковое значение | Описание |
|-----------|-------------------|----------|
| `.install` | `af_install` | Первый запуск приложения после установки |
| `.launch` | `af_launch` | Каждый последующий запуск приложения |
| `.completeRegistration` | `af_complete_registration` | Завершение регистрации нового аккаунта |
| `.login` | `af_login` | Вход в существующий аккаунт |
| `.purchase` | `af_purchase` | Завершённая покупка (IAP или платёж) |
| `.addToCart` | `af_add_to_cart` | Добавление товара в корзину |
| `.addToWishlist` | `af_add_to_wishlist` | Добавление товара в список желаний |
| `.initiatedCheckout` | `af_initiated_checkout` | Начало оформления заказа |
| `.contentView` | `af_content_view` | Просмотр экрана продукта / статьи |
| `.search` | `af_search` | Поисковый запрос внутри приложения |
| `.subscribe` | `af_subscribe` | Оформление подписки |
| `.levelAchieved` | `af_level_achieved` | Достижение нового уровня (игры) |
| `.tutorialCompletion` | `af_tutorial_completion` | Завершение обучающего тура |
| `.rate` | `af_rate` | Оценка приложения или контента |
| `.share` | `af_share` | Публикация / отправка контента |
| `.invite` | `af_invite` | Отправка реферального приглашения |
| `.reEngage` | `af_re_engage` | Возврат пользователя через пуш или диплинк |
| `.update` | `af_update` | Обновление приложения до новой версии |

---

### Стандартные ключи параметров (DLEventParam)

`DLEventParam` содержит типобезопасные строковые константы для ключей словаря `properties`:

| Константа | Строковое значение | Тип значения | Описание |
|-----------|-------------------|:------------:|----------|
| `.contentId` | `af_content_id` | `String` | Уникальный ID товара, статьи или контента |
| `.contentType` | `af_content_type` | `String` | Тип контента (`product`, `article`, `video`) |
| `.revenue` | `af_revenue` | `Double` | Выручка в указанной валюте |
| `.price` | `af_price` | `Double` | Цена одной единицы товара |
| `.quantity` | `af_quantity` | `Int` | Количество единиц товара |
| `.orderId` | `af_order_id` | `String` | Уникальный идентификатор заказа |
| `.level` | `af_level` | `Int` | Номер уровня (для игровых событий) |
| `.score` | `af_score` | `Int` | Количество очков / счёт |
| `.searchString` | `af_search_string` | `String` | Поисковый запрос |
| `.registrationMethod` | `af_registration_method` | `String` | Способ регистрации (`email`, `apple`, `google`) |

Пример использования констант:

```swift
DeferLink.shared.logEvent("af_purchase", properties: [
    DLEventParam.contentId:   "sku_7890",
    DLEventParam.contentType: "physical_good",
    DLEventParam.revenue:     49.99,
    DLEventParam.quantity:    2,
    DLEventParam.orderId:     "ORD-2024-00456"
])
```

---

### Модель события — DeferLinkEvent

Каждое событие, созданное через `logEvent`, представляется следующей структурой перед отправкой на сервер:

```swift
public struct DeferLinkEvent: Codable {
    /// UUID v4 — уникальный идентификатор события.
    /// Используется сервером для дедупликации (INSERT OR IGNORE).
    /// Повторная отправка одного и того же события безопасна.
    public let event_id: String

    /// Имя события (например, "af_purchase").
    public let event_name: String

    /// ISO 8601 timestamp в UTC — момент создания события на устройстве,
    /// а не момент получения сервером.
    public let timestamp: String

    /// UUID сессии атрибуции, полученный после resolveOnFirstLaunch.
    /// Проставляется автоматически — разработчик не передаёт его явно.
    public let session_id: String?

    /// Идентификатор пользователя, установленный через setUserId(_:).
    /// nil до первого вызова setUserId или в анонимном режиме.
    public let app_user_id: String?

    /// promo_id из разрешённой сессии (например, "SUMMER24").
    /// Проставляется автоматически из результата атрибуции.
    public let promo_id: String?

    /// Выручка в числовом формате. Всегда передавайте вместе с currency.
    public let revenue: Double?

    /// Трёхбуквенный код валюты ISO 4217 (например, "USD", "RUB").
    public let currency: String?

    /// Произвольные параметры события — не более 50 пар ключ-значение.
    /// Ключи: String. Значения: String, Int, Double или Bool.
    public let properties: [String: AnyCodable]

    /// Платформа устройства. Всегда "iOS" для Swift SDK.
    public let platform: String

    /// Версия приложения из CFBundleShortVersionString.
    public let app_version: String

    /// Версия DeferLink SDK.
    public let sdk_version: String
}
```

---

### Offline-очередь

SDK никогда не теряет события — даже при отсутствии сети.

#### Буферизация и батчинг

- Новые события помещаются в **in-memory очередь**
- Батч отправляется автоматически при достижении **20 событий** или по истечении **15 секунд** — в зависимости от того, что наступит раньше
- Размер батча при отправке на сервер — до **100 событий** (несколько накопленных батчей могут объединяться)

#### Персистентность

- Если отправка батча завершилась ошибкой (нет сети, сервер недоступен), события **сохраняются в JSON-файл** в директории `Application Support`
- Путь файла: `<Application Support>/com.deferlink/event_queue.json`
- Максимальный размер хранилища: **500 событий**; при переполнении удаляются самые старые (FIFO)

#### Lifecycle-хуки

| Событие приложения | Действие SDK |
|--------------------|-------------|
| `willResignActive` | Принудительный сброс всей очереди на сервер |
| `didBecomeActive` | Попытка отправить ранее сохранённые события |

#### Ретрай с экспоненциальной задержкой

При неудачной отправке SDK повторяет попытку с задержкой `2^n` секунд (1, 2, 4 секунды). Максимальное число попыток — **3**. После исчерпания попыток событие остаётся в персистентном хранилище и будет отправлено при следующем запуске.

#### Дедупликация

Каждое событие несёт уникальный `event_id` (UUID v4), сгенерированный на устройстве в момент создания. Сервер использует `INSERT OR IGNORE` — повторно полученное событие с тем же `event_id` молча игнорируется. Это означает, что ретраи и дублирующиеся вызовы со стороны SDK абсолютно безопасны.

---

### Автоматическое проставление атрибуции

После того как `resolveOnFirstLaunch` (или `resolve()`) завершится успешно, SDK сохраняет `session_id` и `promo_id` в Keychain. Начиная с этого момента оба поля **автоматически** включаются в каждое последующее событие — разработчику ничего дополнительно делать не нужно.

**Пример полного потока:**

```
1. Пользователь кликает рекламу с promo_id=SUMMER24
2. DeferLink.shared.resolveOnFirstLaunch вызван при запуске
   → SDK получает: session_id = "abc-123", promo_id = "SUMMER24"
   → Оба значения сохранены в Keychain

3. Пользователь регистрируется:
   DeferLink.shared.setUserId("user_42")
   DeferLink.shared.logEvent(.registration(method: "apple"))

   Событие, отправленное на сервер:
   {
     "event_name":  "af_complete_registration",
     "session_id":  "abc-123",        ← проставлен автоматически
     "promo_id":    "SUMMER24",       ← проставлен автоматически
     "app_user_id": "user_42",        ← установлен через setUserId
     "properties":  { "af_registration_method": "apple" }
   }

4. Пользователь совершает покупку:
   DeferLink.shared.logEvent(.purchase(29.99, currency: "USD"))

   → session_id и promo_id снова проставлены автоматически.
   → Аналитика в /api/v1/events/revenue корректно атрибутирует
     выручку кампании SUMMER24 без дополнительного кода.
```

---

### Полный пример интеграции

```swift
import DeferLinkSDK

// ── AppDelegate.swift ──────────────────────────────────────────────────────

func application(_ application: UIApplication,
                 didFinishLaunchingWithOptions launchOptions: [...]) -> Bool {

    // 1. Конфигурация SDK
    DeferLink.configure(with: DeferLinkConfiguration(
        baseURL:      "https://api.myapp.com",
        appURLScheme: "myapp",
        debugLogging: false
    ))

    // 2. Разрешение диплинка при первом запуске
    //    После завершения session_id и promo_id начнут автоматически
    //    проставляться во все события.
    DeferLink.shared.resolveOnFirstLaunch { result in
        guard let result, result.matched else { return }

        switch result.promoId {
        case "summer24":  AppRouter.showSummerPromo()
        case "referral":  AppRouter.showReferral(code: result.domain)
        default:          break
        }
    }

    return true
}

// ── После успешного логина ─────────────────────────────────────────────────

func onLoginSuccess(userId: String, method: String) {
    // 3. Передать идентификатор пользователя
    DeferLink.shared.setUserId(userId)

    // 4. Залогировать событие — session_id и promo_id будут добавлены автоматически
    DeferLink.shared.logEvent(.login(method: method))
}

// ── Покупка ────────────────────────────────────────────────────────────────

func onPurchaseCompleted(orderId: String, amount: Double, currency: String) {
    DeferLink.shared.logEvent(
        "af_purchase",
        revenue:    amount,
        currency:   currency,
        properties: [
            DLEventParam.orderId:     orderId,
            DLEventParam.contentType: "subscription"
        ]
    )
}

// ── Принудительный сброс (например, перед выходом из аккаунта) ────────────

func onLogout() {
    Task {
        await DeferLink.shared.flushEvents()
    }
}
```

---

### API событий

#### `POST /api/v1/events` — Отправить одиночное событие

**Request:**
```json
{
  "event_id":    "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "event_name":  "af_purchase",
  "timestamp":   "2024-08-15T14:32:00Z",
  "session_id":  "550e8400-e29b-41d4-a716-446655440000",
  "app_user_id": "user_42",
  "promo_id":    "SUMMER24",
  "revenue":     29.99,
  "currency":    "USD",
  "properties": {
    "af_order_id":     "ORD-2024-00123",
    "af_content_id":   "premium_plan",
    "af_content_type": "subscription",
    "af_quantity":     1
  },
  "platform":    "iOS",
  "app_version": "2.1.0",
  "sdk_version": "1.0.0"
}
```

**Response:**
```json
{
  "success":    true,
  "event_id":   "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "duplicate":  false,
  "message":    "Событие записано"
}
```

> Если событие с таким `event_id` уже существует, поле `duplicate` будет `true`, а HTTP-статус останется `200` — это не ошибка.

---

#### `POST /api/v1/events/batch` — Отправить батч событий

Максимум **100 событий** за один запрос. Именно этот эндпоинт использует SDK при автоматической отправке очереди.

**Request:**
```json
{
  "events": [
    {
      "event_id":   "f47ac10b-58cc-4372-a567-0e02b2c3d479",
      "event_name": "af_content_view",
      "timestamp":  "2024-08-15T14:30:00Z",
      "session_id": "550e8400-e29b-41d4-a716-446655440000",
      "promo_id":   "SUMMER24",
      "properties": { "af_content_id": "article_42" },
      "platform":   "iOS",
      "app_version":"2.1.0",
      "sdk_version": "1.0.0"
    },
    {
      "event_id":   "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "event_name": "af_purchase",
      "timestamp":  "2024-08-15T14:32:00Z",
      "session_id": "550e8400-e29b-41d4-a716-446655440000",
      "promo_id":   "SUMMER24",
      "app_user_id":"user_42",
      "revenue":    29.99,
      "currency":   "USD",
      "properties": { "af_order_id": "ORD-2024-00123" },
      "platform":   "iOS",
      "app_version":"2.1.0",
      "sdk_version": "1.0.0"
    }
  ]
}
```

**Response:**
```json
{
  "success":    true,
  "total":      2,
  "inserted":   1,
  "duplicates": 1,
  "failed":     0,
  "errors":     []
}
```

---

#### `GET /api/v1/events/stats` — Агрегированная статистика

Параметры запроса:

| Параметр | Обязательный | Описание |
|----------|:---:|---------|
| `start` | — | Начало периода (ISO 8601, UTC). По умолчанию: 30 дней назад |
| `end` | — | Конец периода (ISO 8601, UTC). По умолчанию: текущий момент |
| `promo_id` | — | Фильтр по кампании |

```bash
GET /api/v1/events/stats?start=2024-08-01T00:00:00Z&end=2024-08-31T23:59:59Z&promo_id=SUMMER24
```

**Response:**
```json
{
  "period": {
    "start": "2024-08-01T00:00:00Z",
    "end":   "2024-08-31T23:59:59Z"
  },
  "filters": {
    "promo_id": "SUMMER24"
  },
  "summary": {
    "total_events":        4821,
    "unique_users":         943,
    "unique_sessions":      987,
    "total_revenue":      18430.57,
    "currency":           "USD",
    "avg_revenue_per_user": 19.54
  },
  "by_event": [
    { "event_name": "af_content_view",        "count": 2104, "unique_users": 901 },
    { "event_name": "af_add_to_cart",         "count":  876, "unique_users": 621 },
    { "event_name": "af_initiated_checkout",  "count":  543, "unique_users": 498 },
    { "event_name": "af_purchase",            "count":  412, "unique_users": 389 }
  ]
}
```

---

#### `GET /api/v1/events/funnel` — Воронка конверсии

Параметры запроса (повторяющийся `steps`):

```bash
GET /api/v1/events/funnel?steps=af_content_view&steps=af_add_to_cart&steps=af_purchase&promo_id=SUMMER24
```

**Response:**
```json
{
  "promo_id": "SUMMER24",
  "funnel": [
    {
      "step":          1,
      "event_name":    "af_content_view",
      "users":         901,
      "conversion":    100.0,
      "drop_off":      0.0
    },
    {
      "step":          2,
      "event_name":    "af_add_to_cart",
      "users":         621,
      "conversion":    68.9,
      "drop_off":      31.1
    },
    {
      "step":          3,
      "event_name":    "af_purchase",
      "users":         389,
      "conversion":    43.2,
      "drop_off":      56.8
    }
  ],
  "overall_conversion": 43.2
}
```

---

#### `GET /api/v1/events/revenue` — Когортная выручка по дням

```bash
GET /api/v1/events/revenue?promo_id=SUMMER24&days=30
```

**Response:**
```json
{
  "promo_id": "SUMMER24",
  "days":     30,
  "currency": "USD",
  "total_revenue": 18430.57,
  "daily": [
    { "date": "2024-08-01", "revenue": 412.50,  "transactions": 14, "unique_users": 12 },
    { "date": "2024-08-02", "revenue": 687.25,  "transactions": 23, "unique_users": 21 },
    { "date": "2024-08-03", "revenue": 530.00,  "transactions": 18, "unique_users": 16 },
    { "date": "...",        "revenue": "...",    "transactions":  0, "unique_users":  0 }
  ]
}
```

---

#### `GET /api/v1/events/standard-events` — Список стандартных событий

```bash
GET /api/v1/events/standard-events
```

**Response:**
```json
{
  "events": [
    { "name": "af_install",               "description": "Первый запуск после установки" },
    { "name": "af_launch",                "description": "Каждый последующий запуск" },
    { "name": "af_complete_registration", "description": "Завершение регистрации" },
    { "name": "af_login",                 "description": "Вход в аккаунт" },
    { "name": "af_purchase",              "description": "Завершённая покупка" },
    { "name": "af_add_to_cart",           "description": "Добавление в корзину" },
    { "name": "af_add_to_wishlist",       "description": "Добавление в список желаний" },
    { "name": "af_initiated_checkout",    "description": "Начало оформления заказа" },
    { "name": "af_content_view",          "description": "Просмотр контента" },
    { "name": "af_search",                "description": "Поисковый запрос" },
    { "name": "af_subscribe",             "description": "Оформление подписки" },
    { "name": "af_level_achieved",        "description": "Достижение уровня" },
    { "name": "af_tutorial_completion",   "description": "Завершение обучения" },
    { "name": "af_rate",                  "description": "Оценка контента" },
    { "name": "af_share",                 "description": "Публикация контента" },
    { "name": "af_invite",                "description": "Реферальное приглашение" },
    { "name": "af_re_engage",             "description": "Возврат пользователя" },
    { "name": "af_update",                "description": "Обновление приложения" }
  ]
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
│   ├── database.py                SQLite менеджер
│   ├── core/
│   │   ├── intelligent_matcher.py Fingerprint matching — Tier 4
│   │   ├── iab_detector.py        IAB detection + стратегия escape
│   │   ├── safari_escape.py       HTML escape-страница (clipboard + redirect)
│   │   ├── devicecheck.py         Apple DeviceCheck API client — Tier 3
│   │   └── event_tracker.py       Хранение и аналитика событий
│   ├── api/
│   │   ├── deeplinks.py           POST /api/v1/resolve
│   │   ├── stats.py               GET  /api/v1/stats
│   │   ├── health.py              GET  /api/v1/health
│   │   └── events.py              POST /events, /events/batch, /stats, /funnel, /revenue
│   └── migrations/
│       ├── add_devicecheck_fields.py
│       └── add_events_table.py
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
│       ├── Network/DeferLinkClient.swift  POST /resolve, GET /safari-resolve
│       └── Events/
│           ├── DeferLinkEvent.swift       Модель события + DLEventName + DLEventParam
│           ├── EventQueue.swift           Offline-first очередь (Application Support JSON)
│           └── EventTracker.swift         Батчинг + retry + lifecycle observer
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

MIT
