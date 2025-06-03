# DeferLink - Complete Documentation

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Installation and Setup](#installation-and-setup)
4. [API Documentation](#api-documentation)
5. [Configuration](#configuration)
6. [iOS/Android SDK](#iosandroid-sdk)
7. [Usage Examples](#usage-examples)
8. [Monitoring and Analytics](#monitoring-and-analytics)
9. [Security](#security)
10. [Deployment](#deployment)
11. [Troubleshooting](#troubleshooting)

---

## System Overview

**DeferLink** is an intelligent deferred deep linking system for mobile applications that preserves user context between web browsers and mobile apps.

### Key Features

- **Deferred Deep Links**: Context preservation for users without installed apps
- **Smart Matching**: Fingerprinting algorithm for device linking
- **Cross-Platform**: iOS and Android support
- **Analytics**: Detailed statistics and monitoring
- **Security**: Fraud protection and abuse prevention
- **Scalability**: Ready for high loads

### How It Works

1. **Session Creation**: User clicks a link in browser
2. **Fingerprint Collection**: System gathers device data
3. **Redirect**: User is redirected to App Store/Play Store
4. **Matching**: After installation, app searches for matching session
5. **Context Restoration**: App receives original data

---

## Architecture

### System Components

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

### Project Structure

```tree
deferlink/
├── app/                    # Main application
│   ├── __init__.py
│   ├── main.py            # FastAPI application
│   ├── config.py          # Configuration
│   ├── database.py        # Database
│   ├── models.py          # Pydantic models
│   ├── deeplink_handler.py # Core logic
│   ├── fingerprint.py     # Fingerprinting
│   ├── analytics.py       # Analytics
│   └── security.py        # Security
├── ios_app/               # iOS test application
│   ├── Views/
│   ├── Services/
│   ├── Models/
│   └── Utils/
├── data/                  # Database
├── tests/                 # Tests
├── requirements.txt       # Dependencies
├── run.py                # Entry point
└── README.md
```

---

## Installation and Setup

### System Requirements

- Python 3.8+
- SQLite 3.x
- 512MB RAM minimum
- 1GB free space

### Installation

1. **Clone Repository**

```bash
git clone https://github.com/your-repo/deferlink.git
cd deferlink
```

2. **Create Virtual Environment**

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows
```

3. **Install Dependencies**

```bash
pip install -r requirements.txt
```

4. **Configure Settings**

```bash
cp .env.example .env
# Edit .env file
```

5. **Run**

```bash
python run.py
```

### Docker (Optional)

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

## API Documentation

### Base URL

```
http://localhost:8000
```

### Authentication

API uses session-based authentication with cookies.

---

### Endpoints

#### 1. Health Check

**GET** `/health`

Service health check.

**Response:**

```json
{
  "status": "healthy",
  "timestamp": "2025-06-03T19:43:03.774Z",
  "version": "1.0.0"
}
```

---

#### 2. Create Deep Link Session

**POST** `/deeplink/create`

Creates a new deferred deep link session.

**Request Body:**

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

**Response:**

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": true,
  "expires_at": "2025-06-05T19:43:03.774Z",
  "redirect_url": "https://apps.apple.com/app/myapp"
}
```

**Error Codes:**

- `400` - Invalid data
- `429` - Rate limit exceeded
- `500` - Internal server error

---

#### 3. Resolve Deep Link

**POST** `/deeplink/resolve`

Find matching session for mobile application.

**Request Body:**

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

**Response (Match Found):**

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

**Response (No Match):**

```json
{
  "success": true,
  "matched": false,
  "message": "No matching session found",
  "confidence_score": 0.0
}
```

---

#### 4. Get Statistics

**GET** `/stats`

Get general system statistics.

**Response:**

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

#### 5. Detailed Statistics

**GET** `/stats/detailed`

Extended statistics with time breakdown.

**Query Parameters:**

- `period` - period (hour, day, week, month)
- `from_date` - start date (ISO 8601)
- `to_date` - end date (ISO 8601)

**Example:**

```
GET /stats/detailed?period=day&from_date=2025-06-01T00:00:00Z&to_date=2025-06-03T23:59:59Z
```

**Response:**

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

#### 6. Get Session

**GET** `/session/{session_id}`

Get information about specific session.

**Response:**

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

#### 7. Delete Session

**DELETE** `/session/{session_id}`

Delete session (testing only).

**Response:**

```json
{
  "success": true,
  "message": "Session deleted successfully"
}
```

---

#### 8. Bulk Operations

**POST** `/sessions/cleanup`

Clean up expired sessions.

**Response:**

```json
{
  "deleted_count": 150,
  "success": true
}
```

---

### Error Codes

| Code | Description | Example |
|------|-------------|---------|
| 400 | Bad Request | Missing required fields |
| 401 | Unauthorized | Missing or invalid token |
| 404 | Not Found | Session doesn't exist |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Error | Database error |

**Error Format:**

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

## Configuration

### Environment Variables (.env)

```bash
# Security
SECRET_KEY=your-super-secret-key-change-this-in-production
COOKIE_SECURE=false  # true for HTTPS
COOKIE_HTTPONLY=true
COOKIE_SAMESITE=lax

# Database
DATABASE_PATH=data/deeplinks.db

# API
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=1

# Deep Link Settings
DEFAULT_TTL_HOURS=48           # Session lifetime
MAX_FINGERPRINT_DISTANCE=2    # Maximum matching distance
CLEANUP_INTERVAL_MINUTES=30   # Cleanup interval

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_BURST=10

# CORS
CORS_ORIGINS=*  # Specify specific domains in production

# Monitoring
ENABLE_METRICS=false
METRICS_PORT=9090
LOG_LEVEL=INFO

# Analytics
ENABLE_ANALYTICS=true
ANALYTICS_RETENTION_DAYS=90

# Security
MAX_CONTENT_LENGTH=1048576  # 1MB
REQUEST_TIMEOUT=30

# Fraud Detection
FRAUD_DETECTION_ENABLED=false
FRAUD_RISK_THRESHOLD=0.8

# Algorithm Optimization
AUTO_OPTIMIZE_WEIGHTS=false
```

### Production Configuration

```bash
# Production settings
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

#### Installation

1. Add files from `ios_app/` folder to your project
2. Configure dependencies in `Package.swift` or manually

#### Usage

```swift
import DeferLinkSDK

class AppDelegate: UIResponder, UIApplicationDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {

        // Initialize DeferLink
        DeferLinkService.configure(
            baseURL: "https://your-deferlink-server.com",
            timeout: 30.0
        )

        // Attempt deep link resolution
        DeferLinkService.shared.resolveDeepLink { result in
            DispatchQueue.main.async {
                switch result {
                case .success(let response):
                    if response.matched {
                        // Handle deep link
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
        // Your deep link handling logic
        guard let url = url else { return }

        if url.contains("product") {
            // Open product page
        } else if url.contains("promo") {
            // Show promo
        }
    }
}
```

#### Service Configuration

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

#### Fingerprint Collection

```swift
// Automatic fingerprint collection
let fingerprint = FingerprintCollector.collectFingerprint()

// Manual collection
var fingerprint = FingerprintData()
fingerprint.model = UIDevice.current.model
fingerprint.systemName = UIDevice.current.systemName
fingerprint.systemVersion = UIDevice.current.systemVersion
// ... other parameters
```

### Android SDK (Concept)

```kotlin
class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Initialize DeferLink
        DeferLink.configure("https://your-deferlink-server.com")

        // Resolve deep link
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
        // Handle deep link
    }
}
```

---

## Usage Examples

### Web Integration

```html
<!DOCTYPE html>
<html>
<head>
    <title>Smart Link Example</title>
</head>
<body>
    <button onclick="createDeferLink()">Open in App</button>

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
                // Redirect to App Store/Play Store
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

### React Integration

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
            Open in App
        </button>
    );
};

export default DeferLinkButton;
```

---

## Monitoring and Analytics

### Built-in Analytics

```python
# Get metrics
from app.analytics import AnalyticsCollector

analytics = AnalyticsCollector()

# Basic metrics
stats = analytics.get_basic_stats()
print(f"Success rate: {stats['success_rate']:.2f}%")

# Detailed analytics
detailed = analytics.get_detailed_stats(
    from_date="2025-06-01",
    to_date="2025-06-03",
    group_by="platform"
)
```

### Prometheus Metrics

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'deferlink'
    static_configs:
      - targets: ['localhost:9090']
```

Available metrics:

- `deferlink_sessions_total` - Total number of sessions
- `deferlink_matches_total` - Number of successful matches
- `deferlink_confidence_score` - Confidence score
- `deferlink_response_time` - Response time

### Grafana Dashboard

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

## Security

### Fraud Protection

1. **Rate limiting**: Request quantity limits
2. **Fingerprint validation**: Fingerprint correctness checks
3. **TTL limits**: Automatic session expiration
4. **IP blocking**: Suspicious IP blocking

### Security Configuration

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

### HTTPS and Certificates

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

## Deployment

### Local Development

```bash
# Clone
git clone https://github.com/your-repo/deferlink.git
cd deferlink

# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run
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

## Troubleshooting

### Common Issues

#### 1. Database Connection Error

**Problem:** `sqlite3.OperationalError: unable to open database file`

**Solution:**

```bash
# Check permissions
ls -la data/
chmod 755 data/
chmod 644 data/deeplinks.db

# Create folder if missing
mkdir -p data
```

#### 2. Configuration Errors

**Problem:** `Configuration error: SECRET_KEY must be changed`

**Solution:**

```bash
# Set environment variable
export SECRET_KEY="your-unique-secret-key"

# Or in .env file
echo "SECRET_KEY=your-unique-secret-key" >> .env
```

#### 3. Port Already in Use

**Problem:** `OSError: [Errno 48] Address already in use`

**Solution:**

```bash
# Find process
lsof -i :8000

# Kill process
kill -9 <PID>

# Or change port
export API_PORT=8001
```

#### 4. Low Matching Accuracy

**Problem:** Frequent false negatives in matching

**Solution:**

```bash
# Increase maximum distance
export MAX_FINGERPRINT_DISTANCE=3

# Or configure algorithm weights
export AUTO_OPTIMIZE_WEIGHTS=true
```

### Logs and Debugging

```bash
# Enable verbose logs
export LOG_LEVEL=DEBUG

# Check logs
tail -f logs/deferlink.log

# Or in Docker
docker logs -f deferlink-container
```

#### 5. CORS Issues

**Problem:** `Access to fetch at 'http://localhost:8000' from origin 'http://localhost:3000' has been blocked by CORS policy`

**Solution:**

```bash
# Allow specific domains
export CORS_ORIGINS="http://localhost:3000,https://yoursite.com"

# Or temporarily allow all (development only)
export CORS_ORIGINS="*"
```

#### 6. Rate Limiting Exceeded

**Problem:** `429 Too Many Requests`

**Solution:**

```bash
# Increase limits
export RATE_LIMIT_PER_MINUTE=120
export RATE_LIMIT_BURST=20

# Or disable temporarily
export RATE_LIMIT_ENABLED=false
```

### Performance Monitoring

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
        # Application statistics
        from app.database import get_session_count, get_resolution_stats

        return {
            "active_sessions": get_session_count(active_only=True),
            "total_sessions": get_session_count(),
            "resolution_rate": get_resolution_stats()["success_rate"],
            "uptime": time.time() - app_start_time
        }
```

### Backup and Recovery

```bash
# Create database backup
sqlite3 data/deeplinks.db ".backup data/backup_$(date +%Y%m%d_%H%M%S).db"

# Restore from backup
sqlite3 data/deeplinks.db ".restore data/backup_20250603_194500.db"

# Automatic backup (cron)
0 2 * * * cd /path/to/deferlink && sqlite3 data/deeplinks.db ".backup data/backup_$(date +\%Y\%m\%d).db"
```

---

## Scaling

### Horizontal Scaling

#### Load Balancer Configuration (Nginx)

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

        # Sticky sessions for WebSocket
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

### Vertical Scaling

```bash
# Increase container resources
docker run -d \
  --name deferlink \
  --memory="2g" \
  --cpus="2.0" \
  -p 8000:8000 \
  deferlink:latest

# Kubernetes resources
resources:
  requests:
    memory: "512Mi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "2000m"
```

### Caching

#### Redis Integration

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
        """Cache session"""
        self.redis_client.setex(
            f"session:{session_id}",
            ttl,
            json.dumps(data)
        )

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session from cache"""
        data = self.redis_client.get(f"session:{session_id}")
        return json.loads(data) if data else None

    def cache_fingerprint_match(self, fingerprint_hash: str, matches: list):
        """Cache search results"""
        self.redis_client.setex(
            f"fp_match:{fingerprint_hash}",
            300,  # 5 minutes
            json.dumps(matches)
        )
```

---

## Testing

### Unit Tests

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
            "timezone": "America/Los_Angeles",  # Different
            "screen_width": 1920
        }

        distance = calculate_distance(fp1, fp2)
        self.assertGreater(distance, 0)
        self.assertLess(distance, 2)

if __name__ == '__main__':
    unittest.main()
```

### Integration Tests

```python
# tests/test_api.py
import pytest
import requests
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

class TestDeepLinkAPI:
    def test_create_session(self):
        """Test session creation"""
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
        """Test session resolution"""
        # First create session
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

        # Try to resolve
        resolve_payload = {
            "fingerprint": {
                "user_agent": "test-agent",
                "language": "en-US",
                "platform": "ios"  # Different but close
            }
        }

        response = client.post("/deeplink/resolve", json=resolve_payload)
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        # May or may not find depending on settings
```

### Load Testing

```python
# tests/load_test.py
import asyncio
import aiohttp
import time
from concurrent.futures import ThreadPoolExecutor

async def create_session(session, url="myapp://test"):
    """Create single session"""
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
    """Load test"""
    connector = aiohttp.TCPConnector(limit=200)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        start_time = time.time()

        # Create semaphore for limiting concurrent requests
        semaphore = asyncio.Semaphore(concurrent_requests)

        async def limited_request():
            async with semaphore:
                return await create_session(session)

        # Run all requests
        tasks = [limited_request() for _ in range(total_requests)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        end_time = time.time()

        # Analyze results
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

## Real-World Usage Examples

### E-commerce Integration

```javascript
// E-commerce store integration
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
                // Show modal with choice
                this.showAppDownloadModal(data.redirect_url, productId);
            }
        } catch (error) {
            console.error('DeepLink error:', error);
            // Fallback to regular product page
            this.fallbackToWeb(productId);
        }
    }

    showAppDownloadModal(redirectUrl, productId) {
        const modal = document.createElement('div');
        modal.innerHTML = `
            <div class="deeplink-modal">
                <h3>Open in App?</h3>
                <p>Get the best shopping experience in our mobile app</p>
                <div class="modal-buttons">
                    <button onclick="window.location.href='${redirectUrl}'">
                        Download App
                    </button>
                    <button onclick="this.closest('.deeplink-modal').remove()">
                        Continue in Browser
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
        // Logic to determine current promotion
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('promo') || 'default';
    }

    fallbackToWeb(productId) {
        // Show web version of product
        window.location.href = `/product/${productId}`;
    }
}

// Usage
const deepLink = new EcommerceDeepLink('https://api.yourstore.com');

// On product page
document.getElementById('share-app-btn').addEventListener('click', () => {
    const productId = document.querySelector('[data-product-id]').dataset.productId;
    const userId = getCurrentUserId(); // Your function to get user ID
    deepLink.shareProduct(productId, userId);
});
```

### Social Media

```javascript
// Social media posts integration
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

### Media and Content

```swift
// iOS app for media content
class MediaDeepLinkHandler {
    func handleVideoShare(videoId: String, timestamp: TimeInterval = 0) {
        let deepLinkService = DeferLinkService.shared

        deepLinkService.resolveDeepLink { result in
            switch result {
            case .success(let response):
                if response.matched,
                   let customData = response.customData,
                   let videoId = customData["video_id"] as? String {

                    // Get timestamp if available
                    let startTime = customData["timestamp"] as? TimeInterval ?? 0

                    // Open video at specific time
                    self.openVideo(videoId: videoId, startTime: startTime)

                    // Send analytics
                    self.trackDeepLinkSuccess(videoId: videoId, source: "deferred")
                } else {
                    // Show main screen
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
        // Send analytics to your service
        Analytics.track("deeplink_video_opened", properties: [
            "video_id": videoId,
            "source": source,
            "timestamp": Date().timeIntervalSince1970
        ])
    }
}
```

---

## Best Practices

### Performance Optimization

1. **Cache frequent requests**

```python
@lru_cache(maxsize=1000)
def calculate_fingerprint_hash(fingerprint_data: str) -> str:
    return hashlib.sha256(fingerprint_data.encode()).hexdigest()
```

2. **Batch processing**

```python
async def process_multiple_resolutions(fingerprints: List[dict]) -> List[dict]:
    """Process multiple requests simultaneously"""
    tasks = []
    for fp in fingerprints:
        task = resolve_single_fingerprint(fp)
        tasks.append(task)

    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

3. **Database indexing**

```sql
-- Create indexes for fast searches
CREATE INDEX idx_sessions_fingerprint_hash ON sessions(fingerprint_hash);
CREATE INDEX idx_sessions_created_at ON sessions(created_at);
CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_sessions_expires_at ON sessions(expires_at);
```

### Security

1. **Input data validation**

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
        if v and len(v) > 1000:  # Protection from very long UAs
            raise ValueError('User agent too long')
        return v
```

2. **Rate limiting by IP**

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

        # Clean old requests
        self.requests[ip] = [req_time for req_time in self.requests[ip] if req_time > window_start]

        # Check limit
        if len(self.requests[ip]) >= self.max_requests:
            return False

        # Add new request
        self.requests[ip].append(now)
        return True
```

### Monitoring and Alerts

```python
# app/monitoring.py
import logging
from typing import Dict, Any
from datetime import datetime, timedelta

class AlertManager:
    def __init__(self):
        self.logger = logging.getLogger('alerts')

    def check_system_health(self) -> Dict[str, Any]:
        """Check system health"""
        issues = []

        # Check resolution success rate
        success_rate = self.get_success_rate_last_hour()
        if success_rate < 70:  # Less than 70%
            issues.append({
                "type": "low_success_rate",
                "value": success_rate,
                "threshold": 70,
                "severity": "warning"
            })

        # Check performance
        avg_response_time = self.get_avg_response_time()
        if avg_response_time > 2.0:  # More than 2 seconds
            issues.append({
                "type": "slow_response",
                "value": avg_response_time,
                "threshold": 2.0,
                "severity": "warning"
            })

        # Check database
        db_size = self.get_database_size()
        if db_size > 1000000:  # More than 1M records
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
        """Send alert"""
        if issue["severity"] == "critical":
            # Send to PagerDuty/Slack
            self.send_critical_alert(issue)
        elif issue["severity"] == "warning":
            # Send to Slack
            self.send_warning_alert(issue)

        # Logging
        self.logger.warning(f"Alert: {issue}")
```

### A/B Testing

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
                "variant_a": 0.33,  # New algorithm
                "variant_b": 0.34   # Improved weights
            }
        }

    def get_variant(self, test_name: str, user_id: str = None) -> ABTestVariant:
        """Get variant for user"""
        if test_name not in self.tests:
            return ABTestVariant.CONTROL

        # Deterministic splitting based on user_id
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
        """Track conversions"""
        # Send metrics to analytics
        Analytics.track("ab_test_conversion", {
            "test_name": test_name,
            "variant": variant.value,
            "success": success,
            "timestamp": datetime.utcnow().isoformat()
        })
```

---

## 📚 Resources and Links

### Official Documentation

- **FastAPI**: <https://fastapi.tiangolo.com/>
- **SQLAlchemy**: <https://docs.sqlalchemy.org/>
- **Pydantic**: <https://pydantic-docs.helpmanual.io/>
- **Uvicorn**: <https://www.uvicorn.org/>

### Additional Resources

- **Branch.io** - Commercial deep linking solution
- **AppsFlyer** - Attribution and deep linking
- **Adjust** - Mobile analytics and deep linking

### Contact

- **Email**: <tdk@null.net>

---

## 📄 License

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

- ✅ First DeferLink release
- ✅ Basic API for creating and resolving deep links
- ✅ Fingerprinting algorithm
- ✅ iOS test application
- ✅ Analytics and monitoring
- ✅ Docker support

### Future Plans

- 🔄 Android SDK
- 🔄 PostgreSQL support
- 🔄 Machine learning for improved accuracy
- 🔄 WebSocket for real-time
- 🔄 GraphQL API
- 🔄 Kubernetes Helm charts
- 🔄 Advanced fraud detection

---

*This documentation covers all aspects of working with DeferLink. For additional help, refer to the [Troubleshooting](#troubleshooting) section or create an issue in the GitHub repository.*
