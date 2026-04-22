<div align="center">

# DeferLink

**Self-hosted deferred deep linking — без зависимостей от Branch, AppsFlyer и Firebase**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![iOS](https://img.shields.io/badge/iOS-15+-000000?logo=apple&logoColor=white)](https://developer.apple.com)
[![Swift](https://img.shields.io/badge/Swift-5.9-FA7343?logo=swift&logoColor=white)](https://swift.org)
[![License](https://img.shields.io/badge/License-MIT-blue)](LICENSE)

[Быстрый старт](#быстрый-старт) · [Как работает](#как-работает) · [iOS SDK](#ios-sdk) · [API](#api-reference) · [Конфигурация](#конфигурация)

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
│   │   └── devicecheck.py         Apple DeviceCheck API client — Tier 3
│   ├── api/
│   │   ├── deeplinks.py           POST /api/v1/resolve
│   │   ├── stats.py               GET  /api/v1/stats
│   │   └── health.py              GET  /api/v1/health
│   └── migrations/
│       └── add_devicecheck_fields.py
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
│       └── Network/DeferLinkClient.swift  POST /resolve, GET /safari-resolve
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
