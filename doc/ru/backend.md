# Модули бэкенда

Карта файлов `app/` по принципу «публичная поверхность + контракты». Поперечные темы (клоакинг, SKAN, CAPI) разобраны в собственных файлах.

## `app/main.py`

Точка входа в ASGI-приложение. Создаёт инстанс FastAPI, регистрирует роутеры из `app/api/*` и владеет хендлером `lifespan`, который:

* вызывает `Config.validate_config()`;
* открывает SQLite через `db_manager` и применяет все миграции из `app/migrations/`;
* грузит правила клоакинга в `CloakingEngine`, декодеры/конфиги в `SKANService`;
* грузит CAPI-конфиги (`CAPIService.load_configs`);
* создаёт три asyncio-задачи (cleanup, optimisation, CAPI retry) и корректно их останавливает.

Также определяет четыре «публичных» эндпоинта вне `/api/v1/`: `GET /`, `GET /dl`, `POST /resolve`, `GET /safari-resolve`. Детект ботов происходит на этом слое — клоакинг короткозамыкает запрос ещё до записи в БД. Извлечение IP из reverse-proxy уважает `TRUST_PROXY_HEADERS` (когда `true`, выигрывает первый элемент `X-Forwarded-For`).

## `app/config.py`

Единственный класс `Config` — все поля читаются из окружения с разумными дефолтами для разработки. Главные группы:

* **БД / API** — `DATABASE_PATH`, `API_HOST`, `API_PORT`, `API_WORKERS`.
* **Безопасность** — `SECRET_KEY` (≥32 символа и не из чёрного списка слабых паттернов при `ENVIRONMENT=production`), `COOKIE_SECURE`, `COOKIE_SAMESITE` (`lax|strict|none`), `CORS_ORIGINS`.
* **Deep linking** — `DEFAULT_TTL_HOURS` (TTL browser-сессии, 1–168), `MAX_FINGERPRINT_DISTANCE`, `CLEANUP_INTERVAL_MINUTES`.
* **Apple DeviceCheck** — `DEVICECHECK_ENABLED`, `DEVICECHECK_TEAM_ID`, `DEVICECHECK_KEY_ID`, `DEVICECHECK_KEY_PATH`, `DEVICECHECK_SANDBOX`.
* **IAB escape** — `APP_STORE_ID`, `APP_NAME`, `CLIPBOARD_TOKEN_PREFIX` (должен совпадать с SDK), `APP_URL_SCHEME`.
* **Фоновые воркеры** — `CAPI_RETRY_INTERVAL_SECONDS` (>0), `AUTO_OPTIMIZE_WEIGHTS`.

`validate_config()` бросает `ValueError` на плохих сочетаниях. `generate_secure_secret_key()` возвращает `secrets.token_urlsafe(32)`.

## `app/database.py` и миграции

`db_manager` экспозит контекст-менеджер `get_connection()` (на запрос, режим WAL) и `execute_query(sql, params)`, возвращающий список dict-`Row`. SQLite хорошо тянет умеренную нагрузку на одном хосте; для горизонтального масштаба замените на нормальный движок.

Миграции в `app/migrations/` добавляют таблицы и колонки идемпотентно. Порядок:

1. `add_enhanced_fields.py` — дополнительные fingerprint-колонки в `browser_sessions`.
2. `add_events_table.py` — `user_events` (аналитика).
3. `add_devicecheck_fields.py` — хеш токена DeviceCheck + статус верификации.
4. `add_cloaking_tables.py` — `cloaking_ip_rules`, `cloaking_ua_rules`, `cloaking_decision_log`.
5. `add_skadnetwork_tables.py` — `skan_postbacks`, `skan_campaign_decoders`, `skan_cv_configs`, `skan_cv_distribution`.
6. `add_capi_tables.py` — `capi_configs`, `capi_delivery_log`.
7. `enforce_capi_unique_app_platform.py` — уникальность `(app_id, platform)`.

## `app/deeplink_handler.py`

Оркестратор, связывающий browser-сессии и app-resolve.

* `create_session(promo_id, domain, user_agent, fingerprint=None, ttl_hours=Config.DEFAULT_TTL_HOURS)` — вставляет строку в `browser_sessions`, возвращает `session_id`.
* `resolve_matching_session(fingerprint, device_check_token_b64=None)` — прогоняет четырёхуровневый матч по порядку, возвращает `None` или dict с `session_id`, `promo_id`, `domain`, `match_method`, `match_confidence`.
* `cleanup_expired()` — дропает сессии старше TTL (вызывается фоновой задачей и `POST /api/v1/cleanup`).

Деталь: локальный параметр `timezone` раньше шейдил `datetime.timezone`; модуль теперь импортирует его как `from datetime import … timezone as _tz` и пользуется `_tz.utc`. При форке сохраняйте этот алиас.

## `app/core/intelligent_matcher.py`

`IntelligentMatcher` строит `MatchResult` из одного app-fingerprint и списка кандидатов browser-сессий.

* Взвешенный счёт по `timezone (0.35)`, `screen_dimensions (0.25)`, `language (0.20)`, `device_model (0.15)`, `user_agent (0.05)`. Веса меняются через `update_weights(...)` (использует опциональная задача оптимизации).
* Под-оценки сложные: эквивалентные IANA-зоны, фолбэк по UTC-смещению, сравнение aspect-ratio экранов, fuzzy-jaccard по моделям с курированными сопоставлениями (`iPhone14,2 ↔ iPhone 13 Pro`), родственные семьи языков.
* `_validate_temporal_patterns` умножает счёт на коэффициент времени с момента сессии — слишком рано (<10 с) или слишком поздно (>24 ч) штрафуют.
* `_get_dynamic_threshold` выбирает порог в `[0.50, 0.90]` по часу суток и `_assess_fingerprint_quality(...)` — разреженным fingerprint нужна большая уверенность.
* Все под-оценки кешируются по паре `(browser_value, app_value)`.

## `app/core/devicecheck.py`

Серверная верификация Apple DeviceCheck.

* `DeviceCheckVerifier.verify(token)` — `async`. Возвращает `DeviceCheckResult(valid, status, reason, bit0, bit1, last_update_time, is_new_device)`.
* В «degraded mode» (нет credentials Apple или отсутствуют `PyJWT`/`httpx`/`cryptography`) верификатор возвращает `status="indeterminate"`, чтобы хендлер не доверял токену, но и не падал.
* `hash_token(token)` — SHA-256 hex; в БД хранится только в этом виде.
* Synchletton на уровне модуля: `get_verifier()` / `init_verifier(...)`.

## `app/core/safari_escape.py`

`generate_escape_page(session_token, app_store_url, app_name, app_store_id, redirect_delay_ms=400)` возвращает полный HTML IAB-escape моста. Три clipboard-стратегии последовательно — современный Clipboard API, `execCommand('copy')`, `localStorage` — затем `setTimeout(redirect, delay_ms)`.

`build_app_store_url(app_store_id)` возвращает `https://apps.apple.com/app/id<id>`.

Полезная нагрузка clipboard — `f"{CLIPBOARD_PREFIX}:{session_token}"` (по умолчанию префикс `"deferlink"`). SDK парсит тем же префиксом и доверяет, только если суффикс ≥32 символов.

## `app/core/iab_detector.py`

`detect_browser(user_agent)` возвращает `BrowserDetectionResult` с:

* `context` — один из `BrowserContext.{SAFARI, FACEBOOK_IAB, INSTAGRAM_IAB, TIKTOK_IAB, TWITTER_IAB, WECHAT_IAB, SNAPCHAT_IAB, GENERIC_IAB, CHROME_IOS, UNKNOWN}`.
* `is_iab` — bool.
* `clipboard_reliable` — работает ли `execCommand('copy')` без жеста пользователя в этом контексте (Facebook/Instagram/Twitter — да; TikTok/WeChat/Snapchat — нет).
* `escape_strategy` — `EscapeStrategy.{NONE, CLIPBOARD_THEN_APPSTORE, APPSTORE_REDIRECT, UNIVERSAL_LINK}`.

`should_escape_to_safari(result)` — удобный bool.

## `app/core/event_tracker.py`

Чистый слой БД для `user_events`.

* `STANDARD_EVENTS` — множество `af_*`-имён по AppsFlyer.
* `insert_event(...)` — одна вставка с `INSERT OR IGNORE`. Возвращает `"inserted" | "duplicate" | "failed"`.
* `insert_events_batch(events, ip_address)` — пред-проверяет каждый `event_id` на дубль и считает итоги.
* `get_event_stats(start, end, promo_id)` — тоталы, топ-20 событий, выручка по валютам.
* `get_funnel(steps, start, end, promo_id)` — упорядоченный funnel: пользователей по шагу + конверсия к предыдущему/первому.
* `get_cohort_revenue(promo_id, days=30)` — дневная выручка по `(promo_id, currency)`.

## `app/core/cloaking/`

См. [`cloaking.md`](cloaking.md). Кратко:

* `engine.py` — `CloakingEngine.decide(...)` агрегирует сигналы байесом `1 − ∏(1 − cᵢ)`, `HARD_THRESHOLD = 0.88`, `SOFT_THRESHOLD = 0.65`, `BOT_SUSPICION_BOOST = 0.15`. Поведенческие сигналы могут поднять уверенность поверх авторитетного, но в одиночку не классифицируют как бот/ad-review.
* `ip_detector.py` — точные IP, CIDR (от наиболее специфичных), ASN. Кастомные правила из БД мерджатся со встроенными из `known_data.KNOWN_IP_RANGES` / `KNOWN_ASNS`.
* `ua_detector.py` — case-insensitive regex, кастом > builtin.
* `behavior_detector.py` — заголовочные эвристики с весами `no_accept_language=0.50`, `no_sec_fetch_site=0.45`, `no_accept=0.30`, `minimal_accept=0.25`, `no_accept_encoding=0.25`, `connection_close=0.15`, `no_referer=0.10`, `no_cookies=0.10`. Все мапятся в `VisitorType.SUSPICIOUS`.
* `models.py` — `VisitorType`, `CloakingAction`, `DetectionSignal`, `CloakingDecision`, `IPRule`, `UARuleRecord`.

## `app/core/skadnetwork/`

См. [`skadnetwork.md`](skadnetwork.md). Кратко:

* `cv_schema.py` — bit-pack хелперы `encode_cv` / `decode_cv_bits`, класс `CVSchema` с бакетами выручки, расчётом engagement-уровня и `decode(cv) → DecodedCV`. Дефолтные бакеты `[0, 0.01, 1, 5, 20, 50, 100, 300]` USD.
* `models.py` — `CoarseValue`, `FidelityType`, `PostbackSequence` (PB1/PB2/PB3), `SKANPostback`, `SKANConfig`, `DecoderRule` (с инклюзивным диапазоном `cv_min/cv_max`, `static_value` или `value_multiplier`).
* `postback_parser.py` — оборонительный парсер, опциональная ECDSA P-256 проверка по публичному ключу Apple.
* `campaign_decoder.py` — first-rule-wins по `(app_id, campaign_key)`. Coarse-only постбэки маппятся на синтетические CV (low→0, medium→31, high→63).
* `service.py` — `SKANService.ingest_postback(payload, conn) → (postback, row_id, capi_instruction_or_none)`.

## `app/core/capi/`

См. [`capi.md`](capi.md). Кратко:

* `models.py` — `CAPIPlatform`, `CAPIConfig` (per-app креды), `CAPIUserData` (PII, в основном хешированные), `CAPIEventData` (с `event_id` как ключом дедупа), `CAPIDeliveryResult`.
* `facebook.py` — `FacebookCAPIClient.send(config, event)` шлёт в `graph.facebook.com/{api_version}/{pixel_id}/events?access_token=…`. Хеширует `em`, `ph`, `external_id` (идемпотентно — уже хешированные значения проходят как есть).
* `service.py` — `CAPIService.forward(conn, app_id, event, platform)` с дедупом по `capi_delivery_log`. Расписание ретраев `[60, 300, 1800]` секунд, максимум 3 попытки.
* `retry_worker.py` — долгоживущий asyncio-цикл; фабрика `start_capi_retry_worker(interval_seconds=300)`. По умолчанию 300 с — равно минимальному окну в расписании.

## `app/utils.py`

Маленькие хелперы — нормализация UA, извлечение IP с учётом прокси, ISO-время. Читайте, если хотите подключить свой детектор ботов.

## Что обычно импортируют

| Что нужно | Импорт |
|---|---|
| Провалидировать запрос и записать сессию | `from app.deeplink_handler import DeepLinkHandler` (инстанцируется в `app/main.py`) |
| Оценить UA в рантайме | `from app.core.cloaking.engine import get_engine` |
| Принять Apple-постбэк | `from app.core.skadnetwork.service import skan_service` |
| Отправить кастомное событие в Facebook | `from app.core.capi.service import capi_service` |
| Запустить аналитику | `from app.core.event_tracker import get_event_stats, get_funnel` |
| Сгенерировать escape-страницу | `from app.core.safari_escape import generate_escape_page` |
| Детектировать IAB | `from app.core.iab_detector import detect_browser` |
