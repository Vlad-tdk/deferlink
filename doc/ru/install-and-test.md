# Установка, запуск и тестирование

В этом документе:

1. Локальный запуск бэкенда
2. Подключение iOS SDK к нему
3. Прогон автоматических тестов
4. Чек-лист продакшена

## Требования

* Python 3.10+ (используется `from __future__ import annotations` и PEP 604 union-ы)
* macOS / Linux (Windows работает, но не проверяется регулярно)
* Xcode 15+ для SDK и тест-харнеса
* iOS 14.0+ на симуляторе или устройстве

## 1. Бэкенд

```bash
git clone https://github.com/your-org/deferlink.git
cd deferlink

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

`requirements.txt` намеренно крошечный:

```
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
python-multipart==0.0.6
python-dotenv==1.0.0
httpx==0.26.0
cryptography==42.0.5
```

### Запуск

```bash
python run.py
```

`run.py` валидирует конфиг, потом запускает `uvicorn` с `app.main:app`. Bind берётся из `API_HOST` / `API_PORT` (по умолчанию `0.0.0.0:8000`).

Sanity check:

```bash
curl http://localhost:8000/api/v1/health/quick
# {"status":"ok"}

curl http://localhost:8000/api/v1/health
# {"status":"ok","db":"ok","version":"..."}
```

Первый запуск создаёт `data/deeplinks.db` и автоматически прогоняет миграции из `app/migrations/` — они идемпотентны, повторный старт безопасен.

### Конфигурация

Все настройки — в `app/config.py`. Дефолты дружелюбные для разработки. Самые важные:

| Переменная | Default | Заметки |
|---|---|---|
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8000` | Bind. Из iOS Simulator целиться на `127.0.0.1`. |
| `API_WORKERS` | `1` | ≥2 имеет смысл только с реальной БД. SQLite — single writer. |
| `DATABASE_PATH` | `data/deeplinks.db` | SQLite-файл. Директория должна быть писабельной. |
| `DEFAULT_TTL_HOURS` | `48` | Время жизни browser-сессии до cleanup. Диапазон 1–168. |
| `CLEANUP_INTERVAL_MINUTES` | `5` | Частота фоновой чистки. |
| `SECRET_KEY` | dev-secret | **Поменять на проде**, ≥32 символа, не из чёрного списка. |
| `ENVIRONMENT` | `development` | `production` включает строгий `validate_config()`. |
| `COOKIE_SECURE` | `false` | `true` после переезда на HTTPS. |
| `COOKIE_SAMESITE` | `lax` | `lax|strict|none`. `none` только с `COOKIE_SECURE=true`. |
| `CORS_ORIGINS` | `*` | Список через запятую. |
| `TRUST_PROXY_HEADERS` | `false` | За nginx/Cloudflare ставьте `true` — будут уважаться `X-Forwarded-For`. |
| `LOG_LEVEL` | `INFO` | `DEBUG` включает `uvicorn --reload`. |
| `APP_STORE_ID` | — | iTunes app id для meta-тегов escape-страницы. |
| `APP_NAME` | — | Видимое имя на escape-странице. |
| `APP_URL_SCHEME` | `deferlink` | Должен совпадать с SDK `appURLScheme` и `Info.plist`. |
| `CLIPBOARD_TOKEN_PREFIX` | `deferlink` | Должен совпадать с SDK `clipboardTokenPrefix`. |
| `DEVICECHECK_ENABLED` | `false` | Tier-3 атрибуция. |
| `DEVICECHECK_TEAM_ID` / `_KEY_ID` / `_KEY_PATH` | — | Креды Apple Developer, файл `.p8`. |
| `DEVICECHECK_SANDBOX` | `true` | На проде — `false`. |
| `CAPI_RETRY_INTERVAL_SECONDS` | `300` | Частота ретрая CAPI. |
| `AUTO_OPTIMIZE_WEIGHTS` | `false` | Опционально: периодический пересчёт весов матчера. |

Локальная настройка:

```bash
export DATABASE_PATH=./data/dev.db
export DEFAULT_TTL_HOURS=72
export LOG_LEVEL=DEBUG
python run.py
```

## 2. iOS SDK

### Как Swift Package

В Xcode → **File → Add Package Dependencies…** → URL форка `DeferLinkSDK` или перетащите локальный `DeferLinkSDK/` как пакет в workspace.

### Минимальная интеграция

```swift
// AppDelegate.swift (или @main App init)
import DeferLinkSDK

DeferLink.configure(
    baseURL:      "http://127.0.0.1:8000",   // simulator: 127.0.0.1; устройство: ваш LAN IP
    appURLScheme: "myapp",                    // должен совпадать с Info.plist URL Types
    debugLogging: true
)

DeferLink.shared.resolveOnFirstLaunch { result in
    if let promoId = result?.promoId {
        // переход на /promo/<promoId>
    }
}

// SceneDelegate.swift
func scene(_ scene: UIScene, openURLContexts URLContexts: Set<UIOpenURLContext>) {
    URLContexts.forEach { DeferLink.shared.handleOpenURL($0.url) }
}
```

Опционально события + SKAN:

```swift
DeferLink.shared.logEvent(.purchase(9.99, currency: "USD"))
DeferLink.shared.enableSKAdNetwork(appId: "1234567890")
```

В `Info.plist` должен быть URL-схема:

```xml
<key>CFBundleURLTypes</key>
<array>
  <dict>
    <key>CFBundleURLSchemes</key>
    <array><string>myapp</string></array>
  </dict>
</array>
```

Полный референс SDK — [`sdk-ios.md`](sdk-ios.md).

## 3. Тесты

### Бэкенд

```bash
pytest                                    # все тесты
pytest tests/test_deeplink_handler.py     # один модуль
pytest -k capi                            # по ключевому слову
pytest -v --tb=short                      # подробно с короткими трейсбэками
```

Текущие сьюты в `tests/`:

| Файл | Покрытие |
|---|---|
| `test_main_flow.py` | end-to-end `/dl` → `/resolve` happy paths |
| `test_deeplink_handler.py` | четырёхуровневый матч `DeepLinkHandler` |
| `test_event_tracker.py` | вставка событий, batch dedup, stats, funnels, cohort revenue |
| `test_capi.py` | `CAPIService.forward`, расписание ретраев, дедуп |
| `test_cv_schema.py` | round-trip битпак, границы бакетов |
| `test_postback_parser.py` | парсинг SKAN v3/v4, верификация подписи |
| `test_campaign_decoder.py` | разрешение правил декодера, маппинг coarse-CV |
| `test_skan_service.py` | приём постбэков + дедуп + распределение |
| `test_devicecheck.py` | degraded mode верификатора DeviceCheck |
| `test_utils.py` | UA / IP-хелперы |

`tests/conftest.py` создаёт изолированный SQLite-файл на сессию и прогоняет миграции.

### Тесты iOS SDK

SwiftUI-харнес — `DeferLinkTestApp/`:

1. Откройте `DeferLinkTestApp.xcodeproj` в Xcode.
2. Отредактируйте `DeferLinkTestApp/NetworkManager.swift` — поставьте `baseURL` под свой сервер. Для iOS Simulator — `http://127.0.0.1:8000`; для физического устройства — LAN IP машины (и убедитесь, что firewall пропускает).
3. Запустите схему **DeferLinkTestApp**.
4. Тапните **Run All Tests**. Харнес гонит каждый эндпоинт, исполняет seeded `/dl` → `/resolve` сценарии с синтетическими fingerprint-ами, аналитические потоки и проверяет отправку SKAN CV. Каждый тест печатает зелёный/красный статус.

Юнит-тесты самого SDK — в `DeferLinkSDK/Tests/DeferLinkSDKTests/` — открыть `DeferLinkSDK/Package.swift` и запустить test plan.

### Быстрый ручной smoke-test

```bash
# 1) посеять сессию
curl -X POST http://localhost:8000/api/v1/session \
     -H 'Content-Type: application/json' \
     -d '{"promo_id":"summer_sale","domain":"example.com"}'

# 2) попытка resolve с условным fingerprint
curl -X POST http://localhost:8000/resolve \
     -H 'Content-Type: application/json' \
     -d '{
       "fingerprint": {
         "model":"iPhone15,2","language":"en-US",
         "timezone":"Europe/Belgrade","platform":"iOS",
         "user_agent":"DeferLinkSDK/1.0 (iPhone; iOS 17.0)",
         "screen_width":1170,"screen_height":2532,
         "is_first_launch":true
       },
       "app_scheme":"myapp://test",
       "fallback_url":"https://apps.apple.com"
     }'
```

## 4. Чек-лист продакшена

Перед боевым трафиком:

- [ ] **`ENVIRONMENT=production`** + **`SECRET_KEY`** — реальный, ≥32 символа (`generate_secure_secret_key()` из `app/config.py` ок).
- [ ] HTTPS-терминатор спереди (nginx/Caddy/CDN). **`COOKIE_SECURE=true`**, **`COOKIE_SAMESITE=none`** (чтобы SFSafariViewController шарил cookie кросс-контекст), **`TRUST_PROXY_HEADERS=true`**.
- [ ] **`CORS_ORIGINS`** — только реальные ад-домены.
- [ ] `DEVICECHECK_ENABLED=true`, `DEVICECHECK_SANDBOX=false`, реальный `.p8` ключ. Проверить через `POST /resolve` с боевым `device_check_token`.
- [ ] CAPI-конфиги созданы через `POST /api/v1/capi/configs` для каждого `(app_id, platform)`. Проверить — `POST /api/v1/capi/test`.
- [ ] SKAN-декодеры созданы через `POST /api/v1/skadnetwork/decoders` для каждой кампании, которую планируете форвардить.
- [ ] Клоакинг: посмотреть `cloaking_decision_log` через несколько часов; ужать/расширить правила через `/api/v1/cloaking/*`.
- [ ] Бэкапы: `data/deeplinks.db` — это всё состояние. Файлы WAL (`-wal`, `-shm`) рядом. Достаточно cron-а с `sqlite3 deeplinks.db ".backup '/backup/path.db'"`.
- [ ] Логи: `LOG_LEVEL=INFO` нормально; `DEBUG` включает `uvicorn --reload` — на проде не нужно.
- [ ] Ресурсы: SQLite + один воркер uvicorn — это тысячи `/dl` в минуту на маленьком VPS. Если перерастёте — несколько воркеров за единым writer-ом (`API_WORKERS=N`) и переезд на Postgres — границы видны в `app/database.py`.

## Помощь

По коммерческим интеграциям, адаптерам ad-сетей, кастомным CV-схемам, on-prem-разворачиванию и всему, что не вошло в доку:

* 📧 **Email** — [tdk@null.net](mailto:tdk@null.net)
* 📨 **Telegram** — [@smail_ios](https://t.me/smail_ios)
