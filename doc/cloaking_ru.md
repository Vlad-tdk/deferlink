# Cloaking — Документация

> **Файл:** `doc/cloaking_ru.md` · [English version](cloaking_en.md)

---

## Содержание

1. [Что такое клоакинг в DeferLink](#что-такое-клоакинг-в-deferlink)
2. [Как работает детектор](#как-работает-детектор)
3. [Слои детекции](#слои-детекции)
4. [Модель оценки (scoring)](#модель-оценки-scoring)
5. [Типы посетителей и действия](#типы-посетителей-и-действия)
6. [Страницы для ботов](#страницы-для-ботов)
7. [Настройка через API](#настройка-через-api)
8. [Управление правилами](#управление-правилами)
9. [Тестирование решений](#тестирование-решений)
10. [Audit log и статистика](#audit-log-и-статистика)
11. [Встроенные правила](#встроенные-правила)
12. [Архитектура кода](#архитектура-кода)

---

## Что такое клоакинг в DeferLink

Клоакинг — это показ разного контента разным типам посетителей на основании анализа запроса. DeferLink использует клоакинг в трёх легитимных сценариях:

| Сценарий | Кому | Что показывается |
|----------|------|-----------------|
| **SEO** | Поисковые боты (Googlebot, Yandexbot…) | HTML-страница с OG-тегами и мета-данными для индексации |
| **Рекламные ревьюеры** | Системы проверки рекламы (Google Ads, Facebook) | Чистая лендинговая страница без редиректов |
| **Реальные пользователи** | Все остальные | Полный флоу DeferLink (deep link + App Store) |

> **Важно.** DeferLink не помогает скрывать от ревьюеров нарушения политик рекламных сетей. Система предназначена для технической корректной подачи контента разным типам клиентов.

---

## Как работает детектор

При каждом запросе к `/dl` движок анализирует запрос по четырём независимым слоям и собирает список сигналов `DetectionSignal`. Каждый сигнал несёт:

- `source` — откуда пришёл сигнал (`ip_cidr`, `ip_asn`, `ua_regex`, `behavior`)
- `visitor_type` — к какому типу относится (`bot`, `ad_review`, `suspicious`)
- `confidence` — уверенность 0.0–1.0

Сигналы агрегируются в итоговый `CloakingDecision` с финальным типом посетителя и действием.

```
HTTP Request (/dl)
       │
       ▼
┌──────────────────────────────────────────────────────┐
│                   CloakingEngine                     │
│                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │ IPDetector  │  │ UADetector  │  │  Behavior   │  │
│  │             │  │             │  │  Detector   │  │
│  │ CIDR ranges │  │ 80+ regex   │  │ 7 header    │  │
│  │ ASN numbers │  │ patterns    │  │ signals     │  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  │
│         │                │                │          │
│         └────────────────┴────────────────┘          │
│                          │                           │
│                  ┌───────▼────────┐                  │
│                  │   Classifier   │                  │
│                  │ Bayesian score │                  │
│                  │ Priority rules │                  │
│                  └───────┬────────┘                  │
│                          │                           │
│                  CloakingDecision                    │
│           (visitor_type + action + confidence)       │
└──────────────────────────┬───────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
      SEO page       Compliant page    Full flow
    (for bots)      (for ad review)   (real users)
```

---

## Слои детекции

### Слой 1 — IP-адрес (наиболее надёжный)

Проверяет IP клиента по трём источникам:

**Точное совпадение IP** — самый высокий приоритет. Например, если добавлено конкретное `1.2.3.4`.

**CIDR-диапазоны** — предварительно скомпилированные `ipaddress.ip_network` объекты, отсортированные от наиболее специфичных (длинная маска) к наименее специфичным. Первое совпадение — самое точное.

```
66.249.64.1  →  попадает в  66.249.64.0/19  →  Googlebot AS15169  →  confidence=0.98
```

**ASN (Autonomous System Number)** — определяет принадлежность IP к автономной системе. Поддерживается передача ASN из внешней GeoIP-базы через параметр `asn` в `decide()`.

```python
decision = engine.decide(ip="66.249.64.1", user_agent="...", asn=15169)
```

---

### Слой 2 — User-Agent

80+ предкомпилированных регулярных выражений, case-insensitive. Каждый паттерн имеет своё значение `confidence`.

Примеры:

| Паттерн | Тип | Confidence |
|---------|-----|:----------:|
| `\bgooglebot\b` | bot | 0.99 |
| `\badsbot-google\b` | ad_review | 0.97 |
| `facebookexternalhit` | bot | 0.99 |
| `headlesschrome` | suspicious | 0.90 |
| `\bselenium\b` | suspicious | 0.90 |
| `\bcurl\b` | bot | 0.90 |
| `python-requests` | bot | 0.90 |

---

### Слой 3 — Поведенческий анализ заголовков

Анализирует HTTP-заголовки запроса. Каждый сигнал слабый сам по себе, но в сумме может указать на бота:

| Сигнал | Описание | Confidence |
|--------|----------|:----------:|
| Нет `Accept-Language` | Реальные браузеры всегда отправляют | 0.50 |
| Нет `Sec-Fetch-Site` | Отправляется только Chromium/Firefox | 0.45 |
| Нет `Accept` | Браузеры всегда отправляют | 0.30 |
| `Accept: */*` | Характерно для curl, wget и HTTP-клиентов | 0.25 |
| Нет `Accept-Encoding` | Браузеры всегда согласовывают сжатие | 0.25 |
| `Connection: close` | Браузеры предпочитают keep-alive | 0.15 |
| Нет `Referer` | Слабый сигнал | 0.10 |
| Нет cookies | Слабый сигнал | 0.10 |

> **Важно.** Поведенческие сигналы **в одиночку** не могут дать классификацию `bot` или `ad_review` — только `suspicious`. Это защита от ложных срабатываний на пользователей, которые используют Privacy-ориентированные браузеры.

---

## Модель оценки (scoring)

### Шаг 1 — Байесовское накопление

Для каждого типа посетителя (`bot`, `ad_review`, `suspicious`) сигналы накапливаются по формуле:

```
score = 1 − ∏(1 − cᵢ)
```

Где `cᵢ` — confidence каждого сигнала данного типа. Формула гарантирует, что:
- Один сигнал с `c=0.99` даёт `score=0.99`
- Два сигнала с `c=0.70` дают `score=0.91` (не 1.40)
- Десять слабых сигналов `c=0.10` дают `score=0.65`

### Шаг 2 — Пороги

| Порог | Значение | Описание |
|-------|:--------:|---------|
| `HARD_THRESHOLD` | **0.88** | Один сигнал выше порога — решение принимается сразу |
| `SOFT_THRESHOLD` | **0.65** | Накопленный score — для слабых сигналов |

### Шаг 3 — Приоритет типов

Если несколько типов преодолели порог одновременно (например, IP указывает на `bot`, а UA — на `ad_review`), применяется приоритет:

```
ad_review (3) > bot (2) > suspicious (1) > real_user (0)
```

**Пример:** IP `66.249.64.1` (Google, `bot=0.98`) + UA `AdsBot-Google` (`ad_review=0.97`) → итог `ad_review`, потому что `ad_review` имеет более высокий приоритет.

### Шаг 4 — Поведенческий буст

Когда IP или UA уже дали решение, поведенческие сигналы добавляют небольшой буст к итоговой уверенности (максимум +0.15). Это никогда не меняет тип — только увеличивает confidence.

---

## Типы посетителей и действия

| Тип | Значение | Действие по умолчанию |
|-----|----------|----------------------|
| `real_user` | Реальный пользователь | `full_flow` — полный DeferLink флоу |
| `bot` | Поисковый или социальный краулер | `seo_page` — OG-страница для индексации |
| `ad_review` | Система проверки рекламы | `compliant_page` — чистый лендинг |
| `suspicious` | Неоднозначные сигналы | `suspicious_flow` — как `full_flow`, но с флагом в логе |

Действия для каждого типа настраиваются через `CloakingConfig`:

```python
from app.core.cloaking import init_engine, CloakingConfig
from app.core.cloaking.models import VisitorType, CloakingAction

engine = init_engine(CloakingConfig(action_map={
    VisitorType.REAL_USER:  CloakingAction.FULL_FLOW,
    VisitorType.BOT:        CloakingAction.SEO_PAGE,
    VisitorType.AD_REVIEW:  CloakingAction.COMPLIANT_PAGE,
    VisitorType.SUSPICIOUS: CloakingAction.BLOCK,   # жёсткая блокировка подозрительных
}))
```

---

## Страницы для ботов

### SEO-страница (`seo_page`)

Показывается поисковым краулерам. Содержит Open Graph теги, canonical URL и описание приложения — всё необходимое для корректной индексации и предпросмотра ссылок в соцсетях:

```html
<meta property="og:title"       content="MyApp">
<meta property="og:description" content="Download MyApp — exclusive promo SUMMER24">
<meta property="og:type"        content="website">
<meta name="description"        content="...">
<link rel="canonical"           href="https://myapp.com">
```

Страница генерируется динамически — содержит имя приложения (`APP_NAME`), promo_id и ссылку на App Store. Статус ответа `200` (не `302`) — это важно для корректной индексации.

### Compliant-страница (`compliant_page`)

Показывается системам проверки рекламы. Минималистичный HTML: название приложения, описание, кнопка «Скачать» со ссылкой на App Store. Без JavaScript редиректов, без cookie, без скриптов.

---

## Настройка через API

### Базовый URL

```
http://localhost:8000/api/v1/cloaking
```

Полная документация Swagger: `http://localhost:8000/docs#/Cloaking%20Admin`

---

## Управление правилами

### IP-правила

#### Добавить CIDR-диапазон

```bash
curl -X POST http://localhost:8000/api/v1/cloaking/rules/ip \
  -H "Content-Type: application/json" \
  -d '{
    "cidr":         "192.168.1.0/24",
    "visitor_type": "bot",
    "confidence":   0.99,
    "description":  "Внутренняя сеть тестирования",
    "enabled":      true
  }'
```

#### Добавить конкретный IP

```bash
curl -X POST http://localhost:8000/api/v1/cloaking/rules/ip \
  -H "Content-Type: application/json" \
  -d '{
    "ip_exact":     "1.2.3.4",
    "visitor_type": "ad_review",
    "confidence":   0.99,
    "description":  "Известный IP ревьюера Facebook"
  }'
```

#### Добавить ASN

```bash
curl -X POST http://localhost:8000/api/v1/cloaking/rules/ip \
  -H "Content-Type: application/json" \
  -d '{
    "asn":          64496,
    "visitor_type": "bot",
    "confidence":   0.95,
    "description":  "AS64496 — корпоративная сеть"
  }'
```

> **Правило:** ровно одно из полей `cidr` / `ip_exact` / `asn` должно быть заполнено.

#### Получить все IP-правила

```bash
curl http://localhost:8000/api/v1/cloaking/rules/ip
```

```json
{
  "success": true,
  "count": 2,
  "rules": [
    {
      "id":           1,
      "cidr":         "192.168.1.0/24",
      "ip_exact":     null,
      "asn":          null,
      "visitor_type": "bot",
      "confidence":   0.99,
      "description":  "Внутренняя сеть тестирования",
      "enabled":      1,
      "created_at":   "2025-04-23T12:00:00"
    }
  ]
}
```

#### Обновить правило

```bash
curl -X PATCH http://localhost:8000/api/v1/cloaking/rules/ip/1 \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

#### Удалить правило

```bash
curl -X DELETE http://localhost:8000/api/v1/cloaking/rules/ip/1
```

---

### UA-правила

#### Добавить паттерн (regex)

```bash
curl -X POST http://localhost:8000/api/v1/cloaking/rules/ua \
  -H "Content-Type: application/json" \
  -d '{
    "pattern":      "mycompanybot",
    "visitor_type": "bot",
    "confidence":   0.99,
    "description":  "Внутренний бот компании"
  }'
```

Паттерн — case-insensitive регулярное выражение. Примеры валидных паттернов:

```json
"pattern": "mybot"                      // простая подстрока
"pattern": "\\bmybot\\b"               // точное слово
"pattern": "mybot/[0-9]+"              // с версией
"pattern": "(crawler|spider)\\.myco"   // несколько вариантов
```

#### Получить все UA-правила

```bash
curl http://localhost:8000/api/v1/cloaking/rules/ua
```

#### Обновить UA-правило

```bash
curl -X PATCH http://localhost:8000/api/v1/cloaking/rules/ua/1 \
  -H "Content-Type: application/json" \
  -d '{
    "confidence": 0.95,
    "description": "Обновлённое описание"
  }'
```

#### Удалить UA-правило

```bash
curl -X DELETE http://localhost:8000/api/v1/cloaking/rules/ua/1
```

---

## Тестирование решений

Эндпоинт `/test` позволяет проверить любое сочетание IP + UA + заголовков **без реального трафика** — полезно при настройке правил.

### Пример: проверить Googlebot

```bash
curl -X POST http://localhost:8000/api/v1/cloaking/test \
  -H "Content-Type: application/json" \
  -d '{
    "ip":         "66.249.64.1",
    "user_agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
  }'
```

```json
{
  "success":      true,
  "visitor_type": "bot",
  "action":       "seo_page",
  "confidence":   1.0,
  "is_bot":       true,
  "signals": [
    {
      "source":       "ip_cidr",
      "visitor_type": "bot",
      "confidence":   0.98,
      "description":  "Googlebot AS15169",
      "matched":      "66.249.64.1 in 66.249.64.0/19"
    },
    {
      "source":       "ua_regex",
      "visitor_type": "bot",
      "confidence":   0.99,
      "description":  "Googlebot",
      "matched":      "googlebot"
    }
  ]
}
```

### Пример: реальный iPhone с заголовками

```bash
curl -X POST http://localhost:8000/api/v1/cloaking/test \
  -H "Content-Type: application/json" \
  -d '{
    "ip": "8.8.8.8",
    "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "headers": {
      "accept-language":  "ru-RU,ru;q=0.9",
      "accept":           "text/html,application/xhtml+xml,*/*;q=0.8",
      "accept-encoding":  "gzip, deflate, br",
      "sec-fetch-site":   "none",
      "sec-fetch-mode":   "navigate"
    },
    "cookies": {
      "session": "abc123"
    }
  }'
```

```json
{
  "success":      true,
  "visitor_type": "real_user",
  "action":       "full_flow",
  "confidence":   0.0,
  "is_bot":       false,
  "signals":      []
}
```

### Пример: проверить кастомное правило после добавления

```bash
# 1. Добавить правило
curl -X POST http://localhost:8000/api/v1/cloaking/rules/ua \
  -d '{"pattern":"mybot","visitor_type":"bot","confidence":0.99,"description":"My bot"}'

# 2. Убедиться что оно срабатывает
curl -X POST http://localhost:8000/api/v1/cloaking/test \
  -d '{"ip":"1.2.3.4","user_agent":"MyBot/2.0 (crawler)"}'
```

---

## Audit Log и статистика

Каждое решение движка записывается в таблицу `cloaking_decisions_log`. Это позволяет:
- Видеть какие IP/UA были определены как боты
- Анализировать false positives
- Отслеживать тренды по времени

### Просмотр последних решений

```bash
# Последние 50 решений
curl "http://localhost:8000/api/v1/cloaking/log?limit=50"

# Только боты
curl "http://localhost:8000/api/v1/cloaking/log?visitor_type=bot&limit=100"

# По конкретному IP
curl "http://localhost:8000/api/v1/cloaking/log?ip=66.249.64.1"
```

**Ответ:**
```json
{
  "success": true,
  "count": 3,
  "rows": [
    {
      "id":           1,
      "ip":           "66.249.64.1",
      "user_agent":   "Mozilla/5.0 (compatible; Googlebot/2.1; ...)",
      "visitor_type": "bot",
      "action":       "seo_page",
      "confidence":   1.0,
      "signals":      "[{\"source\": \"ip_cidr\", ...}]",
      "path":         "/dl",
      "timestamp":    "2025-04-23T14:00:00"
    }
  ]
}
```

### Агрегированная статистика

```bash
# За последние 7 дней
curl "http://localhost:8000/api/v1/cloaking/stats?days=7"
```

```json
{
  "success":          true,
  "period_days":      7,
  "total_decisions":  4821,
  "breakdown": [
    {
      "visitor_type":   "real_user",
      "action":         "full_flow",
      "total":          4102,
      "avg_confidence": 0.0,
      "unique_ips":     987
    },
    {
      "visitor_type":   "bot",
      "action":         "seo_page",
      "total":          634,
      "avg_confidence": 0.973,
      "unique_ips":     42
    },
    {
      "visitor_type":   "suspicious",
      "action":         "suspicious_flow",
      "total":          71,
      "avg_confidence": 0.821,
      "unique_ips":     58
    },
    {
      "visitor_type":   "ad_review",
      "action":         "compliant_page",
      "total":          14,
      "avg_confidence": 0.961,
      "unique_ips":     7
    }
  ]
}
```

---

## Встроенные правила

Встроенные правила загружаются из `app/core/cloaking/known_data.py` при старте сервера и **не хранятся в базе данных** — это гарантирует их целостность. Изменить их можно только через код.

### Встроенные IP-диапазоны

| Платформа | Диапазонов | Тип | Confidence |
|-----------|:----------:|-----|:----------:|
| Facebook / Meta | 13 | bot | 0.97 |
| Facebook Ads | 3 | ad_review | 0.90–0.93 |
| Google Search | 11 | bot | 0.97–0.98 |
| Google Ads | 2 | ad_review | 0.92 |
| Bing / Microsoft | 7 | bot | 0.95–0.97 |
| Apple | 3 | bot | 0.90–0.95 |
| Yandex | 13 | bot | 0.97 |
| Twitter / X | 3 | bot | 0.95 |
| LinkedIn | 3 | bot | 0.95 |
| AWS (датацентр) | 3 | suspicious | 0.55 |
| SEO-инструменты | 4 | bot | 0.80–0.85 |

### Встроенные ASN

| ASN | Организация | Тип |
|-----|-------------|-----|
| AS32934 | Meta/Facebook | bot |
| AS15169 | Google | bot |
| AS8075 | Microsoft/Bing | bot |
| AS714 | Apple | bot |
| AS13238 | Yandex | bot |
| AS13414 | Twitter/X | bot |
| AS14413 | LinkedIn | bot |
| AS394711 | Ahrefs | bot |
| AS16509 | Amazon AWS | suspicious |
| AS396982 | Google Cloud | suspicious |

### Встроенные UA-паттерны (80+)

Категории:
- **Поисковые боты**: Googlebot, Bingbot, Yandexbot, Baiduspider, DuckDuckBot и др.
- **Социальные краулеры**: facebookexternalhit, Twitterbot, LinkedInBot, Slackbot, Discordbot, WhatsApp и др.
- **Рекламные боты**: AdsBot-Google, mediapartners-google, YandexDirect и др.
- **SEO-инструменты**: SemrushBot, AhrefsBot, MJ12bot, Screaming Frog и др.
- **Мониторинг**: UptimeRobot, Pingdom, New Relic, Datadog и др.
- **HTTP-клиенты**: curl, wget, python-requests, Go, Java, libwww-perl и др.
- **Headless-браузеры**: PhantomJS, HeadlessChrome, Selenium, Puppeteer, Playwright

---

## Архитектура кода

```
app/core/cloaking/
├── __init__.py              Публичный API пакета
│
├── models.py                Типы данных
│   ├── VisitorType          Enum: real_user | bot | ad_review | suspicious
│   ├── CloakingAction       Enum: full_flow | seo_page | compliant_page | block
│   ├── DetectionSignal      Один сигнал с source, confidence, description
│   ├── CloakingDecision     Итоговое решение (тип + действие + список сигналов)
│   ├── IPRule               DB-запись правила для IP
│   └── UARuleRecord         DB-запись правила для UA
│
├── known_data.py            Встроенные данные (не в БД)
│   ├── KNOWN_IP_RANGES      70+ CIDR-диапазонов
│   ├── KNOWN_ASNS           15 автономных систем
│   └── KNOWN_UA_PATTERNS    80+ regex-паттернов
│
├── ip_detector.py           IP-детектор
│   └── IPDetector
│       ├── detect(ip, asn)  → List[DetectionSignal]
│       └── load_custom_rules(rules)  горячая перезагрузка
│
├── ua_detector.py           UA-детектор
│   └── UADetector
│       ├── detect(user_agent)        → List[DetectionSignal]
│       └── load_custom_rules(rules)  горячая перезагрузка
│
├── behavior_detector.py     Поведенческий детектор
│   └── BehaviorDetector
│       └── detect(headers, cookies, referer) → List[DetectionSignal]
│
└── engine.py                Оркестратор
    ├── CloakingEngine
    │   ├── decide(ip, ua, headers, cookies, referer, asn) → CloakingDecision
    │   └── reload_rules(ip_rules, ua_rules)  горячая перезагрузка
    ├── CloakingConfig        Маппинг типов на действия
    ├── get_engine()          Получить singleton
    └── init_engine(config)   Инициализировать singleton

app/api/cloaking_admin.py    Admin REST API (FastAPI router)
app/migrations/
└── add_cloaking_tables.py   Создание таблиц в SQLite

База данных (SQLite):
├── cloaking_ip_rules        Кастомные IP-правила
├── cloaking_ua_rules        Кастомные UA-правила
└── cloaking_decisions_log   Audit log всех решений
```

### Жизненный цикл правил

```
Старт сервера
      │
      ▼
init_engine()                  ← создаёт CloakingEngine
      │
      ▼
_load_all_rules() из БД        ← загружает кастомные правила
      │
      ▼
engine.reload_rules()          ← IPDetector + UADetector перестраивают
      │                          внутренние структуры с кастомными +
      │                          встроенными правилами
      ▼
POST /api/v1/cloaking/rules/*  ← CRUD → сразу вызывает _load_all_rules()
                                  горячая перезагрузка без рестарта
```

---

## Добавление встроенных правил через код

Если нужно добавить новые правила в кодовую базу (а не через API), редактируйте `app/core/cloaking/known_data.py`:

```python
# Добавить новый CIDR в KNOWN_IP_RANGES:
("203.0.113.0/24", "bot", 0.97, "Example Corp crawler AS64496"),

# Добавить новый ASN в KNOWN_ASNS:
(64496, "bot", 0.90, "Example Corp AS64496"),

# Добавить новый UA-паттерн в KNOWN_UA_PATTERNS:
(r"\bexamplebot\b", "bot", 0.99, "Example Corp bot"),
```

После редактирования файла — рестарт сервера.

---

## Ссылки

- [English version](cloaking_en.md)
- [Основной README](../README.md)
- [Swagger UI](http://localhost:8000/docs#/Cloaking%20Admin)
- Исходный код: `app/core/cloaking/`
