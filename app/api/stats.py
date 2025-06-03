"""
Statistics API endpoints
Эндпоинты для статистики системы
"""

import logging
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, status

from ..models import StatsResponse, CleanupResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["statistics"])

# Глобальная переменная для handler
deeplink_handler = None


def set_deeplink_handler(handler):
    """Установка обработчика диплинков из main.py"""
    global deeplink_handler
    deeplink_handler = handler


@router.get("/stats", response_model=StatsResponse)
async def get_stats() -> StatsResponse:
    """Получение базовой статистики"""
    try:
        if not deeplink_handler:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Handler not initialized"
            )

        stats = deeplink_handler.get_stats()

        return StatsResponse(
            total_sessions=stats.get('total_sessions', 0),
            active_sessions=stats.get('active_sessions', 0),
            resolved_sessions=stats.get('resolved_sessions', 0),
            success_rate=stats.get('success_rate', 0.0),
            sessions_last_hour=stats.get('sessions_last_hour', 0),
            average_confidence=stats.get('average_confidence', 0.0),
            timestamp=stats.get('timestamp', '')
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error getting statistics"
        )


@router.get("/stats/detailed")
async def get_detailed_stats() -> Dict[str, Any]:
    """Получение детальной статистики"""
    try:
        if not deeplink_handler:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Handler not initialized"
            )

        stats = deeplink_handler.get_stats()

        # Добавляем дополнительную информацию
        detailed_stats = {
            **stats,
            "matcher_info": {
                "weights": deeplink_handler.intelligent_matcher.weights,
                "thresholds": deeplink_handler.intelligent_matcher.confidence_thresholds
            }
        }

        return detailed_stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting detailed stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error getting detailed statistics"
        )


@router.post("/cleanup", response_model=CleanupResponse)
async def cleanup_expired_sessions() -> CleanupResponse:
    """Очистка истекших сессий"""
    try:
        if not deeplink_handler:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Handler not initialized"
            )

        deleted_count = deeplink_handler.cleanup_expired_sessions()

        return CleanupResponse(
            success=True,
            deleted_sessions=deleted_count,
            hours_threshold=24,  # По умолчанию 24 часа
            timestamp=datetime.now().isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error during cleanup"
        )


@router.get("/stats/analytics")
async def get_analytics_stats() -> Dict[str, Any]:
    """Получение аналитической статистики"""
    try:
        if not deeplink_handler:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Handler not initialized"
            )

        from ..database import db_manager

        # Статистика по типам событий
        query_events = """
            SELECT event_type, COUNT(*) as count
            FROM analytics_events
            WHERE timestamp >= datetime('now', '-24 hours')
            GROUP BY event_type
        """
        events_stats = db_manager.execute_query(query_events)

        # Статистика по часам
        query_hourly = """
            SELECT strftime('%H', timestamp) as hour, COUNT(*) as count
            FROM analytics_events
            WHERE timestamp >= datetime('now', '-24 hours')
            GROUP BY hour
            ORDER BY hour
        """
        hourly_stats = db_manager.execute_query(query_hourly)

        # Статистика по уверенности сопоставления
        query_confidence = """
            SELECT
                CASE
                    WHEN match_confidence >= 0.8 THEN 'high'
                    WHEN match_confidence >= 0.6 THEN 'medium'
                    WHEN match_confidence >= 0.4 THEN 'low'
                    ELSE 'very_low'
                END as confidence_level,
                COUNT(*) as count
            FROM deeplink_sessions
            WHERE match_confidence IS NOT NULL
            AND created_at >= datetime('now', '-24 hours')
            GROUP BY confidence_level
        """
        confidence_stats = db_manager.execute_query(query_confidence)

        return {
            "events_by_type": {row['event_type']: row['count'] for row in events_stats},
            "events_by_hour": {row['hour']: row['count'] for row in hourly_stats},
            "confidence_distribution": {row['confidence_level']: row['count'] for row in confidence_stats},
            "period": "24_hours"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analytics stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error getting analytics statistics"
        )