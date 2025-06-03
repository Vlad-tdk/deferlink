"""
Health check API endpoints
Эндпоинты для проверки состояния системы
"""

import logging
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, status

from ..database import db_manager
from ..models import HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Основная проверка состояния системы"""
    try:
        # Проверка базы данных
        db_healthy = db_manager.health_check()

        if not db_healthy:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unhealthy"
            )

        return HealthResponse(
            status="healthy",
            timestamp=datetime.now().isoformat(),
            database="ok",
            version="1.0.0"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unhealthy"
        )


@router.get("/health/quick")
async def quick_health() -> Dict[str, str]:
    """Быстрая проверка состояния"""
    try:
        db_healthy = db_manager.health_check()

        if not db_healthy:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service unavailable"
            )

        return {
            "status": "ok",
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Quick health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unavailable"
        )


@router.get("/health/detailed")
async def detailed_health() -> Dict[str, Any]:
    """Детальная проверка состояния системы"""
    try:
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "components": {}
        }

        # Проверка базы данных
        try:
            db_healthy = db_manager.health_check()
            db_size = db_manager.get_database_size()

            health_status["components"]["database"] = {
                "status": "healthy" if db_healthy else "unhealthy",
                "size_bytes": db_size,
                "size_mb": round(db_size / 1024 / 1024, 2)
            }
        except Exception as e:
            health_status["components"]["database"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "degraded"

        # Проверка статистики сессий
        try:
            from ..deeplink_handler import deeplink_handler
            stats = deeplink_handler.get_stats()

            health_status["components"]["sessions"] = {
                "status": "healthy",
                "total_sessions": stats.get("total_sessions", 0),
                "active_sessions": stats.get("active_sessions", 0),
                "success_rate": stats.get("success_rate", 0.0)
            }
        except Exception as e:
            health_status["components"]["sessions"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "degraded"

        return health_status

    except Exception as e:
        logger.error(f"Detailed health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Health check failed"
        )