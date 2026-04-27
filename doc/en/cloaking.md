# Cloaking engine

The cloaking subsystem decides what to serve to the visitor on `GET /dl`. It must distinguish four classes:

* **Real user** — full deferred deep-link flow.
* **Bot** (search/social crawler) — show an SEO-friendly page.
* **Ad reviewer** (Facebook/Google/TikTok ad reviewer) — show a compliant page that won't get the campaign banned.
* **Suspicious** — inconclusive signals; configurable, defaults to "log and let through".

All code lives under `app/core/cloaking/`.

## Module map

| File | Role |
|---|---|
| `engine.py` | Aggregation, thresholds, action mapping. Public entry point `CloakingEngine.decide(...)`. |
| `ip_detector.py` | Exact / CIDR / ASN matching. Builtins from `known_data.py`, customs from DB. |
| `ua_detector.py` | Compiled regex patterns. Custom rules win over builtins. |
| `behavior_detector.py` | Header heuristics — weak signals, only ever push to `SUSPICIOUS`. |
| `models.py` | `VisitorType`, `CloakingAction`, `DetectionSignal`, `CloakingDecision`, `IPRule`, `UARuleRecord`. |
| `known_data.py` | Curated builtin IP ranges, ASNs, UA regexes (Google, Facebook, Bingbot, headless browsers, …). |

## Scoring model

Each detector returns zero or more `DetectionSignal` objects. Every signal carries:

```
source:        "ip_exact" | "ip_cidr" | "ip_asn" | "ua_regex" | "behavior"
description:   human-readable
visitor_type:  REAL_USER | BOT | AD_REVIEW | SUSPICIOUS
confidence:    0.0 .. 1.0
matched_value: what triggered the signal
```

`CloakingEngine._classify(...)` aggregates them in three steps:

1. **Per-type Bayesian accumulation**, restricted to *authoritative* signals (IP + UA only):

   ```
   score(vtype) = 1 − ∏ (1 − cᵢ)   for every signal of that vtype
   ```

   This guarantees that two independent 0.6 signals combine to ≈0.84, but no single weak signal can dominate.

2. **Threshold cascade**:

   * If any per-type score ≥ `HARD_THRESHOLD = 0.88` → that visitor type wins immediately.
   * Else if any per-type score ≥ `SOFT_THRESHOLD = 0.65` → that type wins.
   * Else the engine falls back to behavioural-only check (next step).

   When several types pass a threshold, ties are broken by `_TYPE_PRIORITY`: `AD_REVIEW (3) > BOT (2) > SUSPICIOUS (1) > REAL_USER (0)`.

3. **Behavioural boost / cap**:

   * Behavioural signals can *boost* the winner's confidence by up to `BOT_SUSPICION_BOOST = 0.15` (computed as `min(0.15, mean(bh_confidence) × 0.3)`).
   * Behavioural signals **alone** can never elevate beyond `SUSPICIOUS`. If no IP/UA fired, the engine takes the combined behavioural score and only flips to `SUSPICIOUS` when it reaches `CloakingConfig.suspicious_min_confidence` (default `0.70`).

The `CloakingDecision` returned by the engine carries the chosen `visitor_type`, `confidence`, the resolved `CloakingAction`, the original IP/UA, and the full list of contributing signals (good for the admin log).

## Action mapping

`CloakingConfig.action_map` defaults:

| Visitor type | Default action |
|---|---|
| `REAL_USER`   | `FULL_FLOW`        |
| `BOT`         | `SEO_PAGE`         |
| `AD_REVIEW`   | `COMPLIANT_PAGE`   |
| `SUSPICIOUS`  | `SUSPICIOUS_FLOW`  |

`SUSPICIOUS_FLOW` behaves like `FULL_FLOW` but the request is logged at INFO. `BLOCK` is available but not used by default — it returns 403 / empty body.

If `visitor_type == SUSPICIOUS` and `confidence < suspicious_min_confidence`, the engine downgrades to `FULL_FLOW`. This avoids over-blocking on header-only evidence.

## IP detector

* Builtins live in `known_data.KNOWN_IP_RANGES` (CIDR + visitor type + confidence + description) and `KNOWN_ASNS`. Curated for Google, Facebook, Bing, common scrapers, ad networks.
* Custom rules from the DB (`cloaking_ip_rules`) are loaded via `IPDetector.load_custom_rules(rules)`. Each `IPRule` is one of: exact `ip_exact`, `cidr`, or `asn`. The detector merges custom + builtin rules and re-sorts CIDR networks by `prefixlen DESC` so the most specific match wins.
* `detect(ip, asn=None)` returns up to three signals — exact, CIDR (first/most-specific match only), ASN.
* Lookup is O(N) over a flat list — fine for tens of thousands of ranges. If you push past that, swap in a radix tree (`pytricia`).

## UA detector

* Builtins in `known_data.KNOWN_UA_PATTERNS` — case-insensitive regexes for Googlebot, Bingbot, FacebookExternalHit, AdsBot, headless browsers, Selenium/Playwright/Puppeteer markers, etc.
* Custom rules from `cloaking_ua_rules`; the detector validates regex syntax and silently drops invalid patterns with a warning.
* All matching patterns are returned, deduplicated by `(visitor_type, description)` keeping the highest-confidence one. The engine then picks the strongest contribution per visitor type.

## Behaviour detector

Pure header inspection — no network I/O, no DB calls. All signals map to `VisitorType.SUSPICIOUS`, by design.

| Key | Weight | Trigger |
|---|---:|---|
| `no_accept_language` | 0.50 | Empty / missing `Accept-Language` |
| `no_sec_fetch_site`  | 0.45 | Empty / missing `Sec-Fetch-Site` |
| `no_accept`          | 0.30 | Missing `Accept` |
| `minimal_accept`     | 0.25 | `Accept: */*` |
| `no_accept_encoding` | 0.25 | No `Accept-Encoding` |
| `connection_close`   | 0.15 | `Connection: close` and no keep-alive |
| `no_referer`         | 0.10 | No `Referer` |
| `no_cookies`         | 0.10 | No cookies in the request |

Cookies are passed in as a dict; the engine itself extracts them from FastAPI's `Request` in `app/main.py`. The `Referer` is read both from the explicit parameter and from the headers dict (the parameter wins when set).

## Custom rules — admin API

`/api/v1/cloaking/...` (see [`api-reference.md`](api-reference.md#cloaking-admin-appapicloaking_adminpy)) exposes CRUD over `cloaking_ip_rules` and `cloaking_ua_rules`. After insert/update/delete, the API calls `CloakingEngine.reload_rules(...)` so the change is picked up immediately, without a restart.

Field shape mirrors `IPRule` / `UARuleRecord` exactly:

```jsonc
// IP rule
{
  "id":           42,
  "cidr":         "31.13.24.0/21",   // OR ip_exact OR asn — exactly one
  "ip_exact":     null,
  "asn":          null,
  "visitor_type": "ad_review",
  "confidence":   0.95,
  "description":  "Facebook ad review",
  "enabled":      true
}

// UA rule
{
  "id":           7,
  "pattern":      "(?i)facebookexternalhit",
  "visitor_type": "bot",
  "confidence":   0.97,
  "description":  "Facebook crawler",
  "enabled":      true
}
```

## Decision log

Every `CloakingDecision` for a real `/dl` hit is written to `cloaking_decision_log` (`migrations/add_cloaking_tables.py`) with the visitor_type, action, confidence and a JSON-serialised list of signals. `GET /api/v1/cloaking/log` paginates that table for debugging; `/api/v1/cloaking/stats` returns counts per visitor type over a window.

## Testing a UA / IP pair

`POST /api/v1/cloaking/test` runs the engine against a synthetic input — useful when authoring a new rule:

```jsonc
POST /api/v1/cloaking/test
{
  "ip":         "66.249.66.1",
  "user_agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
  "headers":    { "accept": "*/*" },
  "cookies":    {}
}
```

Response is the full `CloakingDecision` JSON, including every contributing signal with its weight — the same shape that ends up in the decision log.

## Hot-reload

`CloakingEngine.reload_rules(ip_rules, ua_rules)` is safe to call at any moment from any task — it rebuilds the internal lists in place. The admin endpoints call it after every mutation, and `app.main.lifespan` calls it once on startup with the rules read from SQLite.
