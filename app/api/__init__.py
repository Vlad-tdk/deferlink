"""
API Package - FastAPI routers and endpoints
Пакет API с роутерами и endpoints
"""

# Импорт всех роутеров
from . import deeplinks
from . import health
from . import stats
from . import events

# Список всех роутеров для подключения в main.py
routers = [
    deeplinks.router,
    health.router,
    stats.router,
    events.router,
]

# Экспорт для удобства
__all__ = [
    "deeplinks",
    "health",
    "stats",
    "events",
    "routers",
]