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
from .api import deeplinks, health, stats

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

    # Валидация конфигурации
    Config.validate_config()
    logger.info("Конфигурация валидна")

    # Инициализация базы данных
    init_database()
    logger.info("База данных инициализирована")

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

    # Создание новой сессии с расширенными данными
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
            ip_address=client_ip
        )

        # Установка cookie
        samesite_value: Literal["lax", "strict", "none"] = Config.COOKIE_SAMESITE

        response.set_cookie(
            key=Config.COOKIE_NAME,
            value=new_session_id,
            max_age=ttl * 3600,  # TTL в секундах
            secure=Config.COOKIE_SECURE,
            httponly=Config.COOKIE_HTTPONLY,
            samesite=samesite_value
        )

        logger.info(f"Создана новая сессия: {new_session_id} от IP: {client_ip}")

        # Определение действия на основе user agent
        if detect_ios_device(user_agent):
            # Редирект в App Store для iOS
            app_store_url = f"https://apps.apple.com/app/id{promo_id}" if promo_id.isdigit() else "https://apps.apple.com"
            return RedirectResponse(url=app_store_url)
        else:
            # Возврат HTML страницы с инструкциями
            return HTMLResponse(content=generate_instruction_page(domain, promo_id))

    except Exception as e:
        logger.error(f"Ошибка создания сессии: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка создания сессии диплинка"
        )


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
            # Отметка сессии как разрешенной с сохранением данных о matching
            confidence_score = matching_session.get('match_confidence', 0.0)
            match_details = matching_session.get('match_details', {})

            deeplink_handler.mark_session_resolved(
                matching_session['session_id'],
                confidence_score,
                match_details
            )

            logger.info(f"Найдено совпадение для сессии: {matching_session['session_id']} "
                       f"с уверенностью: {confidence_score:.3f}")

            return ResolveResponse(
                success=True,
                promo_id=matching_session.get('promo_id'),
                domain=matching_session.get('domain'),
                session_id=matching_session.get('session_id'),
                redirect_url=request.fallback_url,
                app_url=request.app_scheme,
                matched=True,
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