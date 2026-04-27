# Архитектура

Этот документ описывает систему целиком. Глубокие разборы по подсистемам — в конце.

## Высокоуровневая схема

DeferLink — это Python-бэкенд (FastAPI + SQLite) и iOS SDK на Swift. У бэкенда есть одна публичная точка входа для рекламных кликов (`/dl`) и одна для разрешения первого запуска приложения (`/resolve`). Всё остальное живёт под `/api/v1/` и делится на SDK-колбэки (`events`, `skadnetwork/postback`, `skan/config`) и админ-поверхность (правила клоакинга, конфиги CAPI, правила декодера, статистика, health).

```
                        ┌───────────────┐
              ┌────────►│   /api/v1/*   │── админ / SDK
              │         │ (FastAPI)     │
   публичный──┤         └───────────────┘
   интернет   │
              │         ┌───────────────┐         ┌──────────────┐
              ├────────►│  /dl  /escape │────────►│  cloaking    │
              │         │  /resolve     │         │  engine      │
              │         │  /safari-     │         └──────────────┘
              │         │   resolve     │                │
              │         └───────────────┘         ┌──────────────┐
              │                  │                │ DeepLink     │
              │                  └───────────────►│ Handler      │
              │                                   └──────┬───────┘
              │                                          │
              │                                   ┌──────▼───────┐
              │                                   │   SQLite     │
              │                                   │   (один      │
              │                                   │   процесс)   │
              │                                   └──────────────┘
              │
              │         ┌───────────────┐         ┌──────────────┐
              └────────►│  Apple SKAN   │────────►│ SKAN service │
                        │   postback    │         │  + decoder   │
                        └───────────────┘         └──────┬───────┘
                                                         │
                                                  ┌──────▼───────┐
                                                  │ CAPI service │──► graph.facebook.com
                                                  │  + retry     │
                                                  │  worker      │
                                                  └──────────────┘
```

## Жизненный цикл и процессы

HTTP-сервер запускается под `uvicorn` (`run.py`). На старте `app.main` создаёт FastAPI-приложение с `lifespan`, который:

1. Вызывает `Config.validate_config()` — падает быстро при слабом `SECRET_KEY` и т.п. в продакшене.
2. Инициализирует схему SQLite и применяет все миграции из `app/migrations/`.
3. Загружает IP/UA-правила клоакинга и SKAN-декодеры из БД в кеши (`CloakingEngine`, `SKANService`, `CAPIService`).
4. Создаёт singleton `DeepLinkHandler` и подключает его к `app/api/deeplinks.py`.
5. Запускает три фоновые asyncio-задачи на всё время жизни сервера:
   * **Cleanup** — удаляет просроченные browser-сессии (`DEFAULT_TTL_HOURS`, по умолчанию 48 часов) каждые `CLEANUP_INTERVAL_MINUTES`.
   * **Оптимизация алгоритма** — opt-in (`AUTO_OPTIMIZE_WEIGHTS=true`), периодический пересчёт `IntelligentMatcher.weights`.
   * **CAPI retry worker** — каждые `CAPI_RETRY_INTERVAL_SECONDS` сканирует `capi_delivery_log` на строки с `next_retry_at <= now` и повторяет запрос (см. `app/core/capi/retry_worker.py`).

На остановке `lifespan` корректно гасит задачи и закрывает `httpx.AsyncClient`, используемый для исходящих CAPI-вызовов.

## Поток запроса — рекламный клик

1. Рекламная сеть редиректит браузер устройства (или in-app браузер) на `GET /dl?promo_id=…&domain=…`.
2. `app/main.py` извлекает IP клиента (с `TRUST_PROXY_HEADERS`, уважающим `X-Forwarded-For`) и User-Agent.
3. `CloakingEngine.decide(...)` агрегирует IP-, UA- и поведенческие сигналы в `CloakingDecision`. Математика — в [`cloaking.md`](cloaking.md).
4. Если посетитель — `BOT` или `AD_REVIEW`, ответ — настроенное действие (`SEO_PAGE`, `COMPLIANT_PAGE`, `BLOCK`).
5. Иначе `DeepLinkHandler.create_session(promo_id, domain, user_agent, …)` пишет строку в `browser_sessions` и возвращает `session_id`.
6. UA пропускается через `iab_detector.detect_browser(...)`. Если мы внутри in-app браузера (Facebook, Instagram, Twitter, …), `safari_escape.generate_escape_page(...)` возвращает HTML-«мост», который:
   * пишет `deferlink:<session_id>` в буфер обмена через `navigator.clipboard.writeText` (с фолбэком на `execCommand('copy')` и резерв в `localStorage`);
   * ставит маленький `Set-Cookie: dl_session_id=…` (используется позже общим cookie jar SFSafariViewController);
   * редиректит в App Store через `redirect_delay_ms` (по умолчанию 400 мс).
7. Для настоящего Safari просто ставим cookie и делаем `302` прямо в App Store.

## Поток запроса — первый запуск приложения (`/resolve`)

iOS SDK вызывает этот эндпоинт один раз на устройство, при первом запуске, с `FingerprintPayload`:

```jsonc
POST /resolve
{
  "fingerprint": {
    "model":            "iPhone15,2",
    "language":         "en-US",
    "timezone":         "Europe/Belgrade",
    "user_agent":       "DeferLinkSDK/1.0 …",
    "screen_width":     1170,
    "screen_height":    2532,
    "platform":         "iOS",
    "app_version":      "1.0",
    "idfv":             "EBC1F1F0-…",

    "clipboard_token":         "deferlink:<session_id>",   // tier 1
    "safari_cookie_session_id": "<session_id>",            // tier 2
    "device_check_token":      "<base64>",                 // tier 3
    "is_first_launch":         true
  },
  "app_scheme":   "myapp://test",
  "fallback_url": "https://apps.apple.com/…"
}
```

`DeepLinkHandler.resolve_matching_session(...)` обходит четыре уровня по порядку; первое попадание короткозамыкает остальные:

| # | Метод | Уверенность | Поле |
|---|---|---|---|
| 1 | **Clipboard**   | 100 %     | `clipboard_token`, парсится с `CLIPBOARD_TOKEN_PREFIX` |
| 2 | **Safari cookie** | ~99 %    | `safari_cookie_session_id` (из SFSafariViewController) |
| 3 | **DeviceCheck** | ~97 %     | `device_check_token`, проверяется у Apple, хеш сверяется |
| 4 | **Fingerprint** | 60–90 %   | `IntelligentMatcher.find_best_match(...)` с динамическим порогом |

Форма ответа (см. `app/api/deeplinks.py`):

```jsonc
{
  "success":      true,                  // запрос обработан (НЕ == найдено)
  "matched":      true,                  // атрибуция найдена
  "match_method": "clipboard",
  "promo_id":     "summer_sale",
  "session_id":   "f3c2…",
  "domain":       "example.com",
  "redirect_url": "https://apps.apple.com/…",
  "app_url":      "myapp://test",
  "message":      "Сессия успешно разрешена"
}
```

`success=true, matched=false` означает «запрос ОК, атрибуция не найдена» — это ожидаемый исход для органических установок и **не** ошибка.

## Приём событий

SDK шлёт батчи в `POST /api/v1/events/batch`:

* Каждый `DeferLinkEvent` несёт `event_id` (клиентский UUID, ключ дедупликации), `event_name` (`af_purchase` и т.д.), опциональные `revenue` + `currency`, `properties` (≤50), `session_id` / `promo_id` (проставляются после resolve), `app_user_id` плюс контекст устройства.
* `app/core/event_tracker.insert_events_batch(...)` пишет строки в `user_events` через `INSERT OR IGNORE` — дубликаты тихо отбрасываются.
* Если для `app_id` приложения есть CAPI-конфиг, `CAPIService.forward(...)` ставит конверсию в очередь Facebook. Поля PII (`em`, `ph`, `external_id`) хешируются SHA-256; `client_ip_address` и `client_user_agent` идут как есть.

Сбои пишутся в `capi_delivery_log` с `next_retry_at = now + 60s`. Воркер ретраев работает по расписанию `[60s, 300s, 1800s]` до трёх попыток; после этого строка паркуется (`next_retry_at = NULL`) и доступна вручную через `/api/v1/capi/log`.

## Пайплайн SKAdNetwork

Apple шлёт данные конверсии в `POST /api/v1/skadnetwork/postback`. `PostbackParser.parse(...)` декодирует версии 2, 3 и 4, валидирует ECDSA-подпись по опубликованному Apple ключу P-256 и возвращает `SKANPostback`. `SKANService.ingest_postback(...)`:

1. Сохраняет строку в `skan_postbacks` (`transaction_id` уникален; дубли — no-op).
2. Обновляет дневную таблицу распределения для быстрых дашбордов.
3. Если правило `CampaignDecoder` совпадает с тройкой `(app_id, campaign_key, conversion_value)`, возвращает `CAPIEventInstruction` с `capi_event`, `value` и `currency`.

Инструкция уходит через тот же `CAPIService.forward(...)`, что и SDK-события — поэтому один Facebook-пиксель видит и клиентские, и SKAN-конверсии, дедуплицированные по `transaction_id` Apple (он же `event_id` для CAPI).

SDK-сторона повторяет битовую раскладку 1:1 (`CVEncoder.swift`) и шлёт CV через `SKAdNetwork.updatePostbackConversionValue` — предпочитая API iOS 16.1 (fine+coarse) и откатываясь через 15.4 и 14.0.

## Потоки и конкурентность

* Бэкенд: одного `uvicorn`-воркера достаточно для умеренной нагрузки. SQLite открыт с `WAL` и короткими соединениями на запрос (`db_manager.get_connection()`); долгоживущие async-задачи (CAPI retry) открывают свой connection на тик, чтобы избежать шеринга между задачами.
* iOS SDK: каждый публичный метод `DeferLink` и `SKANManager` — `@MainActor`. Сетевые вызовы идут через `DeferLinkClient` (async API `URLSession`). Очередь событий использует серийный `DispatchQueue` для файлового I/O и сливается по `Timer` плюс хукам жизненного цикла приложения.

## База данных

SQLite, один файл по `DATABASE_PATH`. Миграции в `app/migrations/` добавляют (в порядке): расширенные поля fingerprint, таблицу событий, поля DeviceCheck, таблицы клоакинга, таблицы SKAdNetwork, таблицы CAPI и ограничение уникальности `(app_id, platform)` для CAPI-конфигов. Каждая миграция идемпотентна (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE … ADD COLUMN`), повторный запуск безопасен.

## Куда читать дальше

* HTTP-эндпоинты, формы запросов/ответов — [`api-reference.md`](api-reference.md)
* Все модули бэкенда (matching, IAB-детект, escape-страница, event tracker, БД) — [`backend.md`](backend.md)
* Математика клоакинга и формат правил — [`cloaking.md`](cloaking.md)
* Битовая раскладка conversion-value и правила декодера — [`skadnetwork.md`](skadnetwork.md)
* Полезная нагрузка Facebook CAPI, хеширование, retry — [`capi.md`](capi.md)
* Публичная поверхность iOS SDK — [`sdk-ios.md`](sdk-ios.md)
* Пошаговая установка + запуск + тесты — [`install-and-test.md`](install-and-test.md)
