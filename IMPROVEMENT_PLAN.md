# DeferLink — План исправлений и улучшений

> Дата анализа: 2026-04-21  
> Всего найдено проблем: 37  
> Приоритеты: КРИТИЧНО → ВЫСОКИЙ → СРЕДНИЙ → НИЗКИЙ

---

## Критические (блокируют продакшн)

### [CRИТ-1] Слабый SECRET_KEY
**Файл:** `app/config.py:17`  
**Проблема:** Дефолтный `SECRET_KEY = "dev-secret-key-change-in-production"` — общеизвестная строка. Валидация срабатывает только в `ENVIRONMENT=production`, в dev-режиме уязвимость остаётся.  
**Последствия:** Подделка сессий, обход авторизации.  
**Исправление:**
```python
# config.py
import secrets

SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(32))

@validator("SECRET_KEY")
def validate_secret_key(cls, v):
    weak = {"dev-secret-key-change-in-production", "secret", "changeme"}
    if v in weak or len(v) < 32:
        raise ValueError("SECRET_KEY слишком слабый. Используй: secrets.token_urlsafe(32)")
    return v
```

---

## Высокий приоритет (исправить до релиза)

### [ВЫС-1] Отсутствие Rate Limiting
**Файл:** `app/main.py`  
**Проблема:** `RATE_LIMIT_PER_MINUTE=60` задан в конфиге, но middleware не реализован. Эндпоинт `/resolve` открыт для DDoS/брутфорса.  
**Исправление:** Добавить middleware через `fastapi-limiter` или встроенный счётчик:
```python
# requirements.txt: fastapi-limiter>=0.1.6, redis>=5.0

from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter

@router.post("/resolve", dependencies=[Depends(RateLimiter(times=60, seconds=60))])
async def resolve_session(...):
    ...
```

### [ВЫС-2] CORS разрешает все origins
**Файл:** `app/main.py:85-91`  
**Проблема:** `allow_origins=["*"]` в паре со слабым SECRET_KEY открывает путь для CSRF и XSS-атак.  
**Исправление:**
```python
# В production CORS_ORIGINS обязателен, пустой список = ошибка при старте
if settings.ENVIRONMENT == "production" and not settings.CORS_ORIGINS:
    raise RuntimeError("CORS_ORIGINS не задан для production")
```

### [ВЫС-3] Cookie без Secure-флага
**Файл:** `app/config.py`, `app/main.py:156-163`  
**Проблема:** `COOKIE_SECURE` по умолчанию `False`, `SameSite="lax"`. Сессионные куки передаются по HTTP.  
**Исправление:**
```python
# config.py
COOKIE_SECURE: bool = Field(default=True)  # принудительно True в production
COOKIE_SAMESITE: str = Field(default="strict")

# startup validation
if settings.ENVIRONMENT == "production" and not settings.COOKIE_SECURE:
    raise RuntimeError("COOKIE_SECURE должен быть True в production")
```

### [ВЫС-4] SSL Pinning отсутствует (iOS)
**Файл:** `DeferLinkTestApp/DeferLinkTestApp/NetworkManager.swift:39,63,85,128`  
**Проблема:** Используется дефолтный `URLSession` без валидации сертификата. Уязвимость MITM.  
**Исправление:** Реализовать `URLSessionDelegate` с проверкой certificate fingerprint:
```swift
func urlSession(_ session: URLSession,
                didReceive challenge: URLAuthenticationChallenge,
                completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
    // Сверить serverTrust с захардкоженным fingerprint
}
```

---

## Средний приоритет (исправить в ближайшем спринте)

### [СРД-1] N+1 запросов в статистике
**Файл:** `app/deeplink_handler.py:125-160`  
**Проблема:** `get_stats()` делает 5 отдельных SQL-запросов.  
**Исправление:**
```sql
SELECT
    COUNT(*) AS total,
    SUM(CASE WHEN is_resolved = 1 THEN 1 ELSE 0 END) AS resolved,
    SUM(CASE WHEN is_resolved = 0 THEN 1 ELSE 0 END) AS pending,
    AVG(match_confidence) AS avg_confidence,
    MAX(created_at) AS last_activity
FROM deeplink_sessions
WHERE created_at > datetime('now', '-24 hours');
```

### [СРД-2] Кэш без TTL и лимита размера
**Файл:** `app/core/intelligent_matcher.py:42-45`  
**Проблема:** `_device_similarity_cache` и `_timezone_cache` растут без ограничений.  
**Исправление:**
```python
from functools import lru_cache

@lru_cache(maxsize=10_000)
def _device_similarity(self, ua1: str, ua2: str) -> float:
    ...
```

### [СРД-3] Неправильный парсинг timestamp
**Файл:** `app/core/intelligent_matcher.py:555-570`  
**Проблема:** `_validate_temporal_patterns()` пытается парсить ISO-формат, но БД хранит SQLite TIMESTAMP. При ошибке возвращает 0.8 (нейтральный балл), маскируя проблему.  
**Исправление:** Стандартизировать формат хранения или использовать `datetime.fromisoformat()` с fallback:
```python
from dateutil.parser import parse as dateutil_parse

def _parse_timestamp(self, ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        try:
            return dateutil_parse(ts)
        except Exception:
            logger.warning("Не удалось распарсить timestamp: %s", ts)
            return None
```

### [СРД-4] Логирование чувствительных данных
**Файл:** `app/deeplink_handler.py:61-70`  
**Проблема:** User-Agent и IP-адреса попадают в логи напрямую.  
**Исправление:** Хэшировать или маскировать перед записью:
```python
import hashlib

def _sanitize_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()[:16] + "..."

logger.info("Session created for ip_hash=%s", _sanitize_ip(request.client.host))
```

### [СРД-5] Отсутствие CSRF защиты
**Файл:** `app/main.py`  
**Проблема:** POST-эндпоинты (`/resolve`, `/cleanup`) не проверяют CSRF-токен.  
**Исправление:** Добавить `starlette-csrf` middleware или проверять заголовок `X-Requested-With`.

### [СРД-6] Нет Connection Pooling для SQLite
**Файл:** `app/database.py:80`  
**Проблема:** Каждая операция открывает новое соединение.  
**Исправление:**
```python
import threading

_local = threading.local()

def get_connection() -> sqlite3.Connection:
    if not hasattr(_local, "conn"):
        _local.conn = sqlite3.connect(settings.DATABASE_PATH, check_same_thread=False)
    return _local.conn
```

### [СРД-7] Отсутствие таймаутов (iOS)
**Файл:** `DeferLinkTestApp/DeferLinkTestApp/NetworkManager.swift`  
**Исправление:**
```swift
let config = URLSessionConfiguration.default
config.timeoutIntervalForRequest = 10
config.timeoutIntervalForResource = 30
let session = URLSession(configuration: config)
```

### [СРД-8] Null check в нормализации fingerprint
**Файл:** `app/deeplink_handler.py:230-260`  
**Проблема:** `_normalize_fingerprint()` возвращает неполный словарь если все поля None — вызывает KeyError в matcher.  
**Исправление:** Добавить ранний выход:
```python
def _normalize_fingerprint(fp: dict) -> Optional[dict]:
    critical_fields = ["user_agent", "screen_resolution", "timezone"]
    if not any(fp.get(f) for f in critical_fields):
        raise InvalidFingerprintError("Fingerprint не содержит обязательных полей")
    ...
```

---

## Низкий приоритет (рефакторинг и улучшения)

### [НИЗ-1] God Object: IntelligentMatcher (~600 строк)
**Файл:** `app/core/intelligent_matcher.py`  
**Разбить на:**
- `TimezoneComparator`
- `ScreenComparator`  
- `DeviceSimilarityScorer`
- `TemporalValidator`
- `FingerprintQualityAssessor`

### [НИЗ-2] Magic numbers в алгоритме
**Файл:** `app/core/intelligent_matcher.py:156,296,565-575`  
**Исправление:** Вынести в `constants.py` или секцию конфига:
```python
class MatcherConfig:
    HIGH_CONFIDENCE_THRESHOLD = 0.85
    MEDIUM_CONFIDENCE_THRESHOLD = 0.70
    LOW_CONFIDENCE_THRESHOLD = 0.50
    SCREEN_TOLERANCE_PX = 60
    SESSION_WINDOW_TIGHT_SEC = 10
    SESSION_WINDOW_NORMAL_SEC = 600
```

### [НИЗ-3] Разнородная обработка ошибок
**Файл:** несколько файлов в `app/api/`  
**Исправление:** Создать иерархию исключений:
```python
# app/exceptions.py
class DeferLinkError(Exception): ...
class InvalidFingerprintError(DeferLinkError): ...
class SessionExpiredError(DeferLinkError): ...
class MatchingError(DeferLinkError): ...
```

### [НИЗ-4] Неструктурированные логи
**Проблема:** Смесь INFO/WARNING/ERROR для одинаковых событий. Логи на русском и английском.  
**Исправление:** Использовать `python-json-logger`, выбрать один язык (EN), стандартизировать уровни.

### [НИЗ-5] Тесты полностью отсутствуют
**Исправление:**
```
tests/
  conftest.py           # pytest fixtures, mock DB
  test_matcher.py       # unit tests IntelligentMatcher
  test_deeplinks.py     # integration tests API
  test_fingerprint.py   # fingerprint normalization edge cases
```
iOS: заменить `DeferLinkService.runFullTest()` на XCTest с mock URLSession.

### [НИЗ-6] Singleton антипаттерн
**Файлы:** `app/database.py:206`, `NetworkManager.swift:5`  
**Исправление:** Dependency Injection — передавать зависимости явно, а не через глобальные синглтоны.

### [НИЗ-7] Нет версионирования API
**Файл:** `app/api/deeplinks.py:8`  
**Исправление:** Добавить префикс `/api/v1/`, задокументировать политику совместимости.

### [НИЗ-8] Мертвый код и неиспользуемые импорты
**Файлы:** `app/utils.py` (функция `calculate_session_lifetime_hours`), `app/deeplink_handler.py` (импорт `HTTPException`)  
**Исправление:** Удалить или интегрировать.

---

## Архитектурные улучшения (v2+)

| Улучшение | Обоснование |
|-----------|-------------|
| **Prometheus / OpenTelemetry** | `ENABLE_METRICS` задан в конфиге, но не реализован |
| **Audit log** | Трекинг кто/когда создал/зарезолвил сессию — нужен для compliance |
| **Webhook callbacks** | Сейчас клиенты вынуждены поллить; нотификации уменьшат нагрузку |
| **Circuit Breaker** | Защита от каскадных сбоев при медленном matcher |
| **Миграция на async DB** | `sqlite3` синхронный — использовать `aiosqlite` или перейти на PostgreSQL |

---

## Порядок выполнения

```
Неделя 1 (Безопасность)
  ├── КРИТ-1: SECRET_KEY валидация
  ├── ВЫС-1: Rate Limiting
  ├── ВЫС-2: CORS исправление
  └── ВЫС-3: Cookie Secure

Неделя 2 (Надёжность)
  ├── СРД-3: Timestamp парсинг
  ├── СРД-4: Sanitize логи
  ├── СРД-5: CSRF защита
  ├── СРД-8: Null check fingerprint
  └── ВЫС-4: SSL pinning (iOS)

Неделя 3 (Производительность)
  ├── СРД-1: N+1 → одиночный запрос
  ├── СРД-2: LRU Cache с TTL
  └── СРД-6: Connection pooling

Неделя 4 (Качество кода)
  ├── НИЗ-3: Иерархия исключений
  ├── НИЗ-4: Structured logging
  ├── НИЗ-5: Написать тесты
  └── НИЗ-2: Constants вместо magic numbers

Бэклог (v2)
  ├── НИЗ-1: Разбить IntelligentMatcher
  ├── НИЗ-6: Убрать Singleton
  ├── НИЗ-7: API versioning
  └── Архитектурные улучшения
```

---

---

## Реализовано: IAB Escape + DeviceCheck (2026-04-22)

### Архитектура многоуровневого матчинга

```
Tier 1  clipboard_token       100%   Escape-страница → clipboard → приложение
Tier 2  safari_cookie         ~99%   SFSafariViewController shared cookie jar
Tier 3  device_check_token    ~97%   Apple DeviceCheck (нативный, верифицирован)
Tier 4  fingerprint           60-90% IntelligentMatcher (существующий алгоритм)
```

### Новые файлы

| Файл | Назначение |
|------|-----------|
| `app/core/iab_detector.py` | Детектирование Facebook/Instagram/TikTok IAB по UA |
| `app/core/safari_escape.py` | HTML-страница: clipboard write + App Store redirect |
| `app/core/devicecheck.py` | Серверная верификация Apple DeviceCheck токенов |
| `app/migrations/add_devicecheck_fields.py` | Миграция БД (новые колонки) |
| `iOS/DeviceCheckManager.swift` | Генерация DC токена + кэширование |

### Ключевой трюк: Clipboard Handoff

Когда Facebook IAB открывает нашу ссылку:
1. Сервер детектирует IAB → возвращает escape-страницу вместо прямого редиректа
2. JavaScript: `document.execCommand('copy')` — работает без user gesture в WKWebView
3. В буфер попадает `"deferlink:<session_id>"`
4. Редирект → App Store → установка
5. Приложение читает `UIPasteboard.general.string` → 100% матч

### SFSafariViewController Flow (для Safari-трафика)

```
App first launch
    → открыть SFSafariViewController (невидимый, alpha=0)
    → GET /safari-resolve
    → сервер читает cookie (shared с Safari)
    → redirect: deferlink://resolved?session_id=<id>
    → SceneDelegate.scene(_:openURLContexts:) → handleSafariResolveCallback
    → закрыть SFSafariViewController
    → передать session_id в resolve
```

### Настройка DeviceCheck

```env
DEVICECHECK_ENABLED=true
DEVICECHECK_TEAM_ID=ABCDE12345         # Apple Team ID
DEVICECHECK_KEY_ID=ABC123DEF4          # Key ID из Apple Developer Console
DEVICECHECK_KEY_PATH=/secrets/AuthKey_ABC123DEF4.p8
DEVICECHECK_SANDBOX=true               # false в production
```

В Xcode: Signing & Capabilities → + Capability → DeviceCheck

### Настройка URL Scheme (iOS)

В `Info.plist` → URL Types → добавить:
```xml
<key>CFBundleURLSchemes</key>
<array>
  <string>deferlink</string>
</array>
```

В `SceneDelegate.swift`:
```swift
func scene(_ scene: UIScene, openURLContexts contexts: Set<UIOpenURLContext>) {
    if let url = contexts.first?.url {
        deferLinkService.handleSafariResolveCallback(url: url)
    }
}
```

*Обновлено: 2026-04-22*
