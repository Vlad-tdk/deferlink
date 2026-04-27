# DeferLink

**Self-hosted платформа мобильной атрибуции** — deferred deep linking, клоакинг, SKAdNetwork 4.0 и Facebook Conversions API в одном стеке. iOS SDK + Python-бэкенд, без сторонних MMP, полный контроль над данными.

> Языки: [English](README.md) · **Русский (этот файл)**
> Документация по модулям: [`doc/en/`](doc/en/) · [`doc/ru/`](doc/ru/)

---

## Что делает

| Возможность | Что получаете |
|---|---|
| **Deferred deep linking** | Пользователь кликает рекламу → ставит приложение → открывает → попадает на *нужный* промо-экран. Без paste, без ручных кодов. |
| **4-уровневый матчинг** | Clipboard-токен (100 %) → SFSafariViewController shared cookie (~99 %) → Apple DeviceCheck (~97 %) → fingerprint (60–90 %). |
| **Движок клоакинга** | IP / ASN / UA / поведенческое распознавание ботов, ad-ревьюеров и скраперов. SEO-страница или compliant-страница в зависимости от типа посетителя. |
| **SKAdNetwork 4.0** | 6-битная схема conversion-value `[revenue:3][engagement:2][flag:1]`, обработка PB1/PB2/PB3 и проверка подписи Apple ECDSA. |
| **Facebook Conversions API** | Автофорвардинг SKAN-постбэков и SDK-событий в Meta с дедупом и ретраями. |
| **Трекинг событий** | Стандартные AppsFlyer-события (`af_purchase`, `af_complete_registration`, …), воронки, cohort revenue, кастомные свойства. |

---

## Быстрый старт (5 минут)

### 1. Запустите бэкенд

```bash
git clone https://github.com/your-org/deferlink.git
cd deferlink

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Опционально — env-переменные (дефолты дружелюбные для разработки)
export API_HOST=0.0.0.0
export API_PORT=8000

python run.py
```

Сервер поднят на `http://localhost:8000`. Sanity check:

```bash
curl http://localhost:8000/api/v1/health/quick
# {"status":"ok"}
```

### 2. Подключите iOS SDK

В Xcode → **File → Add Package Dependencies…** → URL вашего форка `DeferLinkSDK`, или перетащите локальную папку `DeferLinkSDK/` как Swift-пакет.

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
            // переход на /promo/<promoId>
        }
    }
    return true
}

// SceneDelegate.swift
func scene(_ scene: UIScene, openURLContexts URLContexts: Set<UIOpenURLContext>) {
    URLContexts.forEach { DeferLink.shared.handleOpenURL($0.url) }
}
```

### 3. Трекинг событий (опционально)

```swift
DeferLink.shared.logEvent(.purchase(9.99, currency: "USD"))
DeferLink.shared.logEvent("af_complete_registration",
                          properties: ["method": "email"])
```

### 4. Прогон локально

Полный SwiftUI тест-харнес — `DeferLinkTestApp/`. Дёргает каждый эндпоинт и прогоняет детерминированные seed→resolve сценарии. Откройте `DeferLinkTestApp.xcodeproj`, прицельте `NetworkManager.baseURL` в свой сервер (`http://127.0.0.1:8000` для iOS Simulator) и тапните *Run All Tests*.

Подробные шаги установки / запуска / тестов — [`doc/ru/install-and-test.md`](doc/ru/install-and-test.md).

---

## Архитектура одним взглядом

```
                ┌──────────────────────────────────────────┐
  клик       →  │  /dl?promo_id=…&domain=…  (cloaking gate) │
  по рекламе    │      ├── bot / reviewer → SEO_PAGE         │
                │      └── real user      → /escape (Safari) │
                │           └── clipboard write + App Store  │
                └──────────────────────────────────────────┘
                                     │
                          юзер ставит и открывает app
                                     ▼
                ┌──────────────────────────────────────────┐
  первый      │  POST /resolve                              │
  запуск  →   │   ├── tier 1: clipboard_token               │
                │   ├── tier 2: safari_cookie_session_id      │
                │   ├── tier 3: device_check_token            │
                │   └── tier 4: fingerprint (timezone + …)    │
                │      → возвращает promo_id, session_id      │
                └──────────────────────────────────────────┘
                                     │
                ┌──────────────────────────────────────────┐
  in-app     │  POST /api/v1/events/batch                  │
  события →  │   • дедуп по event_id                       │
                │   • форвард в Facebook CAPI                 │
                │  Apple postback → /api/v1/skadnetwork/…     │
                │   • парсинг + верификация подписи + CV      │
                │   • форвард в Facebook CAPI                 │
                └──────────────────────────────────────────┘
```

Подробный обзор с границами модулей, моделью потоков и схемой БД — в [`doc/ru/architecture.md`](doc/ru/architecture.md).

---

## Карта модулей

| Подсистема | Код | Документация |
|---|---|---|
| HTTP API | `app/api/`, `app/main.py` | [`doc/ru/api-reference.md`](doc/ru/api-reference.md) |
| Deferred deep links | `app/deeplink_handler.py`, `app/core/intelligent_matcher.py`, `app/core/safari_escape.py` | [`doc/ru/backend.md`](doc/ru/backend.md) |
| Клоакинг | `app/core/cloaking/` | [`doc/ru/cloaking.md`](doc/ru/cloaking.md) |
| SKAdNetwork | `app/core/skadnetwork/` | [`doc/ru/skadnetwork.md`](doc/ru/skadnetwork.md) |
| Facebook CAPI | `app/core/capi/` | [`doc/ru/capi.md`](doc/ru/capi.md) |
| iOS SDK | `DeferLinkSDK/Sources/DeferLinkSDK/` | [`doc/ru/sdk-ios.md`](doc/ru/sdk-ios.md) |

Английские версии — [`doc/en/`](doc/en/).

---

## Шпаргалка по конфигу

Все настройки — из переменных окружения. Полный список — `app/config.py`.

| Переменная | Default | Заметки |
|---|---|---|
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8000` | Bind. Для iOS Simulator целиться в `127.0.0.1`. |
| `DATABASE_PATH` | `data/deeplinks.db` | SQLite-файл. |
| `DEFAULT_TTL_HOURS` | `48` | Время жизни browser-сессии до cleanup. |
| `SECRET_KEY` | `dev-secret-key-…` | **Поменять на проде**, ≥32 символов. |
| `ENVIRONMENT` | `development` | `production` включает строгую валидацию. |
| `DEVICECHECK_ENABLED` | `false` | Серверная проверка Apple DeviceCheck. |
| `DEVICECHECK_TEAM_ID` / `_KEY_ID` / `_KEY_PATH` | — | Креды Apple Developer, файл `.p8`. |
| `APP_STORE_ID` | — | Для meta-тега escape-страницы. |
| `APP_URL_SCHEME` | `deferlink` | Должен совпадать с SDK `appURLScheme` и `Info.plist`. |
| `CAPI_RETRY_INTERVAL_SECONDS` | `60` | Тик фонового CAPI-ретрая. |
| `LOG_LEVEL` | `INFO` | `DEBUG` включает `uvicorn --reload`. |

Чек-лист продакшена — [`doc/ru/install-and-test.md`](doc/ru/install-and-test.md#4-чек-лист-продакшена).

---

## Запуск тестов

```bash
pytest                          # юнит + интеграционные тесты бэкенда
pytest tests/test_deeplinks.py  # один модуль
```

iOS SDK и тест-харнес — открыть Xcode-воркспейс и запустить test plan, шаги — [`doc/ru/install-and-test.md`](doc/ru/install-and-test.md#тесты-ios-sdk).

---

## Статус и версионирование

* iOS SDK: **1.0.0** (`DeferLinkSDKInfo.version`)
* CV-схема: **`rev3_eng2_flag1`** (стабильный wire-контракт — никогда не ломается)
* Сервер: stateless воркеры + SQLite. Drop-in Postgres — в roadmap.

---

## Сотрудничество, интеграции, кастомные сборки

По коммерческим интеграциям, адаптерам ad-сетей, кастомным CV-схемам, on-prem-разворачиванию и всему, что не вошло в доку:

* 📧 **Email** — [tdk@null.net](mailto:tdk@null.net)
* 📨 **Telegram** — [@smail_ios](https://t.me/smail_ios)

Issues / PR, не требующие приватного обсуждения, — на GitHub.

---

## Лицензия

См. [`LICENSE`](LICENSE).
