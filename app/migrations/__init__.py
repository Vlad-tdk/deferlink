"""
Database Migrations Package
Пакет миграций базы данных
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Реестр всех доступных миграций
AVAILABLE_MIGRATIONS = [
    "add_enhanced_fields",
]

def get_migration_module(migration_name: str):
    """Получение модуля миграции по имени"""
    try:
        if migration_name == "add_enhanced_fields":
            from .add_enhanced_fields import check_migration_needed, migrate_database
            return {
                'check_needed': check_migration_needed,
                'migrate': migrate_database,
                'name': migration_name
            }
    except ImportError as e:
        logger.warning(f"Миграция {migration_name} недоступна: {e}")
        return None

def run_all_migrations(db_path: str) -> bool:
    """Запуск всех доступных миграций"""
    success = True

    for migration_name in AVAILABLE_MIGRATIONS:
        try:
            migration = get_migration_module(migration_name)
            if migration and migration['check_needed'](db_path):
                logger.info(f"Выполняется миграция: {migration_name}")
                if migration['migrate'](db_path):
                    logger.info(f"Миграция {migration_name} выполнена успешно")
                else:
                    logger.error(f"Ошибка миграции {migration_name}")
                    success = False
        except Exception as e:
            logger.error(f"Критическая ошибка миграции {migration_name}: {e}")
            success = False

    return success

# Экспорт
__all__ = [
    "AVAILABLE_MIGRATIONS",
    "get_migration_module",
    "run_all_migrations",
]