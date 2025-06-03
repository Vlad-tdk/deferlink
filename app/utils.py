"""
Utility functions for DeferLink system
Утилиты для системы DeferLink
"""

import hashlib
import re
from datetime import datetime
from typing import Dict, Optional, Any
from fastapi import Request


def detect_mobile_browser(user_agent: str) -> bool:
    """Определение мобильного браузера"""
    if not user_agent:
        return False

    mobile_patterns = [
        'iPhone', 'iPad', 'Android', 'Mobile', 'webOS', 'BlackBerry',
        'Windows Phone', 'Opera Mini', 'IEMobile', 'Kindle'
    ]
    return any(pattern.lower() in user_agent.lower() for pattern in mobile_patterns)


def detect_ios_device(user_agent: str) -> bool:
    """Определение iOS устройства"""
    if not user_agent:
        return False

    return any(device in user_agent for device in ['iPhone', 'iPad', 'iPod'])


def detect_android_device(user_agent: str) -> bool:
    """Определение Android устройства"""
    if not user_agent:
        return False

    return 'Android' in user_agent


def extract_ios_version(user_agent: str) -> str:
    """Извлечение версии iOS из User-Agent"""
    if not user_agent:
        return ""

    # Паттерн для поиска версии iOS: "OS 15_4" или "OS 15.4"
    pattern = r'OS (\d+)[_.](\d+)(?:[_.](\d+))?'
    match = re.search(pattern, user_agent)

    if match:
        major = match.group(1)
        minor = match.group(2)
        patch = match.group(3) if match.group(3) else "0"
        return f"{major}.{minor}.{patch}"

    return ""


def extract_device_model(user_agent: str) -> str:
    """Извлечение модели устройства из User-Agent"""
    if not user_agent:
        return ""

    # Для iOS
    if 'iPhone' in user_agent:
        return 'iPhone'
    elif 'iPad' in user_agent:
        return 'iPad'
    elif 'iPod' in user_agent:
        return 'iPod'

    # Для Android
    android_match = re.search(r'Android.*?;\s*([^)]+)', user_agent)
    if android_match:
        return android_match.group(1).strip()

    return ""


def sanitize_user_agent(user_agent: str, max_length: int = 200) -> str:
    """Очистка и ограничение длины User-Agent"""
    if not user_agent:
        return ""

    # Удаление потенциально чувствительных данных
    sanitized = re.sub(r'Version/[\d.]+', 'Version/X.X', user_agent)
    sanitized = re.sub(r'Safari/[\d.]+', 'Safari/X.X', sanitized)

    # Ограничение длины
    return sanitized[:max_length] if len(sanitized) > max_length else sanitized


def hash_fingerprint(fingerprint_data: Dict[str, Any]) -> str:
    """Создание хеша fingerprint для быстрого поиска"""
    # Создаем строку из ключевых компонентов
    components = [
        str(fingerprint_data.get('model') or ''),
        str(fingerprint_data.get('language') or ''),
        str(fingerprint_data.get('timezone') or ''),
        str(fingerprint_data.get('screen_size') or '')
    ]

    fingerprint_string = '|'.join(components).lower()
    return hashlib.sha256(fingerprint_string.encode()).hexdigest()[:16]


def validate_promo_id(promo_id: str) -> bool:
    """Валидация ID промо-акции"""
    if not promo_id:
        return False

    # Длина от 1 до 100 символов
    if len(promo_id) > 100:
        return False

    # Разрешенные символы: буквы, цифры, подчеркивания, дефисы
    pattern = r'^[a-zA-Z0-9_-]+$'
    return bool(re.match(pattern, promo_id))


def validate_domain(domain: str) -> bool:
    """Валидация домена"""
    if not domain:
        return False

    # Простая валидация домена
    pattern = r'^[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9]?\.([a-zA-Z]{2,}\.?)+$'
    return bool(re.match(pattern, domain)) and len(domain) <= 253


def validate_session_id(session_id: str) -> bool:
    """Валидация ID сессии (UUID4 формат)"""
    if not session_id:
        return False

    # UUID4 паттерн
    pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
    return bool(re.match(pattern, session_id.lower()))


def generate_app_store_url(app_id: Optional[str] = None, domain: Optional[str] = None) -> str:
    """Генерация URL для App Store"""
    if app_id and app_id.isdigit():
        return f"https://apps.apple.com/app/id{app_id}"
    elif domain:
        # Можно добавить логику поиска app_id по домену
        return "https://apps.apple.com"
    else:
        return "https://apps.apple.com"


def generate_google_play_url(package_name: Optional[str] = None) -> str:
    """Генерация URL для Google Play"""
    if package_name:
        return f"https://play.google.com/store/apps/details?id={package_name}"
    else:
        return "https://play.google.com/store"


def format_user_agent_for_storage(user_agent: str) -> str:
    """Форматирование User-Agent для хранения"""
    if not user_agent:
        return ""

    # Удаление избыточных пробелов
    formatted = ' '.join(user_agent.split())

    # Ограничение длины
    max_length = 500
    if len(formatted) > max_length:
        formatted = formatted[:max_length] + "..."

    return formatted


def parse_screen_size(screen_size: str) -> Dict[str, int]:
    """Парсинг размера экрана"""
    if not screen_size:
        return {"width": 0, "height": 0}

    # Паттерн: "390x844" или "390*844"
    pattern = r'(\d+)[x*](\d+)'
    match = re.match(pattern, screen_size)

    if match:
        return {
            "width": int(match.group(1)),
            "height": int(match.group(2))
        }

    return {"width": 0, "height": 0}


def normalize_language_code(language: str) -> str:
    """Нормализация кода языка"""
    if not language:
        return ""

    # Приведение к стандартному формату: en_US, ru_RU
    language = language.replace('-', '_')

    # Если только код языка (en) - добавляем регион
    if len(language) == 2:
        language_mappings = {
            'en': 'en_US',
            'ru': 'ru_RU',
            'de': 'de_DE',
            'fr': 'fr_FR',
            'es': 'es_ES',
            'it': 'it_IT',
            'ja': 'ja_JP',
            'zh': 'zh_CN',
            'ko': 'ko_KR'
        }
        return language_mappings.get(language.lower(), language)

    return language


def calculate_session_lifetime_hours(created_at: str, resolved_at: Optional[str] = None) -> float:
    """Вычисление времени жизни сессии в часах"""
    try:
        created = datetime.fromisoformat(created_at.replace('Z', '+00:00'))

        if resolved_at:
            resolved = datetime.fromisoformat(resolved_at.replace('Z', '+00:00'))
            delta = resolved - created
        else:
            delta = datetime.now() - created

        return delta.total_seconds() / 3600  # Часы

    except Exception:
        return 0.0


def generate_instruction_page(domain: str, promo_id: str) -> str:
    """Генерация HTML страницы с инструкциями"""
    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Установите приложение</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                text-align: center;
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
            }}
            .container {{
                background: rgba(255, 255, 255, 0.1);
                padding: 40px;
                border-radius: 20px;
                backdrop-filter: blur(10px);
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
                max-width: 400px;
                width: 100%;
            }}
            h1 {{
                margin-bottom: 20px;
                font-size: 28px;
            }}
            p {{
                margin-bottom: 30px;
                font-size: 18px;
                line-height: 1.6;
            }}
            .btn {{
                display: inline-block;
                padding: 15px 30px;
                background: #fff;
                color: #667eea;
                text-decoration: none;
                border-radius: 25px;
                font-weight: bold;
                font-size: 16px;
                transition: transform 0.2s;
            }}
            .btn:hover {{
                transform: translateY(-2px);
            }}
            .promo {{
                background: rgba(255, 255, 255, 0.2);
                padding: 15px 20px;
                border-radius: 15px;
                margin-top: 20px;
                font-size: 14px;
            }}
            .instructions {{
                background: rgba(255, 255, 255, 0.1);
                padding: 20px;
                border-radius: 15px;
                margin-top: 20px;
                font-size: 14px;
                text-align: left;
            }}
            .step {{
                margin-bottom: 10px;
                display: flex;
                align-items: center;
            }}
            .step-number {{
                background: #fff;
                color: #667eea;
                width: 24px;
                height: 24px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
                margin-right: 10px;
                font-size: 12px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📱 Установите приложение</h1>
            <p>Для продолжения вам необходимо установить наше мобильное приложение.</p>

            <a href="{generate_app_store_url(domain=domain)}" class="btn">Скачать из App Store</a>

            <div class="instructions">
                <strong>Что делать дальше:</strong>
                <div class="step">
                    <div class="step-number">1</div>
                    <div>Установите приложение</div>
                </div>
                <div class="step">
                    <div class="step-number">2</div>
                    <div>Откройте приложение</div>
                </div>
                <div class="step">
                    <div class="step-number">3</div>
                    <div>Ваш промо-код активируется автоматически</div>
                </div>
            </div>

            <div class="promo">
                <strong>Промо-код:</strong> {promo_id}<br>
                <strong>Домен:</strong> {domain}
            </div>
        </div>
    </body>
    </html>
    """


def get_client_ip(request: Request) -> str:
    """Получение IP адреса клиента"""
    # Проверка заголовков прокси
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fallback к клиентскому IP
    if request.client and request.client.host:
        return request.client.host

    return "unknown"


def mask_sensitive_data(data: str, mask_char: str = "*", visible_chars: int = 4) -> str:
    """Маскировка чувствительных данных"""
    if not data or len(data) <= visible_chars:
        return data

    return data[:visible_chars] + mask_char * (len(data) - visible_chars)