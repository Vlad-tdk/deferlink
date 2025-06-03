"""
Configuration settings for DeferLink system
Настройки конфигурации для системы DeferLink
"""

import os
from typing import List, Literal, cast


class Config:
    """Configuration class with all settings"""

    # Database settings
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/deeplinks.db")
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_PATH}")

    # Cookie settings
    COOKIE_NAME: str = "dl_session_id"
    COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "true").lower() == "true"
    COOKIE_HTTPONLY: bool = os.getenv("COOKIE_HTTPONLY", "true").lower() == "true"
    _COOKIE_SAMESITE_RAW: str = os.getenv("COOKIE_SAMESITE", "lax").lower()
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = cast(
        Literal["lax", "strict", "none"],
        "lax" if _COOKIE_SAMESITE_RAW not in ["lax", "strict", "none"] else _COOKIE_SAMESITE_RAW
    )

    # Security settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

    # Deep link settings
    DEFAULT_TTL_HOURS: int = int(os.getenv("DEFAULT_TTL_HOURS", "48"))
    MAX_FINGERPRINT_DISTANCE: int = int(os.getenv("MAX_FINGERPRINT_DISTANCE", "2"))
    CLEANUP_INTERVAL_MINUTES: int = int(os.getenv("CLEANUP_INTERVAL_MINUTES", "30"))

    # API settings
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    API_WORKERS: int = int(os.getenv("API_WORKERS", "1"))

    # Rate limiting
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    RATE_LIMIT_BURST: int = int(os.getenv("RATE_LIMIT_BURST", "10"))

    # CORS settings
    CORS_ORIGINS: List[str] = [
        origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",")
    ]

    # Monitoring
    ENABLE_METRICS: bool = os.getenv("ENABLE_METRICS", "false").lower() == "true"
    METRICS_PORT: int = int(os.getenv("METRICS_PORT", "9090"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # Analytics
    ENABLE_ANALYTICS: bool = os.getenv("ENABLE_ANALYTICS", "true").lower() == "true"
    ANALYTICS_RETENTION_DAYS: int = int(os.getenv("ANALYTICS_RETENTION_DAYS", "90"))

    # Security
    MAX_CONTENT_LENGTH: int = int(os.getenv("MAX_CONTENT_LENGTH", "1048576"))  # 1MB
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "30"))

    # Fraud detection
    FRAUD_DETECTION_ENABLED: bool = os.getenv("FRAUD_DETECTION_ENABLED", "false").lower() == "true"
    FRAUD_RISK_THRESHOLD: float = float(os.getenv("FRAUD_RISK_THRESHOLD", "0.8"))

    # Algorithm optimization
    AUTO_OPTIMIZE_WEIGHTS: bool = os.getenv("AUTO_OPTIMIZE_WEIGHTS", "false").lower() == "true"

    @classmethod
    def validate_config(cls) -> bool:
        """Validate configuration settings"""
        #if cls.SECRET_KEY == "dev-secret-key-change-in-production" and cls.COOKIE_SECURE:
           # raise ValueError("SECRET_KEY must be changed in production")

        if cls.DEFAULT_TTL_HOURS <= 0 or cls.DEFAULT_TTL_HOURS > 168:  # Max 7 days
            raise ValueError("DEFAULT_TTL_HOURS must be between 1 and 168 hours")

        if cls.MAX_FINGERPRINT_DISTANCE < 0 or cls.MAX_FINGERPRINT_DISTANCE > 10:
            raise ValueError("MAX_FINGERPRINT_DISTANCE must be between 0 and 10")

        if cls.LOG_LEVEL not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            raise ValueError(f"Invalid LOG_LEVEL: {cls.LOG_LEVEL}")

        if cls.FRAUD_RISK_THRESHOLD < 0.0 or cls.FRAUD_RISK_THRESHOLD > 1.0:
            raise ValueError("FRAUD_RISK_THRESHOLD must be between 0.0 and 1.0")

        return True