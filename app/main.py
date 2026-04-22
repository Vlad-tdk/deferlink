"""
DeferLink FastAPI Application
Основное приложение для обработки отложенных диплинков
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, Literal, Union
import uvicorn
from fastapi import Cookie, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

# ИМПОРТЫ
from .config import Config
from .database import init_database
from .deeplink_handler import DeepLinkHandler
from .models import ResolveRequest, ResolveResponse
from .utils import detect_ios_device, generate_instruction_page, get_client_ip
from .api import deeplinks, health, stats, events as events_api
from .core.iab_detector import detect_browser, should_escape_to_safari, EscapeStrategy
from .core.safari_escape import generate_escape_page, build_app_store_url
from .core import devicecheck as dc_module

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Инициализация обработчика диплинков
deeplink_handler = DeepLinkHandler()

# Устанавливаем обработчик для API модулей
deeplinks.set_deeplink_handler(deeplink_handler)
stats.set_deeplink_handler(deeplink_handler)

# Глобальные переменные для задач
_cleanup_task: Optional[asyncio.Task[None]] = None
_optimization_task: Optional[asyncio.Task[None]] = None


async def cleanup_task() -> None:
    """Фоновая задача очистки истекших сессий"""
    while True:
        try:
            deleted_count = deeplink_handler.cleanup_expired_sessions()
            if deleted_count > 0:
                logger.info(f"Cleanup completed: {deleted_count} sessions deleted")
        except Exception as e:
            logger.error(f"Ошибка при очистке сессий: {e}")

        # Ожидание перед следующей очисткой
        await asyncio.sleep(Config.CLEANUP_INTERVAL_MINUTES * 60)


async def optimization_task() -> None:
    """Периодическая оптимизация алгоритма сопоставления"""
    while True:
        try:
            if Config.AUTO_OPTIMIZE_WEIGHTS:
                logger.info("Запуск автоматической оптимизации весов алгоритма")
                optimized_weights = deeplink_handler.optimize_algorithm_weights()
                logger.info(f"Автоматическая оптимизация весов завершена: {optimized_weights}")

            # Очистка кэшей для освобождения памяти
            deeplink_handler.intelligent_matcher.clear_cache()
            logger.debug("Кэши алгоритма сопоставления очищены")

        except Exception as e:
            logger.error(f"Ошибка автоматической оптимизации: {e}")

        # Выполняем каждый час
        await asyncio.sleep(3600)


async def startup_tasks():
    """Запуск фоновых задач"""
    global _cleanup_task, _optimization_task

    logger.info("Запуск приложения DeferLink...")

    #КРИТИЧНО: Валидация конфигурации ПЕРЕД запуском
    try:
        Config.validate_config()
        logger.info("Конфигурация валидна")

        # Вывод статуса конфигурации
        logger.info(f"Environment: {Config.ENVIRONMENT}")
        logger.info(f"SECRET_KEY: {'Set' if Config.SECRET_KEY != 'dev-secret-key-change-in-production' else 'DEFAULT (INSECURE!)'}")
        logger.info(f"CORS Origins: {Config.CORS_ORIGINS}")
        logger.info(f"Cookie Secure: {Config.COOKIE_SECURE}")
        logger.info(f"Rate Limiting: {Config.RATE_LIMIT_ENABLED}")

        if Config.ENVIRONMENT in ["production", "prod"]:
            logger.info("PRODUCTION MODE - Security checks enabled")
        else:
            logger.info("🛠️ DEVELOPMENT MODE")

    except ValueError as e:
        logger.error(f"ОШИБКА КОНФИГУРАЦИИ: {e}")
        raise SystemExit(1)  # Останавливаем приложение!

    # Инициализация базы данных
    init_database()
    logger.info("База данных инициализирована")

    # Инициализация DeviceCheck верификатора
    if Config.DEVICECHECK_ENABLED:
        dc_module.init_verifier(
            team_id=Config.DEVICECHECK_TEAM_ID or None,
            key_id=Config.DEVICECHECK_KEY_ID or None,
            private_key_path=Config.DEVICECHECK_KEY_PATH or None,
            use_sandbox=Config.DEVICECHECK_SANDBOX,
        )
        logger.info("DeviceCheck верификатор инициализирован")
    else:
        logger.info("DeviceCheck отключён (DEVICECHECK_ENABLED=false)")

    # Запуск фоновых задач
    _cleanup_task = asyncio.create_task(cleanup_task())
    _optimization_task = asyncio.create_task(optimization_task())
    logger.info("Фоновые задачи запущены")


async def shutdown_tasks():
    """Остановка фоновых задач"""
    global _cleanup_task, _optimization_task

    logger.info("Завершение работы приложения...")

    # Остановка фоновых задач
    if _cleanup_task is not None:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass

    if _optimization_task is not None:
        _optimization_task.cancel()
        try:
            await _optimization_task
        except asyncio.CancelledError:
            pass

    logger.info("Фоновые задачи остановлены")

    # Очистка ресурсов
    try:
        deeplink_handler.intelligent_matcher.clear_cache()
        logger.info("Ресурсы очищены")
    except Exception as e:
        logger.warning(f"Ошибка при очистке ресурсов: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    await startup_tasks()
    try:
        yield
    finally:
        await shutdown_tasks()


# Создание FastAPI приложения
app = FastAPI(
    title="DeferLink - Deferred Deep Links System",
    description="Кастомная система отложенных диплинков с интеллектуальным алгоритмом сопоставления",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Подключение роутеров
app.include_router(deeplinks.router)
app.include_router(health.router)
app.include_router(stats.router)
app.include_router(events_api.router)


# Обработчик ошибок
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Глобальный обработчик ошибок"""
    client_ip = get_client_ip(request)
    logger.error(f"Необработанная ошибка для {client_ip}: {exc}")

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Внутренняя ошибка сервера",
            "error_id": str(hash(str(exc)))[:8]
        }
    )


# Корневой endpoint
@app.get("/")
async def root():
    """Корневая страница API"""
    return {
        "message": "DeferLink API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/api/v1/health"
    }


# Основной endpoint для создания диплинков
@app.get("/dl")
async def create_deeplink(
    request: Request,
    response: Response,
    promo_id: str,
    domain: str,
    ttl: int = Config.DEFAULT_TTL_HOURS,
    session_id: Optional[str] = Cookie(None, alias=Config.COOKIE_NAME)
):
    """
    Создание или получение сессии диплинка с расширенным fingerprint

    Args:
        promo_id: ID промо-акции
        domain: Домен для редиректа
        ttl: Время жизни сессии в часах
        session_id: Существующий ID сессии (из cookie)

    Returns:
        HTML страница или редирект в App Store
    """
    user_agent = request.headers.get('user-agent', '')
    client_ip = get_client_ip(request)

    # Извлечение дополнительных параметров из query params
    timezone = request.query_params.get('timezone')
    language = request.query_params.get('language')
    screen_size = request.query_params.get('screen_size')
    model = request.query_params.get('model')

    # Детекция фрода если включена
    if Config.FRAUD_DETECTION_ENABLED:
        fingerprint_dict = {
            'user_agent': user_agent,
            'timezone': timezone,
            'language': language,
            'screen_size': screen_size,
            'model': model
        }

        fraud_result = deeplink_handler.detect_potential_fraud(fingerprint_dict, client_ip)

        if fraud_result['risk_score'] > Config.FRAUD_RISK_THRESHOLD:
            logger.warning(f"Высокий риск фрода от IP {client_ip}: {fraud_result}")

            if 'block_request' in fraud_result['recommendations']:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Слишком много запросов. Попробуйте позже."
                )

    # Проверка существующей сессии
    if session_id:
        existing_session = deeplink_handler.get_session(session_id)
        if existing_session:
            logger.info(f"Используется существующая сессия: {session_id}")

            # Определение нужного действия
            if detect_ios_device(user_agent):
                # Редирект в App Store для iOS
                app_store_url = f"https://apps.apple.com/app/id{promo_id}" if promo_id.isdigit() else "https://apps.apple.com"
                return RedirectResponse(url=app_store_url)
            else:
                # Возврат HTML страницы с инструкциями
                return HTMLResponse(content=generate_instruction_page(domain, promo_id))

    # ── Определяем контекст браузера ──────────────────────────────────────────
    browser_info = detect_browser(user_agent)
    source_context = browser_info.context.value

    # Создание новой сессии
    try:
        new_session_id = deeplink_handler.create_session(
            promo_id=promo_id,
            domain=domain,
            user_agent=user_agent,
            timezone=timezone,
            language=language,
            screen_size=screen_size,
            model=model,
            ttl_hours=ttl,
            ip_address=client_ip,
            source_context=source_context,
        )

        logger.info(
            "Создана сессия: %s | source=%s | ip=%s",
            new_session_id, source_context, client_ip
        )

        samesite_value: Literal["lax", "strict", "none"] = Config.COOKIE_SAMESITE

        def _set_cookie(resp: Response) -> Response:
            """Устанавливает cookie на любой ответ (RedirectResponse или HTMLResponse)."""
            resp.set_cookie(
                key=Config.COOKIE_NAME,
                value=new_session_id,
                max_age=ttl * 3600,
                secure=Config.COOKIE_SECURE,
                httponly=Config.COOKIE_HTTPONLY,
                samesite=samesite_value,
            )
            return resp

        # ── IAB detected → Safari escape ──────────────────────────────────────
        if should_escape_to_safari(browser_info):
            store_id  = promo_id if promo_id.isdigit() else Config.APP_STORE_ID
            store_url = (
                build_app_store_url(store_id)
                if store_id
                else "https://apps.apple.com"
            )

            if browser_info.clipboard_reliable:
                logger.info(
                    "IAB escape [clipboard+appstore]: source=%s session=%s",
                    source_context, new_session_id
                )
                html = generate_escape_page(
                    session_token=new_session_id,
                    app_store_url=store_url,
                    app_name=Config.APP_NAME,
                    app_store_id=store_id or None,
                )
                return HTMLResponse(content=html)
            else:
                logger.info(
                    "IAB escape [appstore-only]: source=%s session=%s",
                    source_context, new_session_id
                )
                return _set_cookie(RedirectResponse(url=store_url, status_code=302))

        # ── Safari или неизвестный браузер ─────────────────────────────────────
        if detect_ios_device(user_agent):
            store_id  = promo_id if promo_id.isdigit() else Config.APP_STORE_ID
            store_url = build_app_store_url(store_id) if store_id else "https://apps.apple.com"
            # Cookie важен для SFSafariViewController (Tier 2 matching)
            return _set_cookie(RedirectResponse(url=store_url, status_code=302))

        return HTMLResponse(content=generate_instruction_page(domain, promo_id))

    except Exception as e:
        logger.error("Ошибка создания сессии: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка создания сессии диплинка"
        )


@app.get("/safari-resolve")
async def safari_cookie_resolve(
    request: Request,
    session_id: Optional[str] = Cookie(None, alias=Config.COOKIE_NAME),
):
    """
    SFSafariViewController Silent Cookie Resolve.

    Приложение открывает этот URL в SFSafariViewController на первом запуске.
    SFSafariViewController разделяет cookie-jar с Safari — если пользователь
    ранее переходил по нашей ссылке в Safari, cookie с session_id уже есть.

    Страница читает cookie → делает redirect на custom URL scheme → app получает session_id.

    Схема: deferlink://resolved?session_id=<id>
    """
    app_scheme = Config.APP_URL_SCHEME

    if session_id:
        existing = deeplink_handler.get_session(session_id)
        if existing and not existing.get('is_resolved'):
            # Редирект в приложение с session_id через URL scheme
            logger.info("safari-resolve: cookie match session=%s", session_id)
            redirect_url = f"{app_scheme}://resolved?session_id={session_id}"
            return RedirectResponse(url=redirect_url)

    # Cookie не найден — тихо закрываем через redirect без session_id
    # Приложение поймает этот callback и продолжит с fingerprint matching
    return RedirectResponse(url=f"{app_scheme}://resolved?session_id=none")


@app.post("/resolve", response_model=ResolveResponse)
async def resolve_deeplink(request: ResolveRequest) -> ResolveResponse:
    """
    Разрешение диплинка по fingerprint с использованием интеллектуального алгоритма

    Args:
        request: Запрос с fingerprint данными

    Returns:
        Информация о найденном диплинке или null
    """
    try:
        # Поиск подходящей сессии с новым алгоритмом
        matching_session = deeplink_handler.find_matching_session(request.fingerprint)

        if matching_session:
            confidence_score = matching_session.get('match_confidence', 0.0)
            match_details    = matching_session.get('match_details', {})
            match_method     = matching_session.get('match_method') or (match_details or {}).get('method')

            deeplink_handler.mark_session_resolved(
                session_id=matching_session['session_id'],
                confidence_score=confidence_score,
                match_details=match_details,
                device_check_token_b64=request.fingerprint.device_check_token,
            )

            logger.info(
                "Resolved: session=%s method=%s confidence=%.3f",
                matching_session['session_id'], match_method, confidence_score
            )

            return ResolveResponse(
                success=True,
                promo_id=matching_session.get('promo_id'),
                domain=matching_session.get('domain'),
                session_id=matching_session.get('session_id'),
                redirect_url=request.fallback_url,
                app_url=request.app_scheme,
                matched=True,
                match_method=match_method,
                message="Сессия успешно разрешена"
            )
        else:
            logger.info("Совпадение не найдено или сессия истекла")
            return ResolveResponse(
                success=False,
                promo_id=None,
                domain=None,
                session_id=None,
                redirect_url=request.fallback_url,
                app_url=request.app_scheme,
                matched=False,
                match_method=None,
                message="Совпадение не найдено или сессия истекла"
            )

    except Exception as e:
        logger.error(f"Ошибка при разрешении диплинка: {e}")
        return ResolveResponse(
            success=False,
            promo_id=None,
            domain=None,
            session_id=None,
            redirect_url=request.fallback_url,
            app_url=request.app_scheme,
            matched=False,
            message=f"Ошибка сервера: {str(e)}"
        )


# Middleware для логирования запросов
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Логирование HTTP запросов"""
    start_time = asyncio.get_event_loop().time()
    client_ip = get_client_ip(request)

    # Выполнение запроса
    response = await call_next(request)

    # Логирование
    process_time = asyncio.get_event_loop().time() - start_time
    logger.info(
        f"{request.method} {request.url.path} - "
        f"IP: {client_ip} - "
        f"Status: {response.status_code} - "
        f"Time: {process_time:.4f}s"
    )

    return response


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=Config.API_HOST,
        port=Config.API_PORT,
        reload=Config.LOG_LEVEL == "DEBUG",
        log_level=Config.LOG_LEVEL.lower(),
        access_log=True
    )