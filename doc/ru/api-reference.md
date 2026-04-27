# Справочник HTTP API

Все маршруты смонтированы в FastAPI-приложении в `app/main.py`. Пространство `/api/v1/*` распределено по роутерам в `app/api/`.

Соглашения:

* JSON in / JSON out, если не оговорено иное.
* `Content-Type: application/json` (формы на POST не принимаются).
* Ошибки — стандартный конверт FastAPI `{"detail": "<message>"}` с соответствующим HTTP-статусом.
* Время — ISO 8601 в UTC.
* На всех маршрутах включён CORS согласно `CORS_ORIGINS`.

---

## Публичные маршруты (в `app/main.py`)

### `GET /`

Баннер сервиса. Возвращает имя приложения, версию, статус-строку и список доступных эндпоинтов. Удобно для liveness-проб, которым нужно непустое тело.

### `GET /dl`

Браузерный обработчик клика.

| Query-параметр | Обязателен | Описание |
|---|---|---|
| `promo_id` | да | Логический идентификатор промо/кампании, возвращается в `/resolve`. |
| `domain`   | да | Источник — используется для аналитики и поиска декодера. |
| `timezone`, `language`, `screen_size`, `model` | нет | Подсказки браузера для fingerprint-матчера. JS escape-страницы заполняет их из `navigator.*`. |

Поведение:

1. Решение клоакинга — боты/ревьюеры получают `SEO_PAGE` или `COMPLIANT_PAGE`.
2. Реальные пользователи получают HTML-«escape»-страницу (clipboard handoff + редирект в App Store), если запрос пришёл из in-app браузера, или `302` в App Store из настоящего Safari.
3. `Set-Cookie: dl_session_id=<session_id>; SameSite=…; Secure` ставится всегда — позднее SFSafariViewController сможет разрешить через tier 2.

### `POST /resolve`

Resolve при первом запуске приложения. Формы тела и ответа описаны в [`architecture.md`](architecture.md#поток-запроса--первый-запуск-приложения-resolve).

`success=true, matched=false` означает, что запрос принят, но сессия не найдена (органик). Сетевые/серверные проблемы — HTTP 5xx с телом `detail`.

### `GET /safari-resolve`

Используется внутри SDK невидимым SFSafariViewController. Читает cookie `dl_session_id`, поставленный `/dl`, и `302`-редиректит обратно в приложение через `<APP_URL_SCHEME>://resolved?session_id=<id>` (или `…?session_id=none`). `handleOpenURL` SDK парсит редирект и снимает блокировку resolve.

---

## `/api/v1/*` — по концернам

### Health (`app/api/health.py`)

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/api/v1/health/quick` | Liveness — `{"status": "ok"}`. |
| `GET` | `/api/v1/health` | Дефолтный health — пинг БД + версия. |
| `GET` | `/api/v1/health/detailed` | Плюс число коннектов, длины очередей, время последнего cleanup. |

### Deep links (`app/api/deeplinks.py`)

| Метод | Путь | Назначение |
|---|---|---|
| `POST` | `/api/v1/session` | Создать синтетическую сессию для тестов. Тело: `{"promo_id":"…","domain":"…"}` → `{"session_id":"…","status":"created"}`. |
| `POST` | `/api/v1/resolve` | Тот же контракт, что у публичного `/resolve` (на симметрию/будущее версионирование). |
| `GET`  | `/api/v1/instruction/{session_id}` | Статическая HTML-страница как редирект-цель в некоторых адаптерах; для нормального SDK не нужна. |

### Events (`app/api/events.py`)

| Метод | Путь | Тело | Назначение |
|---|---|---|---|
| `POST` | `/api/v1/events` | `EventRequest` (одно событие) | Вставить одно событие. Возвращает `{status, event_id}`. |
| `POST` | `/api/v1/events/batch` | `BatchEventRequest` (`events: [...]`, до 100) | Bulk-вставка с дедупом по событию. Возвращает `{success, inserted, duplicate, failed}`. |
| `GET`  | `/api/v1/events/stats` | — query: `start`, `end`, `promo_id` | Тоталы, топ-события, выручка по валютам. |
| `POST` | `/api/v1/events/funnel` | `{steps:["af_install","af_complete_registration","af_purchase"]}` | По шагам: счётчики и конверсии. |
| `GET`  | `/api/v1/events/cohort-revenue` | query: `promo_id`, `days=30` | Дневная выручка по `promo_id` и валютам. |

Имена стандартных событий и константы `DLEventName.*` описаны в [`sdk-ios.md`](sdk-ios.md#трекинг-событий).

### Stats (`app/api/stats.py`)

| Метод | Путь | Назначение |
|---|---|---|
| `GET`  | `/api/v1/stats` | Агрегированная статистика по сессиям/установкам/атрибуции. |
| `GET`  | `/api/v1/stats/detailed` | Разрез по `promo_id` и методу матча. |
| `GET`  | `/api/v1/stats/analytics` | Сводка sessions+events. |
| `POST` | `/api/v1/cleanup` | Ручной триггер той же чистки, что делает фоновая задача. |

### Cloaking admin (`app/api/cloaking_admin.py`)

CRUD для правил клоакинга, потребляемых `CloakingEngine`.

| Метод | Путь | Назначение |
|---|---|---|
| `GET` / `POST` / `PUT /{id}` / `DELETE /{id}` | `/api/v1/cloaking/ip-rules[/{id}]` | Кастомные IP/CIDR/ASN-правила. |
| `GET` / `POST` / `PUT /{id}` / `DELETE /{id}` | `/api/v1/cloaking/ua-rules[/{id}]`  | Кастомные UA-regex-правила. |
| `POST` | `/api/v1/cloaking/test` | Тело `{ip, user_agent, headers?, cookies?}` → живое `CloakingDecision` для отладки. |
| `GET`  | `/api/v1/cloaking/log` | Последние решения (с сигналами) — пагинированно. |
| `GET`  | `/api/v1/cloaking/stats` | Счётчики по `visitor_type` за окно. |

Поля повторяют `IPRule` / `UARuleRecord` из `app/core/cloaking/models.py`.

### Facebook CAPI admin (`app/api/capi_admin.py`)

| Метод | Путь | Назначение |
|---|---|---|
| `GET` / `POST` / `PUT /{id}` / `DELETE /{id}` | `/api/v1/capi/configs[/{id}]` | Конфиг pixel/access-token на приложение. Уникально по `(app_id, platform)`. |
| `POST` | `/api/v1/capi/test` | Послать одно синтетическое событие для проверки кред. |
| `GET`  | `/api/v1/capi/log` | Лог доставки со статусом, последней ошибкой и расписанием ретраев. |
| `POST` | `/api/v1/capi/retry/{row_id}` | Принудительно ретранслировать запаркованную строку. |

### SKAdNetwork (`app/api/skadnetwork.py`)

| Метод | Путь | Назначение |
|---|---|---|
| `POST` | `/api/v1/skadnetwork/postback` | Эндпоинт постбэков Apple. Проверяет подпись, сохраняет, декодирует, форвардит в CAPI. |
| `GET`  | `/api/v1/skan/config?app_id=…` | CV-конфиг для SDK (revenue-бакеты, пороги engagement, окно конверсии). |
| `GET` / `POST` / `PUT /{id}` / `DELETE /{id}` | `/api/v1/skadnetwork/decoders[/{id}]` | Правила декодера для кампаний. |
| `GET`  | `/api/v1/skadnetwork/postbacks` | Последние постбэки (фильтр по app/campaign). |
| `GET`  | `/api/v1/skadnetwork/stats` | Распределение CV, счётчики по `(app_id, source_identifier, day)`. |

Битовая раскладка и семантика правил — [`skadnetwork.md`](skadnetwork.md).

---

## Возможные ошибки

| Статус | Когда |
|---|---|
| `400`  | Невалидный JSON, отсутствует обязательное поле. |
| `404`  | Неизвестный маршрут или несуществующий id на PUT/DELETE. |
| `409`  | Нарушение уникальности (например, дубль `(app_id, platform)` для CAPI). |
| `422`  | Ошибка валидации pydantic. |
| `500`  | Неожиданное исключение — тело `{"detail": "..."}`, в логе stack trace. |

Хендлер сознательно никогда не возвращает 500 на «нет атрибуции» — см. [`/resolve`](#post-resolve) выше.
