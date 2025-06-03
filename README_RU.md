# DeferLink - Полная документация

## Содержание

1. [Обзор системы](#обзор-системы)
2. [Архитектура](#архитектура)
3. [Установка и настройка](#установка-и-настройка)
4. [API Документация](#api-документация)
5. [Конфигурация](#конфигурация)
6. [iOS/Android SDK](#iosandroid-sdk)
7. [Примеры использования](#примеры-использования)
8. [Мониторинг и аналитика](#мониторинг-и-аналитика)
9. [Безопасность](#безопасность)
10. [Развертывание](#развертывание)
11. [Устранение неполадок](#устранение-неполадок)

---

## Обзор системы

**DeferLink** - это интеллектуальная система отложенного связывания (deferred deep linking) для мобильных приложений, которая позволяет сохранять контекст пользователя между веб-браузером и мобильным приложением.

### Основные возможности

- **Отложенные диплинки**: Сохранение контекста для пользователей без установленного приложения
- **Умное сопоставление**: Алгоритм fingerprinting для связывания устройств
- **Кроссплатформенность**: Поддержка iOS и Android
- **Аналитика**: Детальная статистика и мониторинг
- **Безопасность**: Защита от мошенничества и злоупотреблений
- **Масштабируемость**: Готовность к высоким нагрузкам

### Как это работает

1. **Создание сессии**: Пользователь кликает на ссылку в браузере
2. **Сбор fingerprint**: Система собирает данные об устройстве
3. **Редирект**: Пользователь перенаправляется в App Store/Play Store
4. **Сопоставление**: После установки приложение ищет совпадающую сессию
5. **Восстановление контекста**: Приложение получает исходные данные

---

## Архитектура

### Компоненты системы

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web Browser   │────│  DeferLink API  │────│  Mobile App     │
│   (Fingerprint) │    │   (Matching)    │    │  (Resolution)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                       ┌─────────────────┐
                       │    Database     │
                       │   (Sessions)    │
                       └─────────────────┘
```

### Структура проекта

```tree
deferlink/
├── app/                    # Основное приложение
│   ├── __init__.py
│   ├── main.py            # FastAPI приложение
│   ├── config.py          # Конфигурация
│   ├── database.py        # База данных
│   ├── models.py          # Pydantic модели
│   ├── deeplink_handler.py # Основная логика
│   ├── fingerprint.py     # Fingerprinting
│   ├── analytics.py       # Аналитика
│   └── security.py        # Безопасность
├── ios_app/               # iOS тестовое приложение
│   ├── Views/
│   ├── Services/
│   ├── Models/
│   └── Utils/
├── data/                  # База данных
├── tests/                 # Тесты
├── requirements.txt       # Зависимости
├── run.py                # Точка входа
└── README.md
```

---

## Установка и настройка

### Системные требования

- Python 3.8+
- SQLite 3.x
- 512MB RAM минимум
- 1GB свободного места

### Установка

1. **Клонирование репозитория**

```bash
git clone https://github.com/your-repo/deferlink.git
cd deferlink
```

2. **Создание виртуального окружения**

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows
```

3. **Установка зависимостей**

```bash
pip install -r requirements.txt
```

4. **Настройка конфигурации**

```bash
cp .env.example .env
# Отредактируйте .env файл
```

5. **Запуск**

```bash
python run.py
```

### Docker (опционально)

```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["python", "run.py"]
```

```bash
docker build -t deferlink .
docker run -p 8000:8000 deferlink
```

---

## API Документация

### Базовый URL

```
http://localhost:8000
```

### Аутентификация

API использует session-based аутентификацию с cookies.

---

### Endpoints

#### 1. Health Check

**GET** `/health`

Проверка состояния сервиса.

**Ответ:**

```json
{
  "status": "healthy",
  "timestamp": "2025-06-03T19:43:03.774Z",
  "version": "1.0.0"
}
```

---

#### 2. Создание сессии диплинка

**POST** `/deeplink/create`

Создает новую сессию для отложенного диплинка.

**Тело запроса:**

```json
{
  "url": "myapp://product/123",
  "promo_id": "SUMMER2025",
  "domain": "example.com",
  "campaign": "social_media",
  "fingerprint": {
    "user_agent": "Mozilla/5.0...",
    "language": "en-US",
    "timezone": "America/New_York",
    "screen_width": 1920,
    "screen_height": 1080,
    "platform": "web"
  },
  "custom_data": {
    "utm_source": "facebook",
    "utm_campaign": "summer_sale"
  }
}
```

**Ответ:**

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": true,
  "expires_at": "2025-06-05T19:43:03.774Z",
  "redirect_url": "https://apps.apple.com/app/myapp"
}
```

**Коды ошибок:**

- `400` - Некорректные данные
- `429` - Превышен лимит запросов
- `500` - Внутренняя ошибка сервера

---

#### 3. Разрешение диплинка

**POST** `/deeplink/resolve`

Поиск соответствующей сессии для мобильного приложения.

**Тело запроса:**

```json
{
  "fingerprint": {
    "model": "iPhone15,3",
    "system_name": "iOS",
    "system_version": "17.1.1",
    "language": "en-US",
    "timezone": "America/New_York",
    "screen_width": 393,
    "screen_height": 852,
    "platform": "ios",
    "app_version": "1.2.0",
    "idfv": "12345678-1234-1234-1234-123456789012"
  },
  "timeout_seconds": 30
}
```

**Ответ (найдено совпадение):**

```json
{
  "success": true,
  "matched": true,
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "url": "myapp://product/123",
  "promo_id": "SUMMER2025",
  "domain": "example.com",
  "campaign": "social_media",
  "custom_data": {
    "utm_source": "facebook",
    "utm_campaign": "summer_sale"
  },
  "confidence_score": 0.92,
  "matched_fields": ["timezone", "language", "screen_width", "screen_height"],
  "created_at": "2025-06-03T19:43:03.774Z"
}
```

**Ответ (совпадение не найдено):**

```json
{
  "success": true,
  "matched": false,
  "message": "No matching session found",
  "confidence_score": 0.0
}
```

---

#### 4. Получение статистики

**GET** `/stats`

Получение общей статистики системы.

**Ответ:**

```json
{
  "total_sessions": 15420,
  "active_sessions": 234,
  "resolved_sessions": 12180,
  "success_rate": 78.95,
  "sessions_last_hour": 45,
  "average_confidence": 0.847,
  "timestamp": "2025-06-03T19:43:03.774Z",
  "matcher_stats": {
    "total_requests": 18650,
    "successful_matches": 12180,
    "failed_matches": 6470,
    "average_confidence": 0.823
  }
}
```

---

#### 5. Детальная статистика

**GET** `/stats/detailed`

Расширенная статистика с разбивкой по времени.

**Параметры запроса:**

- `period` - период (hour, day, week, month)
- `from_date` - начальная дата (ISO 8601)
- `to_date` - конечная дата (ISO 8601)

**Пример:**

```
GET /stats/detailed?period=day&from_date=2025-06-01T00:00:00Z&to_date=2025-06-03T23:59:59Z
```

**Ответ:**

```json
{
  "period": "day",
  "from_date": "2025-06-01T00:00:00Z",
  "to_date": "2025-06-03T23:59:59Z",
  "data": [
    {
      "date": "2025-06-01",
      "sessions_created": 520,
      "sessions_resolved": 405,
      "success_rate": 77.88,
      "average_confidence": 0.834,
      "platforms": {
        "ios": 312,
        "android": 208
      }
    },
    {
      "date": "2025-06-02",
      "sessions_created": 485,
      "sessions_resolved": 390,
      "success_rate": 80.41,
      "average_confidence": 0.851,
      "platforms": {
        "ios": 290,
        "android": 195
      }
    }
  ],
  "totals": {
    "sessions_created": 1005,
    "sessions_resolved": 795,
    "success_rate": 79.10,
    "average_confidence": 0.842
  }
}
```

---

#### 6. Получение сессии

**GET** `/session/{session_id}`

Получение информации о конкретной сессии.

**Ответ:**

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "url": "myapp://product/123",
  "promo_id": "SUMMER2025",
  "status": "resolved",
  "created_at": "2025-06-03T19:43:03.774Z",
  "resolved_at": "2025-06-03T19:45:12.328Z",
  "expires_at": "2025-06-05T19:43:03.774Z",
  "fingerprint": {
    "user_agent": "Mozilla/5.0...",
    "platform": "web"
  },
  "resolution_fingerprint": {
    "model": "iPhone15,3",
    "platform": "ios"
  },
  "confidence_score": 0.92
}
```

---

#### 7. Удаление сессии

**DELETE** `/session/{session_id}`

Удаление сессии (только для тестирования).

**Ответ:**

```json
{
  "success": true,
  "message": "Session deleted successfully"
}
```

---

#### 8. Bulk операции

**POST** `/sessions/cleanup`

Очистка истекших сессий.

**Ответ:**

```json
{
  "deleted_count": 150,
  "success": true
}
```

---

### Коды ошибок

| Код | Описание | Пример |
|-----|----------|---------|
| 400 | Некорректный запрос | Отсутствуют обязательные поля |
| 401 | Не авторизован | Отсутствует или неверный токен |
| 404 | Не найдено | Сессия не существует |
| 429 | Превышен лимит | Слишком много запросов |
| 500 | Внутренняя ошибка | Ошибка базы данных |

**Формат ошибки:**

```json
{
  "error": "validation_error",
  "message": "Invalid fingerprint data",
  "details": {
    "field": "screen_width",
    "issue": "must be positive integer"
  },
  "timestamp": "2025-06-03T19:43:03.774Z"
}
```

---

## Конфигурация

### Переменные окружения (.env)

```bash
# Безопасность
SECRET_KEY=your-super-secret-key-change-this-in-production
COOKIE_SECURE=false  # true для HTTPS
COOKIE_HTTPONLY=true
COOKIE_SAMESITE=lax

# База данных
DATABASE_PATH=data/deeplinks.db

# API
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=1

# Настройки диплинков
DEFAULT_TTL_HOURS=48           # Время жизни сессии
MAX_FINGERPRINT_DISTANCE=2    # Максимальное расстояние для сопоставления
CLEANUP_INTERVAL_MINUTES=30   # Интервал очистки

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_BURST=10

# CORS
CORS_ORIGINS=*  # В продакшене указать конкретные домены

# Мониторинг
ENABLE_METRICS=false
METRICS_PORT=9090
LOG_LEVEL=INFO

# Аналитика
ENABLE_ANALYTICS=true
ANALYTICS_RETENTION_DAYS=90

# Безопасность
MAX_CONTENT_LENGTH=1048576  # 1MB
REQUEST_TIMEOUT=30

# Обнаружение мошенничества
FRAUD_DETECTION_ENABLED=false
FRAUD_RISK_THRESHOLD=0.8

# Оптимизация алгоритма
AUTO_OPTIMIZE_WEIGHTS=false
```

### Продакшен конфигурация

```bash
# Продакшен настройки
SECRET_KEY=your-production-secret-key
COOKIE_SECURE=true
API_WORKERS=4
RATE_LIMIT_PER_MINUTE=1000
ENABLE_METRICS=true
FRAUD_DETECTION_ENABLED=true
LOG_LEVEL=WARNING
```

---

## iOS/Android SDK

### iOS Swift SDK

#### Установка

1. Добавьте файлы из папки `ios_app/` в ваш проект
2. Настройте зависимости в `Package.swift` или вручную

#### Использование

```swift
import DeferLinkSDK

class AppDelegate: UIResponder, UIApplicationDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {

        // Инициализация DeferLink
        DeferLinkService.configure(
            baseURL: "https://your-deferlink-server.com",
            timeout: 30.0
        )

        // Попытка разрешения диплинка
        DeferLinkService.shared.resolveDeepLink { result in
            DispatchQueue.main.async {
                switch result {
                case .success(let response):
                    if response.matched {
                        // Обработать диплинк
                        self.handleDeepLink(response.url, data: response.customData)
                    }
                case .failure(let error):
                    print("DeferLink error: \(error)")
                }
            }
        }

        return true
    }

    private func handleDeepLink(_ url: String?, data: [String: Any]?) {
        // Ваша логика обработки диплинка
        guard let url = url else { return }

        if url.contains("product") {
            // Открыть страницу продукта
        } else if url.contains("promo") {
            // Показать промо
        }
    }
}
```

#### Конфигурация службы

```swift
import SwiftUI

@main
struct MyApp: App {
    @StateObject private var deferLinkService = DeferLinkService()
    @StateObject private var networkManager = NetworkManager()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(deferLinkService)
                .environmentObject(networkManager)
        }
    }
}
```

#### Сбор Fingerprint

```swift
// Автоматический сбор fingerprint
let fingerprint = FingerprintCollector.collectFingerprint()

// Ручной сбор
var fingerprint = FingerprintData()
fingerprint.model = UIDevice.current.model
fingerprint.systemName = UIDevice.current.systemName
fingerprint.systemVersion = UIDevice.current.systemVersion
// ... другие параметры
```

### Android SDK (концепт)

```kotlin
class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Инициализация DeferLink
        DeferLink.configure("https://your-deferlink-server.com")

        // Разрешение диплинка
        DeferLink.resolve(this) { result ->
            when (result) {
                is DeferLinkResult.Success -> {
                    if (result.matched) {
                        handleDeepLink(result.url, result.customData)
                    }
                }
                is DeferLinkResult.Error -> {
                    Log.e("DeferLink", "Error: ${result.error}")
                }
            }
        }
    }

    private fun handleDeepLink(url: String?, data: Map<String, Any>?) {
        // Обработка диплинка
    }
}
```

---

## Примеры использования

### Веб интеграция

```html
<!DOCTYPE html>
<html>
<head>
    <title>Smart Link Example</title>
</head>
<body>
    <button onclick="createDeferLink()">Открыть в приложении</button>

    <script>
    async function createDeferLink() {
        try {
            const fingerprint = await collectFingerprint();

            const response = await fetch('https://your-server.com/deeplink/create', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    url: 'myapp://product/123',
                    promo_id: 'SUMMER2025',
                    domain: window.location.hostname,
                    fingerprint: fingerprint,
                    custom_data: {
                        utm_source: 'website',
                        product_id: '123'
                    }
                })
            });

            const data = await response.json();

            if (data.success) {
                // Редирект в App Store/Play Store
                window.location.href = data.redirect_url;
            }
        } catch (error) {
            console.error('Error creating defer link:', error);
        }
    }

    async function collectFingerprint() {
        return {
            user_agent: navigator.userAgent,
            language: navigator.language,
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
            screen_width: screen.width,
            screen_height: screen.height,
            platform: 'web'
        };
    }
    </script>
</body>
</html>
```

### React интеграция

```jsx
import React, { useEffect } from 'react';

const DeferLinkButton = ({ productId, promoId }) => {
    const createDeferLink = async () => {
        try {
            const fingerprint = {
                user_agent: navigator.userAgent,
                language: navigator.language,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                screen_width: screen.width,
                screen_height: screen.height,
                platform: 'web'
            };

            const response = await fetch('/api/deeplink/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    url: `myapp://product/${productId}`,
                    promo_id: promoId,
                    domain: window.location.hostname,
                    fingerprint,
                    custom_data: {
                        product_id: productId,
                        source: 'web_app'
                    }
                })
            });

            const data = await response.json();
            if (data.success) {
                window.location.href = data.redirect_url;
            }
        } catch (error) {
            console.error('DeferLink error:', error);
        }
    };

    return (
        <button onClick={createDeferLink} className="defer-link-btn">
            Открыть в приложении
        </button>
    );
};

export default DeferLinkButton;
```

---

## Мониторинг и аналитика

### Встроенная аналитика

```python
# Получение метрик
from app.analytics import AnalyticsCollector

analytics = AnalyticsCollector()

# Основные метрики
stats = analytics.get_basic_stats()
print(f"Success rate: {stats['success_rate']:.2f}%")

# Детальная аналитика
detailed = analytics.get_detailed_stats(
    from_date="2025-06-01",
    to_date="2025-06-03",
    group_by="platform"
)
```

### Prometheus метрики

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'deferlink'
    static_configs:
      - targets: ['localhost:9090']
```

Доступные метрики:

- `deferlink_sessions_total` - Общее количество сессий
- `deferlink_matches_total` - Количество успешных совпадений
- `deferlink_confidence_score` - Оценка уверенности
- `deferlink_response_time` - Время ответа

### Grafana dashboard

```json
{
  "dashboard": {
    "title": "DeferLink Analytics",
    "panels": [
      {
        "title": "Success Rate",
        "type": "stat",
        "targets": [
          {
            "expr": "rate(deferlink_matches_total[5m]) / rate(deferlink_sessions_total[5m]) * 100"
          }
        ]
      }
    ]
  }
}
```

---

## Безопасность

### Защита от мошенничества

1. **Rate limiting**: Ограничение количества запросов
2. **Fingerprint validation**: Проверка корректности отпечатков
3. **TTL ограничения**: Автоматическое истечение сессий
4. **IP блокировка**: Блокировка подозрительных IP

### Конфигурация безопасности

```python
# app/security.py
class SecurityConfig:
    # Rate limiting
    MAX_REQUESTS_PER_MINUTE = 60
    MAX_REQUESTS_PER_HOUR = 1000

    # Fraud detection
    SUSPICIOUS_ACTIVITY_THRESHOLD = 10
    AUTO_BAN_DURATION_MINUTES = 60

    # Validation
    MAX_FINGERPRINT_FIELDS = 20
    MIN_CONFIDENCE_SCORE = 0.3
```

### HTTPS и сертификаты

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Развертывание

### Локальная разработка

```bash
# Клонирование
git clone https://github.com/your-repo/deferlink.git
cd deferlink

# Настройка
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Запуск
python run.py
```

### Docker Compose

```yaml
version: '3.8'

services:
  deferlink:
    build: .
    ports:
      - "8000:8000"
    environment:
      - SECRET_KEY=your-production-secret
      - DATABASE_PATH=/data/deeplinks.db
      - LOG_LEVEL=INFO
    volumes:
      - ./data:/data
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - deferlink
    restart: unless-stopped
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: deferlink
spec:
  replicas: 3
  selector:
    matchLabels:
      app: deferlink
  template:
    metadata:
      labels:
        app: deferlink
    spec:
      containers:
      - name: deferlink
        image: deferlink:latest
        ports:
        - containerPort: 8000
        env:
        - name: SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: deferlink-secret
              key: secret-key
        - name: DATABASE_PATH
          value: "/data/deeplinks.db"
        volumeMounts:
        - name: data-volume
          mountPath: /data
      volumes:
      - name: data-volume
        persistentVolumeClaim:
          claimName: deferlink-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: deferlink-service
spec:
  selector:
    app: deferlink
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
```

### AWS/GCP/Azure

#### AWS (ECS + RDS)

```json
{
  "family": "deferlink",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "containerDefinitions": [
    {
      "name": "deferlink",
      "image": "your-account.dkr.ecr.region.amazonaws.com/deferlink:latest",
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "DATABASE_URL",
          "value": "postgresql://username:password@rds-endpoint:5432/deferlink"
        }
      ]
    }
  ]
}
```

---

## Устранение неполадок

### Частые проблемы

#### 1. Ошибка подключения к базе данных

**Проблема:** `sqlite3.OperationalError: unable to open database file`

**Решение:**

```bash
# Проверить права доступа
ls -la data/
chmod 755 data/
chmod 644 data/deeplinks.db

# Создать папку если отсутствует
mkdir -p data
```

#### 2. Конфигурационные ошибки

**Проблема:** `Configuration error: SECRET_KEY must be changed`

**Решение:**

```bash
# Установить переменную окружения
export SECRET_KEY="your-unique-secret-key"

# Или в .env файле
echo "SECRET_KEY=your-unique-secret-key" >> .env
```

#### 3. Порт уже используется

**Проблема:** `OSError: [Errno 48] Address already in use`

**Решение:**

```bash
# Найти процесс
lsof -i :8000

# Убить процесс
kill -9 <PID>

# Или изменить порт
export API_PORT=8001
```

#### 4. Низкая точность сопоставления

**Проблема:** Частые false negatives в сопоставлении

**Решение:**

```bash
# Увеличить максимальное расстояние
export MAX_FINGERPRINT_DISTANCE=3

# Или настроить веса алгоритма
export AUTO_OPTIMIZE_WEIGHTS=true
```

### Логи и отладка

```bash
# Включить подробные логи
export LOG_LEVEL=DEBUG

# Проверить логи
tail -f logs/deferlink.log

# Или в Docker
docker logs -f deferlink-container
```

#### 5. Проблемы с CORS

**Проблема:** `Access to fetch at 'http://localhost:8000' from origin 'http://localhost:3000' has been blocked by CORS policy`

**Решение:**

```bash
# Разрешить конкретные домены
export CORS_ORIGINS="http://localhost:3000,https://yoursite.com"

# Или временно разрешить все (только для разработки)
export CORS_ORIGINS="*"
```

#### 6. Превышение лимитов Rate Limiting

**Проблема:** `429 Too Many Requests`

**Решение:**

```bash
# Увеличить лимиты
export RATE_LIMIT_PER_MINUTE=120
export RATE_LIMIT_BURST=20

# Или отключить временно
export RATE_LIMIT_ENABLED=false
```

### Мониторинг производительности

```python
# app/monitoring.py
import time
import psutil
from typing import Dict, Any

class PerformanceMonitor:
    @staticmethod
    def get_system_stats() -> Dict[str, Any]:
        return {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_usage": psutil.disk_usage('/').percent,
            "timestamp": time.time()
        }

    @staticmethod
    def get_app_stats() -> Dict[str, Any]:
        # Статистика приложения
        from app.database import get_session_count, get_resolution_stats

        return {
            "active_sessions": get_session_count(active_only=True),
            "total_sessions": get_session_count(),
            "resolution_rate": get_resolution_stats()["success_rate"],
            "uptime": time.time() - app_start_time
        }
```

### Бэкап и восстановление

```bash
# Создание бэкапа базы данных
sqlite3 data/deeplinks.db ".backup data/backup_$(date +%Y%m%d_%H%M%S).db"

# Восстановление из бэкапа
sqlite3 data/deeplinks.db ".restore data/backup_20250603_194500.db"

# Автоматический бэкап (cron)
0 2 * * * cd /path/to/deferlink && sqlite3 data/deeplinks.db ".backup data/backup_$(date +\%Y\%m\%d).db"
```

---

## Масштабирование

### Горизонтальное масштабирование

#### Load Balancer конфигурация (Nginx)

```nginx
upstream deferlink_backend {
    server deferlink1:8000 weight=1;
    server deferlink2:8000 weight=1;
    server deferlink3:8000 weight=1;

    # Health check
    keepalive 32;
}

server {
    listen 80;
    server_name api.deferlink.com;

    location / {
        proxy_pass http://deferlink_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Sticky sessions для WebSocket
        ip_hash;
    }

    location /health {
        access_log off;
        proxy_pass http://deferlink_backend/health;
    }
}
```

#### Docker Swarm

```yaml
version: '3.8'

services:
  deferlink:
    image: deferlink:latest
    deploy:
      replicas: 5
      restart_policy:
        condition: on-failure
      placement:
        constraints:
          - node.role == worker
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/deferlink
    networks:
      - deferlink-network

  db:
    image: postgres:14
    environment:
      POSTGRES_DB: deferlink
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
    volumes:
      - db_data:/var/lib/postgresql/data
    deploy:
      placement:
        constraints:
          - node.role == manager
    networks:
      - deferlink-network

  redis:
    image: redis:7-alpine
    deploy:
      placement:
        constraints:
          - node.role == manager
    networks:
      - deferlink-network

networks:
  deferlink-network:
    driver: overlay

volumes:
  db_data:
```

### Вертикальное масштабирование

```bash
# Увеличение ресурсов контейнера
docker run -d \
  --name deferlink \
  --memory="2g" \
  --cpus="2.0" \
  -p 8000:8000 \
  deferlink:latest

# Kubernetes ресурсы
resources:
  requests:
    memory: "512Mi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "2000m"
```

### Кэширование

#### Redis интеграция

```python
# app/cache.py
import redis
import json
from typing import Optional, Any
from app.config import Config

class CacheManager:
    def __init__(self):
        self.redis_client = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            db=0,
            decode_responses=True
        )

    def set_session(self, session_id: str, data: dict, ttl: int = 3600):
        """Кэширование сессии"""
        self.redis_client.setex(
            f"session:{session_id}",
            ttl,
            json.dumps(data)
        )

    def get_session(self, session_id: str) -> Optional[dict]:
        """Получение сессии из кэша"""
        data = self.redis_client.get(f"session:{session_id}")
        return json.loads(data) if data else None

    def cache_fingerprint_match(self, fingerprint_hash: str, matches: list):
        """Кэширование результатов поиска"""
        self.redis_client.setex(
            f"fp_match:{fingerprint_hash}",
            300,  # 5 минут
            json.dumps(matches)
        )
```

---

## Тестирование

### Unit тесты

```python
# tests/test_fingerprint.py
import unittest
from app.fingerprint import FingerprintMatcher, calculate_distance

class TestFingerprintMatcher(unittest.TestCase):
    def setUp(self):
        self.matcher = FingerprintMatcher()

    def test_exact_match(self):
        fp1 = {
            "user_agent": "Mozilla/5.0...",
            "language": "en-US",
            "timezone": "America/New_York"
        }
        fp2 = fp1.copy()

        distance = calculate_distance(fp1, fp2)
        self.assertEqual(distance, 0)

    def test_partial_match(self):
        fp1 = {
            "user_agent": "Mozilla/5.0...",
            "language": "en-US",
            "timezone": "America/New_York",
            "screen_width": 1920
        }
        fp2 = {
            "user_agent": "Mozilla/5.0...",
            "language": "en-US",
            "timezone": "America/Los_Angeles",  # Отличается
            "screen_width": 1920
        }

        distance = calculate_distance(fp1, fp2)
        self.assertGreater(distance, 0)
        self.assertLess(distance, 2)

if __name__ == '__main__':
    unittest.main()
```

### Интеграционные тесты

```python
# tests/test_api.py
import pytest
import requests
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

class TestDeepLinkAPI:
    def test_create_session(self):
        """Тест создания сессии"""
        payload = {
            "url": "myapp://test",
            "fingerprint": {
                "user_agent": "test-agent",
                "platform": "web"
            }
        }

        response = client.post("/deeplink/create", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "session_id" in data

    def test_resolve_session(self):
        """Тест разрешения сессии"""
        # Сначала создаем сессию
        create_payload = {
            "url": "myapp://test",
            "fingerprint": {
                "user_agent": "test-agent",
                "language": "en-US",
                "platform": "web"
            }
        }

        create_response = client.post("/deeplink/create", json=create_payload)
        session_id = create_response.json()["session_id"]

        # Пытаемся разрешить
        resolve_payload = {
            "fingerprint": {
                "user_agent": "test-agent",
                "language": "en-US",
                "platform": "ios"  # Отличается, но близко
            }
        }

        response = client.post("/deeplink/resolve", json=resolve_payload)
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        # Может найти или не найти в зависимости от настроек
```

### Нагрузочное тестирование

```python
# tests/load_test.py
import asyncio
import aiohttp
import time
from concurrent.futures import ThreadPoolExecutor

async def create_session(session, url="myapp://test"):
    """Создание одной сессии"""
    payload = {
        "url": url,
        "fingerprint": {
            "user_agent": f"test-agent-{time.time()}",
            "platform": "web",
            "timestamp": time.time()
        }
    }

    async with session.post("http://localhost:8000/deeplink/create", json=payload) as resp:
        return await resp.json()

async def load_test(concurrent_requests=100, total_requests=1000):
    """Нагрузочный тест"""
    connector = aiohttp.TCPConnector(limit=200)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        start_time = time.time()

        # Создаем семафор для ограничения concurrent requests
        semaphore = asyncio.Semaphore(concurrent_requests)

        async def limited_request():
            async with semaphore:
                return await create_session(session)

        # Запускаем все запросы
        tasks = [limited_request() for _ in range(total_requests)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        end_time = time.time()

        # Анализ результатов
        successful = len([r for r in results if not isinstance(r, Exception)])
        failed = len([r for r in results if isinstance(r, Exception)])

        print(f"Total time: {end_time - start_time:.2f}s")
        print(f"Requests per second: {total_requests / (end_time - start_time):.2f}")
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")
        print(f"Success rate: {successful / total_requests * 100:.2f}%")

if __name__ == "__main__":
    asyncio.run(load_test(concurrent_requests=50, total_requests=500))
```

---

## Примеры реального использования

### E-commerce интеграция

```javascript
// Интеграция в интернет-магазин
class EcommerceDeepLink {
    constructor(apiUrl) {
        this.apiUrl = apiUrl;
    }

    async shareProduct(productId, userId = null) {
        const fingerprint = await this.collectFingerprint();

        const payload = {
            url: `mystore://product/${productId}`,
            promo_id: this.getCurrentPromo(),
            domain: window.location.hostname,
            fingerprint: fingerprint,
            custom_data: {
                product_id: productId,
                user_id: userId,
                utm_source: 'product_share',
                utm_campaign: 'mobile_app_install',
                referrer: document.referrer,
                page_url: window.location.href
            }
        };

        try {
            const response = await fetch(`${this.apiUrl}/deeplink/create`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (data.success) {
                // Показать модальное окно с выбором
                this.showAppDownloadModal(data.redirect_url, productId);
            }
        } catch (error) {
            console.error('DeepLink error:', error);
            // Fallback на обычную страницу продукта
            this.fallbackToWeb(productId);
        }
    }

    showAppDownloadModal(redirectUrl, productId) {
        const modal = document.createElement('div');
        modal.innerHTML = `
            <div class="deeplink-modal">
                <h3>Открыть в приложении?</h3>
                <p>Получите лучший опыт покупок в нашем мобильном приложении</p>
                <div class="modal-buttons">
                    <button onclick="window.location.href='${redirectUrl}'">
                        Скачать приложение
                    </button>
                    <button onclick="this.closest('.deeplink-modal').remove()">
                        Продолжить в браузере
                    </button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }

    async collectFingerprint() {
        return {
            user_agent: navigator.userAgent,
            language: navigator.language,
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
            screen_width: screen.width,
            screen_height: screen.height,
            platform: 'web',
            color_depth: screen.colorDepth,
            pixel_ratio: window.devicePixelRatio,
            cookies_enabled: navigator.cookieEnabled,
            local_storage: !!window.localStorage,
            session_storage: !!window.sessionStorage
        };
    }

    getCurrentPromo() {
        // Логика определения текущей промо-акции
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('promo') || 'default';
    }

    fallbackToWeb(productId) {
        // Показать веб-версию продукта
        window.location.href = `/product/${productId}`;
    }
}

// Использование
const deepLink = new EcommerceDeepLink('https://api.yourstore.com');

// На странице продукта
document.getElementById('share-app-btn').addEventListener('click', () => {
    const productId = document.querySelector('[data-product-id]').dataset.productId;
    const userId = getCurrentUserId(); // Ваша функция получения ID пользователя
    deepLink.shareProduct(productId, userId);
});
```

### Социальные сети

```javascript
// Интеграция для социальных постов
class SocialShareDeepLink {
    async sharePost(postId, authorId) {
        const shareData = {
            url: `mysocial://post/${postId}`,
            promo_id: 'social_share_2025',
            domain: 'mysocial.com',
            fingerprint: await this.collectFingerprint(),
            custom_data: {
                post_id: postId,
                author_id: authorId,
                share_source: 'web',
                content_type: 'post',
                engagement_context: this.getEngagementContext()
            }
        };

        const response = await fetch('/api/deeplink/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(shareData)
        });

        const result = await response.json();
        return result.redirect_url;
    }

    getEngagementContext() {
        return {
            time_on_page: this.getTimeOnPage(),
            scroll_depth: this.getScrollDepth(),
            previous_interactions: this.getPreviousInteractions()
        };
    }
}
```

### Медиа и контент

```swift
// iOS приложение для медиа-контента
class MediaDeepLinkHandler {
    func handleVideoShare(videoId: String, timestamp: TimeInterval = 0) {
        let deepLinkService = DeferLinkService.shared

        deepLinkService.resolveDeepLink { result in
            switch result {
            case .success(let response):
                if response.matched,
                   let customData = response.customData,
                   let videoId = customData["video_id"] as? String {

                    // Получить timestamp если есть
                    let startTime = customData["timestamp"] as? TimeInterval ?? 0

                    // Открыть видео с конкретного момента
                    self.openVideo(videoId: videoId, startTime: startTime)

                    // Отправить аналитику
                    self.trackDeepLinkSuccess(videoId: videoId, source: "deferred")
                } else {
                    // Показать главный экран
                    self.showMainScreen()
                }

            case .failure(let error):
                print("DeepLink resolution failed: \(error)")
                self.showMainScreen()
            }
        }
    }

    private func openVideo(videoId: String, startTime: TimeInterval) {
        DispatchQueue.main.async {
            let videoVC = VideoPlayerViewController()
            videoVC.videoId = videoId
            videoVC.startTime = startTime

            if let nav = UIApplication.shared.windows.first?.rootViewController as? UINavigationController {
                nav.pushViewController(videoVC, animated: true)
            }
        }
    }

    private func trackDeepLinkSuccess(videoId: String, source: String) {
        // Отправка аналитики в ваш сервис
        Analytics.track("deeplink_video_opened", properties: [
            "video_id": videoId,
            "source": source,
            "timestamp": Date().timeIntervalSince1970
        ])
    }
}
```

---

## Лучшие практики

### Оптимизация производительности

1. **Кэширование частых запросов**

```python
@lru_cache(maxsize=1000)
def calculate_fingerprint_hash(fingerprint_data: str) -> str:
    return hashlib.sha256(fingerprint_data.encode()).hexdigest()
```

2. **Batch обработка**

```python
async def process_multiple_resolutions(fingerprints: List[dict]) -> List[dict]:
    """Обработка нескольких запросов одновременно"""
    tasks = []
    for fp in fingerprints:
        task = resolve_single_fingerprint(fp)
        tasks.append(task)

    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

3. **Индексация базы данных**

```sql
-- Создание индексов для быстрого поиска
CREATE INDEX idx_sessions_fingerprint_hash ON sessions(fingerprint_hash);
CREATE INDEX idx_sessions_created_at ON sessions(created_at);
CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_sessions_expires_at ON sessions(expires_at);
```

### Безопасность

1. **Валидация входных данных**

```python
from pydantic import BaseModel, validator
from typing import Optional

class FingerprintData(BaseModel):
    user_agent: Optional[str] = None
    language: Optional[str] = None
    timezone: Optional[str] = None
    screen_width: Optional[int] = None
    screen_height: Optional[int] = None

    @validator('screen_width', 'screen_height')
    def validate_screen_dimensions(cls, v):
        if v is not None and (v <= 0 or v > 10000):
            raise ValueError('Invalid screen dimensions')
        return v

    @validator('user_agent')
    def validate_user_agent(cls, v):
        if v and len(v) > 1000:  # Защита от очень длинных UA
            raise ValueError('User agent too long')
        return v
```

2. **Rate limiting по IP**

```python
from collections import defaultdict
import time

class IPRateLimiter:
    def __init__(self, max_requests: int = 100, window_seconds: int = 3600):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)

    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds

        # Очистка старых запросов
        self.requests[ip] = [req_time for req_time in self.requests[ip] if req_time > window_start]

        # Проверка лимита
        if len(self.requests[ip]) >= self.max_requests:
            return False

        # Добавление нового запроса
        self.requests[ip].append(now)
        return True
```

### Мониторинг и алерты

```python
# app/monitoring.py
import logging
from typing import Dict, Any
from datetime import datetime, timedelta

class AlertManager:
    def __init__(self):
        self.logger = logging.getLogger('alerts')

    def check_system_health(self) -> Dict[str, Any]:
        """Проверка здоровья системы"""
        issues = []

        # Проверка успешности разрешения
        success_rate = self.get_success_rate_last_hour()
        if success_rate < 70:  # Меньше 70%
            issues.append({
                "type": "low_success_rate",
                "value": success_rate,
                "threshold": 70,
                "severity": "warning"
            })

        # Проверка производительности
        avg_response_time = self.get_avg_response_time()
        if avg_response_time > 2.0:  # Больше 2 секунд
            issues.append({
                "type": "slow_response",
                "value": avg_response_time,
                "threshold": 2.0,
                "severity": "warning"
            })

        # Проверка базы данных
        db_size = self.get_database_size()
        if db_size > 1000000:  # Больше 1M записей
            issues.append({
                "type": "large_database",
                "value": db_size,
                "threshold": 1000000,
                "severity": "info"
            })

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "issues": issues,
            "status": "healthy" if not issues else "warning"
        }

    def send_alert(self, issue: Dict[str, Any]):
        """Отправка алерта"""
        if issue["severity"] == "critical":
            # Отправить в PagerDuty/Slack
            self.send_critical_alert(issue)
        elif issue["severity"] == "warning":
            # Отправить в Slack
            self.send_warning_alert(issue)

        # Логирование
        self.logger.warning(f"Alert: {issue}")
```

### A/B тестирование

```python
# app/ab_testing.py
import random
from typing import Dict, Any
from enum import Enum

class ABTestVariant(Enum):
    CONTROL = "control"
    VARIANT_A = "variant_a"
    VARIANT_B = "variant_b"

class ABTestManager:
    def __init__(self):
        self.tests = {
            "fingerprint_algorithm": {
                "control": 0.33,
                "variant_a": 0.33,  # Новый алгоритм
                "variant_b": 0.34   # Улучшенные веса
            }
        }

    def get_variant(self, test_name: str, user_id: str = None) -> ABTestVariant:
        """Получение варианта для пользователя"""
        if test_name not in self.tests:
            return ABTestVariant.CONTROL

        # Детерминированное разделение на основе user_id
        if user_id:
            hash_value = hash(f"{test_name}:{user_id}")
            random.seed(hash_value)

        rand_value = random.random()
        cumulative = 0

        for variant, probability in self.tests[test_name].items():
            cumulative += probability
            if rand_value <= cumulative:
                return ABTestVariant(variant)

        return ABTestVariant.CONTROL

    def track_conversion(self, test_name: str, variant: ABTestVariant, success: bool):
        """Отслеживание конверсий"""
        # Отправка метрик в аналитику
        Analytics.track("ab_test_conversion", {
            "test_name": test_name,
            "variant": variant.value,
            "success": success,
            "timestamp": datetime.utcnow().isoformat()
        })
```

---

## 📚 Ресурсы и ссылки

### Официальная документация

- **FastAPI**: <https://fastapi.tiangolo.com/>
- **SQLAlchemy**: <https://docs.sqlalchemy.org/>
- **Pydantic**: <https://pydantic-docs.helpmanual.io/>
- **Uvicorn**: <https://www.uvicorn.org/>

### Дополнительные ресурсы

- **Branch.io** - Коммерческое решение для deep linking
- **AppsFlyer** - Атрибуция и deep linking
- **Adjust** - Мобильная аналитика и deep linking

###

- **Email**: <tdk@null.net>

---

## 📄 Лицензия

```
MIT License

Copyright (c) 2025 DeferLink Project

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 📝 Changelog

### v1.0.0 (2025-06-03)

- ✅ Первый релиз DeferLink
- ✅ Базовый API для создания и разрешения диплинков
- ✅ Fingerprinting алгоритм
- ✅ iOS тестовое приложение
- ✅ Аналитика и мониторинг
- ✅ Docker поддержка

### Планы на будущее

- 🔄 Android SDK
- 🔄 PostgreSQL поддержка
- 🔄 Машинное обучение для улучшения точности
- 🔄 WebSocket для реального времени
- 🔄 GraphQL API
- 🔄 Kubernetes Helm charts
- 🔄 Advanced fraud detection

---

*Эта документация охватывает все аспекты работы с DeferLink. Для получения дополнительной помощи обращайтесь к разделу [Устранение неполадок](#устранение-неполадок) или создайте issue в GitHub репозитории.*
