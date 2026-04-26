"""
Apple DeviceCheck — серверная верификация
Apple DeviceCheck server-side verification

Документация Apple:
  https://developer.apple.com/documentation/devicecheck

Что даёт DeviceCheck:
  - Токен уникален для конкретного устройства + вашего Team ID
  - Не требует ATT / IDFA
  - Недоступен в WKWebView — только в нативном Swift через DCDevice.current.generateToken()
  - Серверная верификация подтверждает подлинность токена у Apple

Схема интеграции:
  1. Приложение: DCDevice.current.generateToken() → base64 токен
  2. Приложение: отправляет токен на наш сервер вместе с fingerprint
  3. Сервер: верифицирует токен у Apple (JWT-аутентификация)
  4. Сервер: матчит с существующей сессией (clipboard / fingerprint)
  5. Сервер: сохраняет хэш токена для повторных запусков

Требования для включения:
  - DEVICECHECK_TEAM_ID=<Apple Team ID>
  - DEVICECHECK_KEY_ID=<Key ID из Apple Developer>
  - DEVICECHECK_KEY_PATH=<путь до .p8 файла>
  - pip install PyJWT httpx

Без конфигурации модуль работает в "degraded mode":
  верификация пропускается, токен используется только как дополнительный
  сигнал для fingerprint matching.
"""

import hashlib
import logging
import time
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Опциональные зависимости
try:
    import jwt            # pip install PyJWT
    import httpx          # pip install httpx
    _DEPS_AVAILABLE = True
except ImportError:
    _DEPS_AVAILABLE = False
    logger.info(
        "DeviceCheck: PyJWT / httpx не установлены. "
        "Верификация токенов недоступна. "
        "Установите: pip install PyJWT httpx cryptography"
    )


@dataclass
class DeviceCheckResult:
    valid: bool
    status: str = "invalid"         # valid | invalid | indeterminate
    reason: str = ""
    is_new_device: bool = False     # Первый раз видим устройство
    bit0: bool = False              # Состояние бита 0 (можно использовать как флаг)
    bit1: bool = False              # Состояние бита 1
    last_update_time: Optional[str] = None


class DeviceCheckVerifier:
    """
    Верификация Apple DeviceCheck токенов.

    Использует Apple API для подтверждения что токен выдан реальным Apple устройством.
    Хранит хэш токена (никогда не сырой токен) для повторного распознавания.
    """

    _PROD_API = "https://api.devicecheck.apple.com/v1/validate_device_token"
    _DEV_API  = "https://api.development.devicecheck.apple.com/v1/validate_device_token"

    def __init__(
        self,
        team_id: Optional[str]       = None,
        key_id: Optional[str]        = None,
        private_key_path: Optional[str] = None,
        use_sandbox: bool            = False,
        request_timeout: float       = 5.0,
    ):
        self.team_id          = team_id
        self.key_id           = key_id
        self.private_key_path = private_key_path
        self.use_sandbox      = use_sandbox
        self.request_timeout  = request_timeout
        self._private_key: Optional[str] = None

        self.configured = bool(team_id and key_id and private_key_path and _DEPS_AVAILABLE)

        if self.configured and private_key_path:
            try:
                with open(private_key_path, "r") as f:
                    self._private_key = f.read()
                logger.info("DeviceCheck: приватный ключ загружен (%s)", private_key_path)
            except FileNotFoundError:
                logger.warning("DeviceCheck: файл ключа не найден: %s", private_key_path)
                self.configured = False
            except Exception as e:
                logger.warning("DeviceCheck: ошибка загрузки ключа: %s", e)
                self.configured = False

        if not self.configured:
            logger.info(
                "DeviceCheck: работает в degraded mode "
                "(токены принимаются как сигнал, верификация Apple API отключена)"
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    async def verify(self, device_token_b64: str) -> DeviceCheckResult:
        """
        Верифицировать DeviceCheck токен.

        Args:
            device_token_b64: base64-encoded токен от DCDevice.current.generateToken()

        Returns:
            DeviceCheckResult — результат верификации
        """
        if not device_token_b64:
            return DeviceCheckResult(valid=False, status="invalid", reason="empty_token")

        if not self.configured:
            logger.info("DeviceCheck degraded: токен не верифицируется, сигнал понижен в доверии")
            return DeviceCheckResult(valid=False, status="indeterminate", reason="degraded_mode")

        try:
            developer_jwt = self._build_developer_jwt()
            api_url = self._DEV_API if self.use_sandbox else self._PROD_API

            payload = {
                "device_token": device_token_b64,
                "transaction_id": self._make_transaction_id(device_token_b64),
                "timestamp": int(time.time() * 1000),
            }

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    api_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {developer_jwt}",
                        "Content-Type": "application/json",
                    },
                    timeout=self.request_timeout,
                )

            # 200 OK — токен валидный, у устройства есть данные
            if resp.status_code == 200:
                data = resp.json()
                return DeviceCheckResult(
                    valid=True,
                    status="valid",
                    bit0=data.get("bit0", False),
                    bit1=data.get("bit1", False),
                    last_update_time=data.get("last_update_time"),
                    is_new_device=("bit0" not in data and "bit1" not in data),
                )

            # 400 — невалидный токен (или истёк)
            if resp.status_code == 400:
                return DeviceCheckResult(
                    valid=False,
                    status="invalid",
                    reason=f"apple_rejected: {resp.text[:120]}"
                )

            logger.warning("DeviceCheck API вернул %s: %s", resp.status_code, resp.text[:200])
            return DeviceCheckResult(
                valid=False,
                status="indeterminate",
                reason=f"api_error_{resp.status_code}"
            )

        except httpx.TimeoutException:
            logger.warning("DeviceCheck: таймаут запроса к Apple API")
            return DeviceCheckResult(valid=False, status="indeterminate", reason="timeout")

        except Exception as e:
            logger.error("DeviceCheck: неожиданная ошибка: %s", e)
            return DeviceCheckResult(valid=False, status="indeterminate", reason=f"error: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Утилиты
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def hash_token(device_token_b64: str) -> str:
        """
        Хэшировать токен для хранения в БД.
        Никогда не храним сырой токен — только SHA-256.
        """
        return hashlib.sha256(device_token_b64.encode()).hexdigest()

    def _build_developer_jwt(self) -> str:
        """Создать JWT для авторизации в Apple DeviceCheck API."""
        if not _DEPS_AVAILABLE:
            raise RuntimeError("PyJWT не установлен")

        return jwt.encode(
            payload={"iss": self.team_id, "iat": int(time.time())},
            key=self._private_key,
            algorithm="ES256",
            headers={"kid": self.key_id},
        )

    @staticmethod
    def _make_transaction_id(token: str) -> str:
        """Уникальный transaction_id для каждого запроса к Apple API."""
        return hashlib.sha256(
            f"{token}{time.time()}".encode()
        ).hexdigest()[:32]


# ──────────────────────────────────────────────────────────────────────────────
# Singleton — создаётся из Config при старте приложения
# ──────────────────────────────────────────────────────────────────────────────

_verifier: Optional[DeviceCheckVerifier] = None


def get_verifier() -> DeviceCheckVerifier:
    """Получить глобальный экземпляр верификатора."""
    global _verifier
    if _verifier is None:
        _verifier = DeviceCheckVerifier()
    return _verifier


def init_verifier(
    team_id: Optional[str],
    key_id: Optional[str],
    private_key_path: Optional[str],
    use_sandbox: bool = False,
) -> DeviceCheckVerifier:
    """Инициализировать верификатор с конфигурацией."""
    global _verifier
    _verifier = DeviceCheckVerifier(
        team_id=team_id,
        key_id=key_id,
        private_key_path=private_key_path,
        use_sandbox=use_sandbox,
    )
    return _verifier
