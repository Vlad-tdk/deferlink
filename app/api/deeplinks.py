"""
Deep link API endpoints
Эндпоинты API для диплинков
"""

import html
import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from ..config import Config
from ..core import devicecheck as dc_module
from ..models import ResolveRequest, ResolveResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["deeplinks"])

# Глобальная переменная для handler
deeplink_handler = None


def set_deeplink_handler(handler):
    """Установка обработчика диплинков из main.py"""
    global deeplink_handler
    deeplink_handler = handler


def _copy_fingerprint_without_devicecheck(resolve_request: ResolveRequest) -> ResolveRequest:
    try:
        fingerprint = resolve_request.fingerprint.model_copy(update={"device_check_token": None})
        return resolve_request.model_copy(update={"fingerprint": fingerprint})
    except AttributeError:
        fingerprint = resolve_request.fingerprint.copy(update={"device_check_token": None})
        return resolve_request.copy(update={"fingerprint": fingerprint})


@router.post("/session", status_code=status.HTTP_201_CREATED)
async def create_session(request: Request) -> Dict[str, str]:
    """Создание новой браузерной сессии"""
    try:
        if not deeplink_handler:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Handler not initialized"
            )

        user_agent = request.headers.get("User-Agent", "")
        session_id = deeplink_handler.create_session(
            promo_id="default",
            domain="default.com",
            user_agent=user_agent
        )

        return {
            "session_id": session_id,
            "status": "created"
        }

    except Exception as e:
        logger.error(f"Error creating session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating session"
        )


@router.post("/resolve", response_model=ResolveResponse)
async def resolve_deeplink(request: ResolveRequest) -> ResolveResponse:
    """Разрешение диплинка"""
    try:
        if not deeplink_handler:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Handler not initialized"
            )

        prepared_request = request
        verified_devicecheck_token = None
        token = request.fingerprint.device_check_token
        if token and Config.DEVICECHECK_ENABLED:
            verification = await dc_module.get_verifier().verify(token)
            if verification.status == "valid":
                verified_devicecheck_token = token
            else:
                logger.info(
                    "DeviceCheck token not trusted for API resolve: status=%s reason=%s",
                    verification.status,
                    verification.reason,
                )
                prepared_request = _copy_fingerprint_without_devicecheck(request)

        matching_session = deeplink_handler.resolve_matching_session(
            prepared_request.fingerprint,
            device_check_token_b64=verified_devicecheck_token,
        )

        if matching_session:
            confidence_score = matching_session.get('match_confidence', 0.0)
            match_details    = matching_session.get('match_details', {})
            match_method     = matching_session.get('match_method') or (match_details or {}).get('method')

            return ResolveResponse(
                success=True,
                promo_id=matching_session.get('promo_id'),
                domain=matching_session.get('domain'),
                session_id=matching_session['session_id'],
                redirect_url=prepared_request.fallback_url,
                app_url=prepared_request.app_scheme,
                matched=True,
                match_method=match_method,
                message="Сессия успешно разрешена"
            )
        else:
            # Запрос обработан — просто нет атрибуции. Не ошибка.
            return ResolveResponse(
                success=True,
                promo_id=None,
                domain=None,
                session_id=None,
                redirect_url=prepared_request.fallback_url,
                app_url=prepared_request.app_scheme,
                matched=False,
                match_method=None,
                message="Подходящая сессия не найдена"
            )

    except Exception as e:
        logger.error(f"Error resolving deeplink: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error resolving deeplink"
        )


@router.get("/instruction/{session_id}")
async def get_instruction_page(session_id: str) -> HTMLResponse:
    """Страница с инструкциями"""
    safe_session_id = html.escape(session_id, quote=True)
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Instructions</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                margin: 0;
                padding: 20px;
                background: #f5f5f5;
                color: #333;
            }}
            .container {{
                max-width: 400px;
                margin: 0 auto;
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                text-align: center;
            }}
            h1 {{
                color: #007AFF;
                margin-bottom: 20px;
            }}
            p {{
                line-height: 1.6;
                margin-bottom: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📱 Open App</h1>
            <p>Session ID: {safe_session_id}</p>
            <p>Please open the application on your device to continue.</p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
