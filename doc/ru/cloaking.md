# Движок клоакинга

Подсистема клоакинга решает, что отдать посетителю на `GET /dl`. Она различает четыре класса:

* **Real user** — полный flow deferred deep link.
* **Bot** (поисковый/соц-краулер) — отдать SEO-страницу.
* **Ad reviewer** (модератор Facebook/Google/TikTok) — compliant-страницу, чтобы кампания не улетела в бан.
* **Suspicious** — неубедительные сигналы; настраиваемое действие, по умолчанию «логируем и пропускаем».

Весь код в `app/core/cloaking/`.

## Карта модулей

| Файл | Роль |
|---|---|
| `engine.py` | Агрегация, пороги, мапинг действий. Публичная точка входа `CloakingEngine.decide(...)`. |
| `ip_detector.py` | Точные IP / CIDR / ASN. Builtins из `known_data.py`, custom — из БД. |
| `ua_detector.py` | Скомпилированные regex. Custom > builtin. |
| `behavior_detector.py` | Заголовочные эвристики — слабые сигналы, поднимают только до `SUSPICIOUS`. |
| `models.py` | `VisitorType`, `CloakingAction`, `DetectionSignal`, `CloakingDecision`, `IPRule`, `UARuleRecord`. |
| `known_data.py` | Курированные встроенные IP-диапазоны, ASN, UA-regex (Google, Facebook, Bingbot, headless-браузеры …). |

## Модель скоринга

Каждый детектор возвращает 0+ объектов `DetectionSignal`:

```
source:        "ip_exact" | "ip_cidr" | "ip_asn" | "ua_regex" | "behavior"
description:   человекочитаемое описание
visitor_type:  REAL_USER | BOT | AD_REVIEW | SUSPICIOUS
confidence:    0.0 .. 1.0
matched_value: что именно сработало
```

`CloakingEngine._classify(...)` склеивает их в три шага:

1. **Байесовская аккумуляция по типам** — только по «авторитетным» сигналам (IP + UA):

   ```
   score(vtype) = 1 − ∏ (1 − cᵢ)   по всем сигналам этого vtype
   ```

   Гарантирует: два независимых 0.6 дают ≈0.84, при этом ни один слабый сигнал не доминирует в одиночку.

2. **Каскад порогов**:

   * Любой score типа ≥ `HARD_THRESHOLD = 0.88` → этот тип сразу выигрывает.
   * Иначе любой score типа ≥ `SOFT_THRESHOLD = 0.65` → выигрывает.
   * Иначе — фолбэк на behavioural-only (см. ниже).

   Если порог проходят несколько типов, ничьи разрешает `_TYPE_PRIORITY`: `AD_REVIEW (3) > BOT (2) > SUSPICIOUS (1) > REAL_USER (0)`.

3. **Behavioural boost / cap**:

   * Поведенческие сигналы могут *поднять* уверенность победителя на максимум `BOT_SUSPICION_BOOST = 0.15` (формула — `min(0.15, mean(bh_confidence) × 0.3)`).
   * **В одиночку** поведенческие сигналы никогда не повышают тип выше `SUSPICIOUS`. Если IP/UA не сработали, движок берёт их совокупный score и переводит в `SUSPICIOUS` только при достижении `CloakingConfig.suspicious_min_confidence` (по умолчанию `0.70`).

`CloakingDecision` несёт выбранный `visitor_type`, `confidence`, итоговое `CloakingAction`, исходные IP/UA и весь список сигналов (попадает в админ-лог).

## Маппинг действий

`CloakingConfig.action_map` по умолчанию:

| Тип посетителя | Действие |
|---|---|
| `REAL_USER`   | `FULL_FLOW`        |
| `BOT`         | `SEO_PAGE`         |
| `AD_REVIEW`   | `COMPLIANT_PAGE`   |
| `SUSPICIOUS`  | `SUSPICIOUS_FLOW`  |

`SUSPICIOUS_FLOW` — то же, что `FULL_FLOW`, но запрос логируется на INFO. `BLOCK` доступен, но не используется по умолчанию — возвращает 403 / пустое тело.

Если `visitor_type == SUSPICIOUS` и `confidence < suspicious_min_confidence`, движок понижает решение до `FULL_FLOW`. Это страхует от ложных срабатываний по чисто заголовочным эвристикам.

## IP-детектор

* Builtins — `known_data.KNOWN_IP_RANGES` (CIDR + visitor type + confidence + описание) и `KNOWN_ASNS`. Курированы под Google, Facebook, Bing, типичных скраперов и рекламные сети.
* Кастомные правила из БД (`cloaking_ip_rules`) грузятся через `IPDetector.load_custom_rules(rules)`. Каждое `IPRule` — одно из: `ip_exact`, `cidr` или `asn`. Детектор мерджит custom + builtin и пересортирует CIDR по `prefixlen DESC`, чтобы выигрывал самый специфичный.
* `detect(ip, asn=None)` возвращает до трёх сигналов — exact, CIDR (только первое/самое специфичное), ASN.
* Поиск O(N) по плоскому списку — нормально для десятков тысяч диапазонов. Если перевалите за это, ставьте radix-tree (`pytricia`).

## UA-детектор

* Builtins — `known_data.KNOWN_UA_PATTERNS`, case-insensitive regex для Googlebot, Bingbot, FacebookExternalHit, AdsBot, headless-браузеров, маркеров Selenium/Playwright/Puppeteer и т.п.
* Кастомные — `cloaking_ua_rules`; детектор валидирует синтаксис regex и тихо отбрасывает битые с warn-логом.
* Возвращаются все совпавшие паттерны, с дедупом по `(visitor_type, description)` — оставляем самый высокий confidence. Дальше движок берёт сильнейший вклад на тип.

## Поведенческий детектор

Чисто инспекция заголовков — без I/O и БД. Все сигналы → `VisitorType.SUSPICIOUS`, by design.

| Ключ | Вес | Триггер |
|---|---:|---|
| `no_accept_language` | 0.50 | Пустой / отсутствует `Accept-Language` |
| `no_sec_fetch_site`  | 0.45 | Пустой / отсутствует `Sec-Fetch-Site` |
| `no_accept`          | 0.30 | Нет `Accept` |
| `minimal_accept`     | 0.25 | `Accept: */*` |
| `no_accept_encoding` | 0.25 | Нет `Accept-Encoding` |
| `connection_close`   | 0.15 | `Connection: close` без keep-alive |
| `no_referer`         | 0.10 | Нет `Referer` |
| `no_cookies`         | 0.10 | В запросе нет cookies |

Cookies приходят dict-ом; сам движок достаёт их из FastAPI-`Request` в `app/main.py`. `Referer` читается и из явного параметра, и из заголовков (явный параметр выигрывает).

## Кастомные правила — админ API

`/api/v1/cloaking/...` (см. [`api-reference.md`](api-reference.md#cloaking-admin-appapicloaking_adminpy)) даёт CRUD по `cloaking_ip_rules` и `cloaking_ua_rules`. После insert/update/delete API вызывает `CloakingEngine.reload_rules(...)` — изменения применяются мгновенно, без рестарта.

Поля повторяют `IPRule` / `UARuleRecord`:

```jsonc
// IP-правило
{
  "id":           42,
  "cidr":         "31.13.24.0/21",   // ИЛИ ip_exact ИЛИ asn — ровно одно
  "ip_exact":     null,
  "asn":          null,
  "visitor_type": "ad_review",
  "confidence":   0.95,
  "description":  "Facebook ad review",
  "enabled":      true
}

// UA-правило
{
  "id":           7,
  "pattern":      "(?i)facebookexternalhit",
  "visitor_type": "bot",
  "confidence":   0.97,
  "description":  "Facebook crawler",
  "enabled":      true
}
```

## Лог решений

Каждое `CloakingDecision` по реальному `/dl` пишется в `cloaking_decision_log` (`migrations/add_cloaking_tables.py`) с visitor_type, action, confidence и JSON-сериализованным списком сигналов. `GET /api/v1/cloaking/log` пагинирует таблицу для отладки; `/api/v1/cloaking/stats` — счётчики по типу за окно.

## Тест UA / IP-пары

`POST /api/v1/cloaking/test` гонит движок на синтетическом входе — удобно при написании нового правила:

```jsonc
POST /api/v1/cloaking/test
{
  "ip":         "66.249.66.1",
  "user_agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
  "headers":    { "accept": "*/*" },
  "cookies":    {}
}
```

В ответе — полный JSON `CloakingDecision`, включая каждый сигнал с весом. Та же форма, что попадает в decision-лог.

## Hot-reload

`CloakingEngine.reload_rules(ip_rules, ua_rules)` безопасно вызывать из любой задачи в любой момент — он перестраивает внутренние списки in-place. Админские эндпоинты дёргают его после каждой мутации, а `app.main.lifespan` — один раз на старте с правилами из SQLite.
