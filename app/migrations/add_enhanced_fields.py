"""
Migration: Add enhanced fields to deeplink_sessions table
Миграция: Добавление расширенных полей в таблицу deeplink_sessions
"""

import logging
import sqlite3
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Новые поля для добавления
NEW_FIELDS = [
    ('ip_address', 'TEXT'),
    ('match_confidence', 'REAL'),
    ('match_details', 'TEXT'),
    ('updated_at', 'TIMESTAMP'),
]


def check_migration_needed(db_path: str) -> bool:
    """
    Проверка необходимости выполнения миграции

    Args:
        db_path: Путь к файлу базы данных

    Returns:
        True если миграция нужна, False если уже выполнена
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Получение списка существующих колонок
        cursor.execute("PRAGMA table_info(deeplink_sessions)")
        existing_columns = {row[1] for row in cursor.fetchall()}

        conn.close()

        # Проверка наличия новых полей
        new_field_names = {field[0] for field in NEW_FIELDS}
        missing_fields = new_field_names - existing_columns

        migration_needed = len(missing_fields) > 0

        if migration_needed:
            logger.info(f"Миграция необходима. Отсутствующие поля: {missing_fields}")
        else:
            logger.info("Миграция не нужна - все поля уже существуют")

        return migration_needed

    except sqlite3.Error as e:
        logger.error(f"Ошибка проверки необходимости миграции: {e}")
        return False
    except Exception as e:
        logger.error(f"Неожиданная ошибка при проверке миграции: {e}")
        return False


def migrate_database(db_path: str) -> bool:
    """
    Выполнение миграции базы данных

    Args:
        db_path: Путь к файлу базы данных

    Returns:
        True если миграция успешна, False в случае ошибки
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Включение поддержки внешних ключей
        cursor.execute("PRAGMA foreign_keys = ON")

        # Получение текущей схемы таблицы
        cursor.execute("PRAGMA table_info(deeplink_sessions)")
        existing_columns = {row[1]: row[2] for row in cursor.fetchall()}

        logger.info(f"Существующие колонки: {list(existing_columns.keys())}")

        # Добавление новых полей
        fields_added = []

        for field_name, field_type in NEW_FIELDS:
            if field_name not in existing_columns:
                try:
                    # Создание ALTER TABLE запроса
                    alter_query = f"ALTER TABLE deeplink_sessions ADD COLUMN {field_name} {field_type}"
                    cursor.execute(alter_query)

                    fields_added.append(field_name)
                    logger.info(f"Добавлено поле: {field_name} ({field_type})")

                except sqlite3.Error as e:
                    logger.error(f"Ошибка добавления поля {field_name}: {e}")
                    conn.rollback()
                    conn.close()
                    return False

        # Создание индексов для новых полей (для производительности)
        indexes_to_create = [
            ("idx_ip_address", "ip_address"),
            ("idx_match_confidence", "match_confidence"),
            ("idx_updated_at", "updated_at"),
        ]

        for index_name, column_name in indexes_to_create:
            if column_name in fields_added:
                try:
                    cursor.execute(f"""
                        CREATE INDEX IF NOT EXISTS {index_name}
                        ON deeplink_sessions({column_name})
                    """)
                    logger.info(f"Создан индекс: {index_name}")
                except sqlite3.Error as e:
                    logger.warning(f"Не удалось создать индекс {index_name}: {e}")

        # Обновление существующих записей (установка значений по умолчанию)
        if 'updated_at' in fields_added:
            cursor.execute("""
                UPDATE deeplink_sessions
                SET updated_at = created_at
                WHERE updated_at IS NULL
            """)
            logger.info("Установлены значения updated_at для существующих записей")

        # Фиксация изменений
        conn.commit()
        conn.close()

        logger.info(f"Миграция успешно завершена. Добавлено полей: {len(fields_added)}")

        return True

    except sqlite3.Error as e:
        logger.error(f"Ошибка SQLite при миграции: {e}")
        try:
            conn.rollback()
            conn.close()
        except:
            pass
        return False
    except Exception as e:
        logger.error(f"Неожиданная ошибка при миграции: {e}")
        try:
            conn.rollback()
            conn.close()
        except:
            pass
        return False


def rollback_migration(db_path: str) -> bool:
    """
    Откат миграции (удаление добавленных полей)

    Args:
        db_path: Путь к файлу базы данных

    Returns:
        True если откат успешен, False в случае ошибки
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        logger.warning("Выполняется откат миграции add_enhanced_fields")

        # В SQLite нельзя удалить колонки напрямую, нужно пересоздать таблицу

        # 1. Создание временной таблицы с исходной схемой
        cursor.execute("""
            CREATE TABLE deeplink_sessions_backup AS
            SELECT session_id, created_at, user_agent, custom_data, is_resolved
            FROM deeplink_sessions
        """)

        # 2. Удаление исходной таблицы
        cursor.execute("DROP TABLE deeplink_sessions")

        # 3. Пересоздание таблицы с исходной схемой
        cursor.execute("""
            CREATE TABLE deeplink_sessions (
                session_id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_agent TEXT,
                custom_data TEXT,
                is_resolved BOOLEAN DEFAULT FALSE
            )
        """)

        # 4. Копирование данных обратно
        cursor.execute("""
            INSERT INTO deeplink_sessions
            SELECT * FROM deeplink_sessions_backup
        """)

        # 5. Удаление временной таблицы
        cursor.execute("DROP TABLE deeplink_sessions_backup")

        # 6. Пересоздание исходных индексов
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_created
            ON deeplink_sessions(created_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_resolved
            ON deeplink_sessions(is_resolved)
        """)

        conn.commit()
        conn.close()

        logger.info("Откат миграции успешно завершен")
        return True

    except sqlite3.Error as e:
        logger.error(f"Ошибка при откате миграции: {e}")
        try:
            conn.rollback()
            conn.close()
        except:
            pass
        return False
    except Exception as e:
        logger.error(f"Неожиданная ошибка при откате миграции: {e}")
        try:
            conn.rollback()
            conn.close()
        except:
            pass
        return False


def get_migration_info() -> dict:
    """
    Информация о миграции

    Returns:
        Словарь с информацией о миграции
    """
    return {
        'name': 'add_enhanced_fields',
        'description': 'Добавление расширенных полей для ИИ сопоставления',
        'version': '1.0.0',
        'fields_added': [field[0] for field in NEW_FIELDS],
        'reversible': True,
        'dependencies': []
    }