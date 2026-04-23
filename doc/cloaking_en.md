# Cloaking — Documentation

> **File:** `doc/cloaking_en.md` · [Русская версия](cloaking_ru.md)

---

## Table of Contents

1. [What is Cloaking in DeferLink](#what-is-cloaking-in-deferlink)
2. [How the Detector Works](#how-the-detector-works)
3. [Detection Layers](#detection-layers)
4. [Scoring Model](#scoring-model)
5. [Visitor Types and Actions](#visitor-types-and-actions)
6. [Bot Response Pages](#bot-response-pages)
7. [Configuration via API](#configuration-via-api)
8. [Rule Management](#rule-management)
9. [Testing Decisions](#testing-decisions)
10. [Audit Log and Statistics](#audit-log-and-statistics)
11. [Built-in Rules](#built-in-rules)
12. [Code Architecture](#code-architecture)

---

## What is Cloaking in DeferLink

Cloaking means serving different content to different visitor types based on request analysis. DeferLink uses cloaking for three legitimate scenarios:

| Scenario | Audience | What is Served |
|----------|----------|----------------|
| **SEO** | Search crawlers (Googlebot, Yandexbot, …) | HTML page with OG tags and metadata for indexing |
| **Ad Review** | Ad review systems (Google Ads, Meta) | Clean landing page with no redirects |
| **Real Users** | Everyone else | Full DeferLink flow (deep link + App Store) |

> **Note.** DeferLink does not help conceal policy violations from ad network reviewers. The system is designed to technically serve the appropriate content to each client type.

---

## How the Detector Works

On every request to `/dl`, the engine analyzes the request across four independent layers and collects a list of `DetectionSignal` objects. Each signal carries:

- `source` — where the signal came from (`ip_cidr`, `ip_asn`, `ua_regex`, `behavior`)
- `visitor_type` — the visitor category it points to (`bot`, `ad_review`, `suspicious`)
- `confidence` — certainty score from 0.0 to 1.0

Signals are aggregated into a final `CloakingDecision` containing the resolved visitor type and corresponding action.

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

## Detection Layers

### Layer 1 — IP Address (most reliable)

Checks the client IP against three sources:

**Exact IP match** — highest priority. For example, if a specific `1.2.3.4` has been added as a rule.

**CIDR ranges** — pre-compiled `ipaddress.ip_network` objects sorted from most specific (longest prefix) to least specific. The first match is always the most precise.

```
66.249.64.1  →  matches  66.249.64.0/19  →  Googlebot AS15169  →  confidence=0.98
```

**ASN (Autonomous System Number)** — identifies the network an IP belongs to. You can pass the ASN from an external GeoIP database via the `asn` parameter in `decide()`:

```python
decision = engine.decide(ip="66.249.64.1", user_agent="...", asn=15169)
```

---

### Layer 2 — User-Agent

80+ pre-compiled regular expressions, case-insensitive. Each pattern has its own `confidence` value.

Examples:

| Pattern | Type | Confidence |
|---------|------|:----------:|
| `\bgooglebot\b` | bot | 0.99 |
| `\badsbot-google\b` | ad_review | 0.97 |
| `facebookexternalhit` | bot | 0.99 |
| `headlesschrome` | suspicious | 0.90 |
| `\bselenium\b` | suspicious | 0.90 |
| `\bcurl\b` | bot | 0.90 |
| `python-requests` | bot | 0.90 |

---

### Layer 3 — Behavioral Header Analysis

Analyzes the HTTP request headers. Each signal is weak on its own, but together they can indicate a non-browser client:

| Signal | Description | Confidence |
|--------|-------------|:----------:|
| No `Accept-Language` | Real browsers always send this | 0.50 |
| No `Sec-Fetch-Site` | Only sent by Chromium/Firefox | 0.45 |
| No `Accept` | Browsers always include this | 0.30 |
| `Accept: */*` | Typical of curl, wget, and HTTP clients | 0.25 |
| No `Accept-Encoding` | Browsers always negotiate compression | 0.25 |
| `Connection: close` | Browsers prefer keep-alive | 0.15 |
| No `Referer` | Weak signal | 0.10 |
| No cookies | Weak signal | 0.10 |

> **Important.** Behavioral signals **alone** can never produce a `bot` or `ad_review` classification — only `suspicious`. This prevents false positives for users of privacy-focused browsers.

---

## Scoring Model

### Step 1 — Bayesian Accumulation

For each visitor type (`bot`, `ad_review`, `suspicious`), signals are accumulated using the formula:

```
score = 1 − ∏(1 − cᵢ)
```

Where `cᵢ` is the confidence of each signal for that visitor type. This formula ensures that:
- One signal with `c=0.99` gives `score=0.99`
- Two signals with `c=0.70` give `score=0.91` (not 1.40)
- Ten weak signals with `c=0.10` give `score=0.65`

### Step 2 — Thresholds

| Threshold | Value | Description |
|-----------|:-----:|-------------|
| `HARD_THRESHOLD` | **0.88** | A single signal above this threshold is sufficient to classify immediately |
| `SOFT_THRESHOLD` | **0.65** | Accumulated score threshold for weak signal combinations |

### Step 3 — Type Priority

If multiple visitor types exceed the threshold simultaneously (for example, an IP indicates `bot` while the UA indicates `ad_review`), priority is applied:

```
ad_review (3) > bot (2) > suspicious (1) > real_user (0)
```

**Example:** IP `66.249.64.1` (Google, `bot=0.98`) + UA `AdsBot-Google` (`ad_review=0.97`) → result is `ad_review`, because `ad_review` has higher priority.

### Step 4 — Behavioral Boost

When IP or UA signals have already produced a decision, behavioral signals add a small boost to the final confidence score (maximum +0.15). This never changes the visitor type — it only increases the confidence value.

---

## Visitor Types and Actions

| Type | Meaning | Default Action |
|------|---------|----------------|
| `real_user` | Genuine end user | `full_flow` — complete DeferLink flow |
| `bot` | Search or social crawler | `seo_page` — OG metadata page for indexing |
| `ad_review` | Ad review system | `compliant_page` — clean landing page |
| `suspicious` | Ambiguous signals | `suspicious_flow` — same as `full_flow`, but flagged in the log |

Actions for each visitor type are configurable via `CloakingConfig`:

```python
from app.core.cloaking import init_engine, CloakingConfig
from app.core.cloaking.models import VisitorType, CloakingAction

engine = init_engine(CloakingConfig(action_map={
    VisitorType.REAL_USER:  CloakingAction.FULL_FLOW,
    VisitorType.BOT:        CloakingAction.SEO_PAGE,
    VisitorType.AD_REVIEW:  CloakingAction.COMPLIANT_PAGE,
    VisitorType.SUSPICIOUS: CloakingAction.BLOCK,   # hard-block suspicious visitors
}))
```

---

## Bot Response Pages

### SEO Page (`seo_page`)

Served to search crawlers. Contains Open Graph tags, a canonical URL, and an app description — everything needed for proper indexing and social media link previews:

```html
<meta property="og:title"       content="MyApp">
<meta property="og:description" content="Download MyApp — exclusive promo SUMMER24">
<meta property="og:type"        content="website">
<meta name="description"        content="...">
<link rel="canonical"           href="https://myapp.com">
```

The page is generated dynamically — it includes the app name (`APP_NAME`), promo_id, and the App Store link. The response status is `200` (not `302`) — this is important for correct indexing.

### Compliant Page (`compliant_page`)

Served to ad review systems. Minimal HTML: the app name, a description, and a "Download" button pointing to the App Store. No JavaScript redirects, no cookies, no tracking scripts.

---

## Configuration via API

### Base URL

```
http://localhost:8000/api/v1/cloaking
```

Full Swagger documentation: `http://localhost:8000/docs#/Cloaking%20Admin`

---

## Rule Management

### IP Rules

#### Add a CIDR Range

```bash
curl -X POST http://localhost:8000/api/v1/cloaking/rules/ip \
  -H "Content-Type: application/json" \
  -d '{
    "cidr":         "192.168.1.0/24",
    "visitor_type": "bot",
    "confidence":   0.99,
    "description":  "Internal testing network",
    "enabled":      true
  }'
```

#### Add a Specific IP

```bash
curl -X POST http://localhost:8000/api/v1/cloaking/rules/ip \
  -H "Content-Type: application/json" \
  -d '{
    "ip_exact":     "1.2.3.4",
    "visitor_type": "ad_review",
    "confidence":   0.99,
    "description":  "Known Facebook reviewer IP"
  }'
```

#### Add an ASN

```bash
curl -X POST http://localhost:8000/api/v1/cloaking/rules/ip \
  -H "Content-Type: application/json" \
  -d '{
    "asn":          64496,
    "visitor_type": "bot",
    "confidence":   0.95,
    "description":  "AS64496 — corporate network"
  }'
```

> **Rule:** exactly one of `cidr` / `ip_exact` / `asn` must be provided.

#### List All IP Rules

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
      "description":  "Internal testing network",
      "enabled":      1,
      "created_at":   "2025-04-23T12:00:00"
    }
  ]
}
```

#### Update a Rule

```bash
curl -X PATCH http://localhost:8000/api/v1/cloaking/rules/ip/1 \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

#### Delete a Rule

```bash
curl -X DELETE http://localhost:8000/api/v1/cloaking/rules/ip/1
```

---

### UA Rules

#### Add a Pattern (regex)

```bash
curl -X POST http://localhost:8000/api/v1/cloaking/rules/ua \
  -H "Content-Type: application/json" \
  -d '{
    "pattern":      "mycompanybot",
    "visitor_type": "bot",
    "confidence":   0.99,
    "description":  "Internal company bot"
  }'
```

The pattern is a case-insensitive regular expression. Examples of valid patterns:

```json
"pattern": "mybot"                      // simple substring
"pattern": "\\bmybot\\b"               // exact word boundary
"pattern": "mybot/[0-9]+"              // with version number
"pattern": "(crawler|spider)\\.myco"   // multiple alternatives
```

#### List All UA Rules

```bash
curl http://localhost:8000/api/v1/cloaking/rules/ua
```

#### Update a UA Rule

```bash
curl -X PATCH http://localhost:8000/api/v1/cloaking/rules/ua/1 \
  -H "Content-Type: application/json" \
  -d '{
    "confidence": 0.95,
    "description": "Updated description"
  }'
```

#### Delete a UA Rule

```bash
curl -X DELETE http://localhost:8000/api/v1/cloaking/rules/ua/1
```

---

## Testing Decisions

The `/test` endpoint lets you verify any combination of IP + UA + headers **without real traffic** — useful when setting up or validating rules.

### Example: Test Googlebot

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

### Example: Real iPhone with Full Headers

```bash
curl -X POST http://localhost:8000/api/v1/cloaking/test \
  -H "Content-Type: application/json" \
  -d '{
    "ip": "8.8.8.8",
    "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "headers": {
      "accept-language":  "en-US,en;q=0.9",
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

### Example: Validate a Custom Rule After Adding It

```bash
# 1. Add the rule
curl -X POST http://localhost:8000/api/v1/cloaking/rules/ua \
  -d '{"pattern":"mybot","visitor_type":"bot","confidence":0.99,"description":"My bot"}'

# 2. Confirm it fires
curl -X POST http://localhost:8000/api/v1/cloaking/test \
  -d '{"ip":"1.2.3.4","user_agent":"MyBot/2.0 (crawler)"}'
```

---

## Audit Log and Statistics

Every engine decision is written to the `cloaking_decisions_log` table. This allows you to:
- See which IPs/UAs were classified as bots
- Analyze false positives
- Track trends over time

### View Recent Decisions

```bash
# Last 50 decisions
curl "http://localhost:8000/api/v1/cloaking/log?limit=50"

# Bots only
curl "http://localhost:8000/api/v1/cloaking/log?visitor_type=bot&limit=100"

# By a specific IP
curl "http://localhost:8000/api/v1/cloaking/log?ip=66.249.64.1"
```

**Response:**
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

### Aggregated Statistics

```bash
# Last 7 days
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

## Built-in Rules

Built-in rules are loaded from `app/core/cloaking/known_data.py` at server startup and **are not stored in the database** — this guarantees their integrity. They can only be modified by editing the source code.

### Built-in IP Ranges

| Platform | Ranges | Type | Confidence |
|----------|:------:|------|:----------:|
| Facebook / Meta | 13 | bot | 0.97 |
| Facebook Ads | 3 | ad_review | 0.90–0.93 |
| Google Search | 11 | bot | 0.97–0.98 |
| Google Ads | 2 | ad_review | 0.92 |
| Bing / Microsoft | 7 | bot | 0.95–0.97 |
| Apple | 3 | bot | 0.90–0.95 |
| Yandex | 13 | bot | 0.97 |
| Twitter / X | 3 | bot | 0.95 |
| LinkedIn | 3 | bot | 0.95 |
| AWS (data center) | 3 | suspicious | 0.55 |
| SEO tools | 4 | bot | 0.80–0.85 |

### Built-in ASNs

| ASN | Organization | Type |
|-----|--------------|------|
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

### Built-in UA Patterns (80+)

Categories:
- **Search crawlers**: Googlebot, Bingbot, Yandexbot, Baiduspider, DuckDuckBot, and more
- **Social crawlers**: facebookexternalhit, Twitterbot, LinkedInBot, Slackbot, Discordbot, WhatsApp, and more
- **Ad bots**: AdsBot-Google, mediapartners-google, YandexDirect, and more
- **SEO tools**: SemrushBot, AhrefsBot, MJ12bot, Screaming Frog, and more
- **Monitoring**: UptimeRobot, Pingdom, New Relic, Datadog, and more
- **HTTP clients**: curl, wget, python-requests, Go, Java, libwww-perl, and more
- **Headless browsers**: PhantomJS, HeadlessChrome, Selenium, Puppeteer, Playwright

---

## Code Architecture

```
app/core/cloaking/
├── __init__.py              Package public API
│
├── models.py                Data types
│   ├── VisitorType          Enum: real_user | bot | ad_review | suspicious
│   ├── CloakingAction       Enum: full_flow | seo_page | compliant_page | block
│   ├── DetectionSignal      Single signal with source, confidence, description
│   ├── CloakingDecision     Final decision (type + action + signal list)
│   ├── IPRule               DB record for an IP rule
│   └── UARuleRecord         DB record for a UA rule
│
├── known_data.py            Built-in data (not in DB)
│   ├── KNOWN_IP_RANGES      70+ CIDR ranges
│   ├── KNOWN_ASNS           15 autonomous systems
│   └── KNOWN_UA_PATTERNS    80+ regex patterns
│
├── ip_detector.py           IP detector
│   └── IPDetector
│       ├── detect(ip, asn)          → List[DetectionSignal]
│       └── load_custom_rules(rules)   hot-reload
│
├── ua_detector.py           UA detector
│   └── UADetector
│       ├── detect(user_agent)         → List[DetectionSignal]
│       └── load_custom_rules(rules)   hot-reload
│
├── behavior_detector.py     Behavioral detector
│   └── BehaviorDetector
│       └── detect(headers, cookies, referer) → List[DetectionSignal]
│
└── engine.py                Orchestrator
    ├── CloakingEngine
    │   ├── decide(ip, ua, headers, cookies, referer, asn) → CloakingDecision
    │   └── reload_rules(ip_rules, ua_rules)  hot-reload
    ├── CloakingConfig        Maps visitor types to actions
    ├── get_engine()          Get the singleton instance
    └── init_engine(config)   Initialize the singleton

app/api/cloaking_admin.py    Admin REST API (FastAPI router)
app/migrations/
└── add_cloaking_tables.py   SQLite table creation

Database (SQLite):
├── cloaking_ip_rules        Custom IP rules
├── cloaking_ua_rules        Custom UA rules
└── cloaking_decisions_log   Audit log of all decisions
```

### Rule Lifecycle

```
Server startup
      │
      ▼
init_engine()                  ← creates CloakingEngine
      │
      ▼
_load_all_rules() from DB      ← loads custom rules
      │
      ▼
engine.reload_rules()          ← IPDetector + UADetector rebuild
      │                          internal structures with custom +
      │                          built-in rules combined
      ▼
POST /api/v1/cloaking/rules/*  ← CRUD → immediately calls _load_all_rules()
                                  hot-reload, no server restart required
```

---

## Adding Built-in Rules via Code

To add new rules to the codebase (rather than via the API), edit `app/core/cloaking/known_data.py`:

```python
# Add a new CIDR to KNOWN_IP_RANGES:
("203.0.113.0/24", "bot", 0.97, "Example Corp crawler AS64496"),

# Add a new ASN to KNOWN_ASNS:
(64496, "bot", 0.90, "Example Corp AS64496"),

# Add a new UA pattern to KNOWN_UA_PATTERNS:
(r"\bexamplebot\b", "bot", 0.99, "Example Corp bot"),
```

After editing the file, restart the server.

---

## Links

- [Русская версия](cloaking_ru.md)
- [Main README](../README.md)
- [Swagger UI](http://localhost:8000/docs#/Cloaking%20Admin)
- Source code: `app/core/cloaking/`
