"""
Database operations for DeferLink system
Операции с базой данных для системы DeferLink
"""

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from contextlib import contextmanager

from .config import Config

logger = logging.getLogger(__name__)


def init_database(db_path: Optional[str] = None) -> None:
    """Инициализация базы данных с поддержкой миграций"""
    actual_db_path: str = db_path or Config.DATABASE_PATH

    # Создание директории если не существует
    Path(actual_db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(actual_db_path)
    cursor = conn.cursor()

    try:
        # Включение поддержки внешних ключей
        cursor.execute("PRAGMA foreign_keys = ON")

        # Создание таблицы сессий с расширенными полями
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deeplink_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                promo_id TEXT,
                domain TEXT,
                user_agent TEXT,
                timezone TEXT,
                language TEXT,
                screen_size TEXT,
                model TEXT,
                idfv TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                is_resolved BOOLEAN DEFAULT FALSE,
                resolved_at TIMESTAMP,
                fingerprint_distance INTEGER,
                ip_address TEXT,
                match_confidence REAL,
                match_details TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Создание таблицы аналитики
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS analytics_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                event_type TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT,
                FOREIGN KEY (session_id) REFERENCES deeplink_sessions(session_id)
            )
        ''')

        # Создание индексов для оптимизации поиска
        indexes = [
            'CREATE INDEX IF NOT EXISTS idx_session_id ON deeplink_sessions(session_id)',
            'CREATE INDEX IF NOT EXISTS idx_expires_at ON deeplink_sessions(expires_at)',
            'CREATE INDEX IF NOT EXISTS idx_fingerprint ON deeplink_sessions(user_agent, language, timezone, model)',
            'CREATE INDEX IF NOT EXISTS idx_created_at ON deeplink_sessions(created_at)',
            'CREATE INDEX IF NOT EXISTS idx_resolved ON deeplink_sessions(is_resolved)',
            'CREATE INDEX IF NOT EXISTS idx_analytics_timestamp ON analytics_events(timestamp)',
            'CREATE INDEX IF NOT EXISTS idx_analytics_event_type ON analytics_events(event_type)',
            'CREATE INDEX IF NOT EXISTS idx_ip_address ON deeplink_sessions(ip_address)',
            'CREATE INDEX IF NOT EXISTS idx_match_confidence ON deeplink_sessions(match_confidence)',
            'CREATE INDEX IF NOT EXISTS idx_resolved_at ON deeplink_sessions(resolved_at)',
            'CREATE INDEX IF NOT EXISTS idx_active_sessions ON deeplink_sessions(expires_at, is_resolved) WHERE is_resolved = FALSE',
            'CREATE INDEX IF NOT EXISTS idx_updated_at ON deeplink_sessions(updated_at)'
        ]

        for index_sql in indexes:
            cursor.execute(index_sql)

        conn.commit()
        logger.info(f"База данных инициализирована: {actual_db_path}")

    except Exception as e:
        logger.error(f"Ошибка инициализации базы данных: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


class DatabaseManager:
    """Менеджер для работы с базой данных"""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path: str = db_path or Config.DATABASE_PATH

    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для получения соединения с базой данных"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Для доступа к колонкам по имени
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute_query(self, query: str, params: Union[tuple, List] = ()) -> List[Dict[str, Any]]:
        """Выполнение SELECT запроса"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def execute_update(self, query: str, params: Union[tuple, List] = ()) -> int:
        """Выполнение INSERT/UPDATE/DELETE запроса"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount

    def execute_insert(self, query: str, params: Union[tuple, List] = ()) -> Optional[int]:
        """Выполнение INSERT запроса с возвратом ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.lastrowid

    def execute_many(self, query: str, params_list: List[Union[tuple, List]]) -> int:
        """Выполнение множественных операций"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            conn.commit()
            return cursor.rowcount

    def health_check(self) -> bool:
        """Проверка состояния базы данных"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Получение информации о таблице"""
        query = f"PRAGMA table_info({table_name})"
        return self.execute_query(query)

    def vacuum_database(self) -> None:
        """Оптимизация базы данных"""
        try:
            with self.get_connection() as conn:
                conn.execute("VACUUM")
                logger.info("Database vacuumed successfully")
        except Exception as e:
            logger.error(f"Failed to vacuum database: {e}")
            raise

    def get_database_size(self) -> int:
        """Получение размера базы данных в байтах"""
        try:
            return Path(self.db_path).stat().st_size
        except Exception as e:
            logger.error(f"Failed to get database size: {e}")
            return 0

    def backup_database(self, backup_path: str) -> bool:
        """Создание резервной копии базы данных"""
        try:
            with self.get_connection() as source:
                backup = sqlite3.connect(backup_path)
                source.backup(backup)
                backup.close()
            logger.info(f"Database backed up to: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to backup database: {e}")
            return False


# Глобальный экземпляр менеджера базы данных
db_manager = DatabaseManager()