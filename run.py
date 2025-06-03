#!/usr/bin/env python3
"""
DeferLink - Entry Point
Основной файл для запуска приложения
"""

import uvicorn
from app.main import app
from app.config import Config

if __name__ == "__main__":
    # Валидация конфигурации
    try:
        Config.validate_config()
        print("✓ Configuration validation passed")
    except ValueError as e:
        print(f"✗ Configuration error: {e}")
        exit(1)

    # Запуск сервера
    uvicorn.run(
        "app.main:app",
        host=Config.API_HOST,
        port=Config.API_PORT,
        workers=Config.API_WORKERS if Config.API_WORKERS > 1 else None,
        reload=Config.LOG_LEVEL == "DEBUG",
        log_level=Config.LOG_LEVEL.lower(),
        access_log=True
    )
