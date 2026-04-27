# SKAdNetwork 4.0

DeferLink несёт полный серверный пайплайн SKAdNetwork:

* 6-битная схема conversion-value (CV), 1:1 совпадающая между бэкендом и iOS SDK;
* приёмник постбэков Apple с поддержкой версий 2/3/4 и проверкой ECDSA-подписи;
* кампанийный декодер, мапящий `(app_id, campaign_key, conversion_value)` в Facebook-CAPI событие;
* быстрая агрегированная таблица распределения для дашбордов.

Весь код — в `app/core/skadnetwork/`. Swift-зеркало — в `DeferLinkSDK/Sources/DeferLinkSDK/SKAdNetwork/`.

## Битовая раскладка CV — схема `rev3_eng2_flag1`

```
 бит 5 4 3 │ 2 1 │ 0
 └─revenue─┘ └─eng─┘ flag

 revenue_bucket ∈ [0..7]   3 бита — log-scale USD-бакеты
 engagement     ∈ [0..3]   2 бита — bounce / active / deep / power
 event_flag     ∈ [0..1]   1 бит  — 1 = реальное событие конверсии произошло
```

Кодирование:

```
cv = (revenue_bucket << 3) | (engagement << 1) | event_flag
```

`schema_name = "rev3_eng2_flag1"` — часть проводного контракта, никогда не меняется. Если когда-нибудь понадобится другая раскладка — выкатывайте под новым именем, старое держите вечно для legacy-устройств.

### Дефолтные revenue-бакеты

| Бакет | Floor (USD) | Заметки |
|---:|---:|---|
| 0 | 0.00     | Free user / нет покупки |
| 1 | 0.01     | Микро / реклама |
| 2 | 1.00     | Low |
| 3 | 5.00     | Standard |
| 4 | 20.00    | Mid (trial → sub) |
| 5 | 50.00    | High |
| 6 | 100.00   | Whale-track |
| 7 | 300.00   | Whale (открытый сверху) |

Per-app оверрайды лежат в `skan_cv_configs` и отдаются SDK через `GET /api/v1/skan/config?app_id=…`.

### Уровни engagement

`CVSchema.engagement_tier(...)` детерминирована:

| Уровень | Код | Триггер |
|---|---:|---|
| `bounce` | 0 | Дефолт — короткая / одна сессия |
| `active` | 1 | `sessions ≥ active_min_sessions` (default 2), либо `total_seconds ≥ bounce_max_seconds × 4` |
| `deep`   | 2 | `sessions ≥ deep_min_sessions` (default 5), либо `core_actions ≥ deep_min_core_actions` |
| `power`  | 3 | `power_requires_retention=true` И вернулся на следующий день И удержался day-2 И core_actions выполнены |

Те же константы заданы в Swift-стороне (`SKANConfig.swift`), чтобы симулятор и бэкенд считали идентично.

## Парсинг постбэка

`POST /api/v1/skadnetwork/postback` принимает JSON Apple. `PostbackParser.parse(...)`:

1. Защитно тянет все известные поля (string-cast, диапазоны int, enum-lookup). Неизвестные поля сохраняются в `raw_json`.
2. Требует `transaction-id` и `ad-network-id` — без них исключение.
3. Если `verify_signature=True` (по умолчанию), запускает ECDSA-P256 SHA-256 верификацию через `cryptography.hazmat` по опубликованному ключу (`APPLE_SKADNETWORK_PUBLIC_KEY_PEM`).
   * Успех → `signature_verified=1`.
   * Неудача → `signature_verified=2` (постбэк всё равно сохраняем, тихо не теряем).
   * Если `cryptography` не установлен → верификация отключается на старте, у строк `signature_verified=0`.

Состав подписываемой строки задокументирован в `_build_signed_fields(...)`:

* **v4.x** — `version | ad-network-id | source-identifier | app-id | transaction-id | redownload | source-app-id|source-domain | fidelity-type | did-win | postback-sequence-index`
* **v3.0** — `version | ad-network-id | campaign-id | app-id | transaction-id | redownload | source-app-id | (fidelity-type)`

Поля соединяются невидимым разделителем U+2063 (по спеке Apple).

## Последовательности постбэков

```
PostbackSequence.PB1 = 0   # день 0–2  — fine CV доступен
PostbackSequence.PB2 = 1   # день 3–7  — только coarse CV
PostbackSequence.PB3 = 2   # день 8–35 — только coarse CV
```

Coarse-only постбэки маппятся на синтетические CV для матчинга правил:

```
low    → cv = 0
medium → cv = 31
high   → cv = 63
```

Это позволяет одному списку правил декодера покрывать и PB1 (fine), и PB2/PB3 (coarse) без отдельных конфигов.

## Персистенс

`SKANService.ingest_postback(payload, conn)` возвращает `(SKANPostback, row_id, capi_instruction|None)`:

1. Парсинг + верификация (выше).
2. `INSERT INTO skan_postbacks (...)`. На `transaction_id` стоит `UNIQUE` — повторные ретраи Apple — no-op, возвращается существующий `row_id` с `inserted_new=False`, инструкция не выдаётся.
3. `INSERT … ON CONFLICT … DO UPDATE` на `skan_cv_distribution(date, app_id, source_identifier, campaign_id, conversion_value)` — инкрементирует `postback_count` для быстрых графиков.
4. Если есть `app_id`, спрашивается `CampaignDecoder.decode(pb, schema=CVSchema(config))`. Если правило совпало → возвращается `CAPIEventInstruction`. Хендлер маршрута форвардит её через `CAPIService.forward(...)` (см. [`capi.md`](capi.md)).
5. После CAPI-доставки маршрут обновляет `capi_forwarded`, `capi_forwarded_at`, `capi_last_error` через `SKANService.mark_forwarded(...)`.

## Правила декодера

`DecoderRule` (в `models.py`):

```jsonc
{
  "cv_min":           20,        // inclusive 0..63
  "cv_max":           63,        // inclusive 0..63
  "capi_event":       "Purchase",
  "forward":          true,      // false — заглушает этот диапазон CV
  "static_value":     null,      // если задано: значение CAPI = это (USD)
  "value_multiplier": 1.0,       // если static_value null:
                                 //   value = midpoint(revenue_bucket) × multiplier
  "currency":         "USD",
  "description":      "Платящие — полная выручка"
}
```

Декодер — упорядоченный список правил. **First match wins.** Нет совпадения → CAPI-событие не уходит (это намеренно).

Хранится в `skan_campaign_decoders`:

| Колонка | Заметки |
|---|---|
| `app_id` | Bundle id, например `com.example.app`. |
| `source_identifier` | Строка SKAN 4 (4 цифры). Для новых кампаний используйте её. |
| `campaign_id` | Legacy SKAN 2/3 int 0–99. Только если SKAN 4 source-id недоступен. |
| `decoder_json` | JSON-список объектов `DecoderRule` (выше). |
| `enabled` | `0`/`1`. Reload подхватывает изменения мгновенно. |

Lookup `(app_id, campaign_key)` сначала смотрит `source_identifier`, затем `str(campaign_id)` — см. `SKANPostback.campaign_key`.

## Per-app SKAN-конфиг

`GET /api/v1/skan/config?app_id=…` возвращает SDK-friendly JSON:

```jsonc
{
  "app_id":                  "com.example.app",
  "schema_version":          1,
  "schema_name":             "rev3_eng2_flag1",
  "revenue_buckets_usd":     [0.0, 0.01, 1.0, 5.0, 20.0, 50.0, 100.0, 300.0],
  "bounce_max_seconds":      30,
  "active_min_sessions":     2,
  "deep_min_sessions":       5,
  "deep_min_core_actions":   1,
  "power_requires_retention": true,
  "conversion_window_hours": 48,
  "cache_ttl_seconds":       86400
}
```

iOS SDK тянет это раз в `cache_ttl_seconds`, локально кеширует и вычисляет CV по той же арифметике, что `CVSchema.compute_cv(...)`. Файлы SDK: `CVEncoder.swift`, `SKANConfig.swift`.

## Админ-эндпоинты

См. [`api-reference.md`](api-reference.md#skadnetwork-appapiskadnetworkpy) — полный CRUD декодеров, листинг свежих постбэков, статистика распределения CV по `(app_id, source_identifier, day)`.

## Сторона SDK — отправка CV

```swift
// в приложении
SKANManager.shared.recordEvent(.purchase(amount: 9.99, currency: "USD"))

// SKANManager:
//   1. копит метрики сессий/engagement
//   2. вычисляет fine CV через CVEncoder.computeCV(...)
//   3. вызывает SKAdNetwork.updatePostbackConversionValue(...),
//      предпочитая API iOS 16.1 (fine+coarse),
//      откатываясь через 15.4 (coarse) и 14.0 (fine only).
```

Реализация в Swift (`CVEncoder.swift`) повторяет `cv_schema.py` бит-в-бит; обе используют `(rev << 3) | (eng << 1) | flag`.

## Что получаем end-to-end

1. Приложение шлёт события через `/api/v1/events/batch`.
2. Локально `SKANManager` агрегирует их в `(revenue, engagement, flag)` и обновляет SKAN-окно через API Apple.
3. Apple когда-нибудь шлёт `/api/v1/skadnetwork/postback`. Сохраняем + декодируем → опционально CAPI-событие.
4. `CAPIService.forward(...)` дедуплицирует по `transaction_id` Apple, поэтому один Facebook-пиксель видит и клиентские `af_purchase`, и серверные SKAN-Purchase без двойного счёта.
