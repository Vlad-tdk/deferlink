"""
Pydantic models for DeferLink system
Pydantic модели для системы DeferLink
"""

from datetime import datetime
from typing import Dict, Optional, Any
from pydantic import BaseModel, Field, validator


class FingerprintData(BaseModel):
    """Данные fingerprint устройства"""
    device_model: Optional[str] = Field(None, description="Модель устройства", alias="model")
    language: Optional[str] = Field(None, description="Язык системы")
    timezone: Optional[str] = Field(None, description="Часовой пояс")
    user_agent: Optional[str] = Field(None, description="User Agent")
    screen_width: Optional[int] = Field(None, description="Ширина экрана")
    screen_height: Optional[int] = Field(None, description="Высота экрана")
    screen_size: Optional[str] = Field(None, description="Размер экрана (строка)")
    platform: Optional[str] = Field(None, description="Платформа")
    app_version: Optional[str] = Field(None, description="Версия приложения")
    idfv: Optional[str] = Field(None, description="Identifier for Vendor (iOS)")

    @validator("screen_size", pre=True, always=True)
    def set_screen_size(cls, v, values):
        """Автоматическое формирование screen_size из width/height"""
        if v:
            return v
        width = values.get("screen_width")
        height = values.get("screen_height")
        if width and height:
            return f"{width}x{height}"
        return None

    @validator("language")
    def validate_language(cls, v):
        """Валидация формата языка"""
        if v and len(v) > 10:
            raise ValueError("Language code too long")
        return v

    @validator("timezone")
    def validate_timezone(cls, v):
        """Валидация часового пояса"""
        if v and len(v) > 50:
            raise ValueError("Timezone string too long")
        return v

    class Config:
        allow_population_by_field_name = True
        json_schema_extra = {
            "example": {
                "model": "iPhone14,2",
                "language": "ru_RU",
                "timezone": "Europe/Moscow",
                "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
                "screen_width": 390,
                "screen_height": 844,
                "idfv": "12345678-1234-1234-1234-123456789ABC"
            }
        }


class ResolveRequest(BaseModel):
    """Запрос на разрешение диплинка"""
    fingerprint: FingerprintData = Field(..., description="Fingerprint устройства")
    app_scheme: Optional[str] = Field(None, description="Схема приложения")
    fallback_url: Optional[str] = Field(None, description="URL для fallback")

    class Config:
        json_schema_extra = {
            "example": {
                "fingerprint": {
                    "model": "iPhone14,2",
                    "language": "ru_RU",
                    "timezone": "Europe/Moscow",
                    "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
                    "screen_width": 390,
                    "screen_height": 844
                },
                "app_scheme": "myapp://promo/summer2024",
                "fallback_url": "https://myapp.com/download"
            }
        }


class ResolveResponse(BaseModel):
    """Ответ на запрос разрешения диплинка"""
    success: bool = Field(..., description="Успешность операции")
    promo_id: Optional[str] = Field(None, description="ID промо-акции")
    domain: Optional[str] = Field(None, description="Домен")
    session_id: Optional[str] = Field(None, description="ID сессии")
    redirect_url: Optional[str] = Field(None, description="URL для редиректа")
    app_url: Optional[str] = Field(None, description="URL приложения")
    matched: bool = Field(False, description="Найдено ли совпадение")
    message: Optional[str] = Field(None, description="Сообщение")

    def __init__(self, success: bool, **data):
        # Устанавливаем дефолтные значения для обязательных полей
        super().__init__(
            success=success,
            promo_id=data.get('promo_id'),
            domain=data.get('domain'),
            session_id=data.get('session_id'),
            redirect_url=data.get('redirect_url'),
            app_url=data.get('app_url'),
            matched=data.get('matched', False),
            message=data.get('message')
        )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "promo_id": "summer2024",
                "domain": "myapp.com",
                "session_id": "abc123-def456-ghi789",
                "matched": True,
                "message": None
            }
        }


class SessionData(BaseModel):
    """Данные сессии"""
    session_id: str = Field(..., description="ID сессии")
    promo_id: Optional[str] = Field(None, description="ID промо-акции")
    domain: Optional[str] = Field(None, description="Домен")
    user_agent: Optional[str] = Field(None, description="User Agent")
    timezone: Optional[str] = Field(None, description="Часовой пояс")
    language: Optional[str] = Field(None, description="Язык")
    screen_size: Optional[str] = Field(None, description="Размер экрана")
    model: Optional[str] = Field(None, description="Модель устройства")
    ip_address: Optional[str] = Field(None, description="IP адрес")
    created_at: datetime = Field(..., description="Время создания")
    expires_at: Optional[datetime] = Field(None, description="Время истечения")
    is_resolved: bool = Field(False, description="Статус разрешения")
    resolved_at: Optional[datetime] = Field(None, description="Время разрешения")
    match_confidence: Optional[float] = Field(None, description="Уверенность совпадения")
    match_details: Optional[Dict[str, Any]] = Field(None, description="Детали совпадения")


class SessionCreate(BaseModel):
    """Модель для создания сессии"""
    promo_id: str = Field(..., description="ID промо-акции")
    domain: str = Field(..., description="Домен")
    user_agent: str = Field(..., description="User Agent")
    timezone: Optional[str] = Field(None, description="Часовой пояс")
    language: Optional[str] = Field(None, description="Язык системы")
    screen_size: Optional[str] = Field(None, description="Размер экрана")
    model: Optional[str] = Field(None, description="Модель устройства")
    ttl_hours: int = Field(48, description="Время жизни в часах")
    ip_address: Optional[str] = Field(None, description="IP адрес")

    @validator("ttl_hours")
    def validate_ttl(cls, v):
        if v <= 0 or v > 168:  # Max 7 days
            raise ValueError("TTL must be between 1 and 168 hours")
        return v


class SessionResponse(BaseModel):
    """Ответ с информацией о сессии"""
    session_id: str = Field(..., description="ID сессии")
    promo_id: str = Field(..., description="ID промо-акции")
    domain: str = Field(..., description="Домен")
    created_at: str = Field(..., description="Время создания")
    expires_at: str = Field(..., description="Время истечения")
    resolved: bool = Field(..., description="Статус разрешения")


class StatsResponse(BaseModel):
    """Ответ со статистикой системы"""
    total_sessions: int = Field(..., description="Общее количество сессий")
    active_sessions: int = Field(..., description="Активные сессии")
    resolved_sessions: int = Field(..., description="Разрешенные сессии")
    success_rate: float = Field(..., description="Процент успешных разрешений")
    sessions_last_hour: int = Field(..., description="Сессии за последний час")
    average_confidence: float = Field(..., description="Средняя уверенность")
    timestamp: str = Field(..., description="Время получения статистики")


class HealthResponse(BaseModel):
    """Ответ health check"""
    status: str = Field(..., description="Статус системы")
    timestamp: str = Field(..., description="Время проверки")
    database: Optional[str] = Field(None, description="Статус базы данных")
    version: Optional[str] = Field(None, description="Версия приложения")


class CleanupResponse(BaseModel):
    """Ответ операции очистки"""
    success: bool = Field(..., description="Успешность операции")
    deleted_sessions: int = Field(..., description="Количество удаленных сессий")
    hours_threshold: int = Field(..., description="Порог в часах")
    timestamp: str = Field(..., description="Время операции")