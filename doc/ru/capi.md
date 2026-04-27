# Facebook Conversions API

`app/core/capi/` — самодостаточный CAPI-форвардер. Принимает платформонезависимые данные события, диспатчит в нужный платформенный клиент (сейчас только Facebook), сохраняет каждую попытку в `capi_delivery_log` и крутит фоновый воркер ретраев по фиксированному расписанию.

## Карта модулей

| Файл | Роль |
|---|---|
| `models.py` | Датаклассы — `CAPIPlatform`, `CAPIConfig`, `CAPIUserData`, `CAPIEventData`, `CAPIDeliveryResult`. |
| `facebook.py` | `FacebookCAPIClient` — собственно HTTPS POST в `graph.facebook.com`, сборка payload, хеширование PII. |
| `service.py` | `CAPIService` — кеш конфигов, `forward()`, `retry_pending()`, дедуп, персистенс. Singleton `capi_service`. |
| `retry_worker.py` | `CAPIRetryWorker` asyncio-задача; фабрика `start_capi_retry_worker(interval_seconds=…)`. |

## Wire flow

```
SDK / SKAN
   │
   ▼
CAPIEventData   ──►  CAPIService.forward(conn, app_id, event, platform)
                          │
                          ├─ дедуп по capi_delivery_log (succeeded=1)
                          ├─ резолв CAPIConfig из кеша
                          ├─ FacebookCAPIClient.send(...)
                          │      → POST https://graph.facebook.com/v21.0/{pixel}/events
                          ├─ INSERT INTO capi_delivery_log (...)
                          ▼
                   CAPIDeliveryResult
```

Отдельный фоновый цикл вызывает `CAPIService.retry_pending(conn)` каждые `CAPI_RETRY_INTERVAL_SECONDS` (по умолчанию 300).

## CAPIConfig

Креды на приложение + платформу, лежат в `capi_configs` с уникальностью на `(app_id, platform)` (см. `migrations/enforce_capi_unique_app_platform.py`).

```jsonc
{
  "id":              1,
  "app_id":          "com.example.app",
  "platform":        "facebook",
  "pixel_id":        "1234567890",
  "access_token":    "<long-lived CAPI token>",
  "test_event_code": "TEST12345",   // опционально, для FB-дашборда
  "api_version":     "v21.0",
  "enabled":         true
}
```

`CAPIService.load_configs(conn)` строит in-memory кеш `(app_id, platform) → CAPIConfig`. Админ-эндпоинты под `/api/v1/capi/configs` перезагружают его после каждой мутации.

## CAPIEventData

```python
@dataclass
class CAPIEventData:
    event_name:      str          # "Purchase", "Lead", "CompleteRegistration"
    event_id:        str          # ключ дедупа (UUID для SDK, Apple txn-id для SKAN)
    event_time:      int          # unix-секунды
    event_source_url: Optional[str] = None
    action_source:   str = "app"  # "app" | "website" | "email" | …
    user_data:       CAPIUserData = field(default_factory=CAPIUserData)
    value:           Optional[float] = None
    currency:        Optional[str]   = None
    custom_data:     Dict[str, Any]  = {}
    source:          str = "manual"  # "sdk" | "skan" | "manual"
    source_ref_id:   Optional[int] = None
```

`source` и `source_ref_id` сохраняются в delivery_log, чтобы строку из `skan_postbacks.id` или `user_events.id` всегда можно было проследить через CAPI.

## Хеширование PII

`FacebookCAPIClient._hash_user_data(...)`:

| Поле | Хеш? | Заметки |
|---|:---:|---|
| `client_ip_address` | нет | как есть |
| `client_user_agent` | нет | как есть |
| `fbp`, `fbc` | нет | уже непрозрачные id |
| `em` (email) | да | lower-case + `sha256` |
| `ph` (phone) | да | lower-case + `sha256` |
| `external_id` (app_user_id) | да | lower-case + `sha256` |

Хеширование идемпотентно: значение, уже выглядящее как 64 hex-символа в нижнем регистре, проходит без изменений. Это значит, что SDK может пред-хешировать на устройстве (рекомендуем для `external_id`) — двойного хеша не будет.

## Форма payload (Facebook)

```jsonc
POST https://graph.facebook.com/v21.0/{pixel_id}/events?access_token=…
{
  "data": [
    {
      "event_name":    "Purchase",
      "event_time":    1700000000,
      "event_id":      "uuid-or-skan-txn-id",
      "action_source": "app",
      "user_data": {
        "client_ip_address": "203.0.113.7",
        "client_user_agent": "DeferLinkSDK/1.0 …",
        "external_id":       "<sha256>",
        "em":                "<sha256>"
      },
      "custom_data": {
        "value":    9.99,
        "currency": "USD"
      }
    }
  ],
  "test_event_code": "TEST12345"
}
```

`event_source_url`, `value`, `currency` и `custom_data` шлются только если заданы. Тело ответа в delivery_log обрезается до 2000 символов, чтобы таблица не пухла.

## Дедупликация

Перед отправкой `CAPIService.forward(...)` запускает:

```sql
SELECT id FROM capi_delivery_log
 WHERE app_id   = ?
   AND platform = ?
   AND event_id = ?
   AND succeeded = 1
 LIMIT 1
```

Если успешная доставка уже есть, нового запроса не будет; вызов вернёт `success=true, response_body="[dedup] already delivered"` и существующий `delivery_log_id`.

Вместе с серверной дедупликацией Facebook по `event_id` это означает:

* Повторные SDK-ретраи одного события ⇒ доставлено один раз.
* SKAN-постбэк после SDK-`af_purchase` с тем же `event_id` ⇒ доставлено один раз.
* Повторный успешный ретрай PB1 после первого ⇒ доставлено один раз.

Для SKAN ключ дедупа `event_id` — это **`transaction_id` Apple**.

## Семантика ретраев

Расписание (`_RETRY_SCHEDULE = [60, 300, 1800]` секунд):

| Попытка | Backoff до следующей |
|---:|---|
| 1 (исходная) | +60 с |
| 2 | +300 с |
| 3 | +1800 с |
| 4+ | паркуется (`next_retry_at = NULL`) |

`_MAX_ATTEMPTS = 3` — после третьей неудачи строка остаётся с `succeeded=0, next_retry_at=NULL`. Видна в `GET /api/v1/capi/log`, можно принудительно ретрайнуть через `POST /api/v1/capi/retry/{row_id}`.

Воркер ретраев работает так:

```python
async def _tick(self) -> int:
    with self._db_manager.get_connection() as conn:
        return await self._service.retry_pending(conn)
```

`retry_pending(conn)` читает до 100 пора-наступивших строк по `next_retry_at ASC`, повторно POST-ит сохранённый payload (`payload_json`), обновляет `attempts`, `last_error`, `last_attempt_at`, `next_retry_at`. На каждый тик открывается новый коннект — `sqlite3` не шарит коннекты между задачами.

Дефолтный интервал тика — 300 с; воркер кламится снизу 30 секундами.

## Режимы отказа

| Состояние строки `delivery_log` | Смысл |
|---|---|
| `succeeded=1` | Готово. Игнорится всеми ретраями и дедупами. |
| `succeeded=0, next_retry_at <= now` | На следующем тике воркер заберёт. |
| `succeeded=0, next_retry_at > now` | Откладываемся до запланированного времени. |
| `succeeded=0, next_retry_at IS NULL, attempts >= 3` | Запаркована, нужно вмешательство. |
| `succeeded=0, next_retry_at IS NULL, last_error="no config"` | Конфиг CAPI пропал — пересоздать и вручную ретрайнуть. |

`POST /api/v1/capi/retry/{row_id}` сбрасывает `next_retry_at` в «сейчас», воркер заберёт строку немедленно.

## Тестовый эндпоинт

`POST /api/v1/capi/test` собирает синтетический `CAPIEventData` из тела запроса, зовёт `CAPIService.forward(...)` с `source="manual"` и возвращает живой `CAPIDeliveryResult`. Удобно для проверки свежей пары pixel + access-token до боевого включения трафика.

## Интеграция в lifecycle

В `app/main.py:lifespan`:

```python
capi_service.load_configs(conn)
_capi_retry_worker = start_capi_retry_worker(interval_seconds=Config.CAPI_RETRY_INTERVAL_SECONDS)
...
await _capi_retry_worker.stop()
await capi_service.close()
```

`capi_service.close()` корректно гасит внутренний `httpx.AsyncClient`, чтобы пулы соединений не утекали при reload-циклах.
