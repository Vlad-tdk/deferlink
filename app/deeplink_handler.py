"""
Enhanced deep link handling logic with intelligent matching
Улучшенная логика обработки диплинков с интеллектуальным сопоставлением
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from fastapi import HTTPException, status

from .config import Config
from .database import db_manager
from .models import ResolveRequest, FingerprintData, SessionData
from .core.intelligent_matcher import IntelligentMatcher, MatchResult

logger = logging.getLogger(__name__)


class DeepLinkHandler:
    """
    Улучшенный обработчик диплинков с интеллектуальным сопоставлением
    """

    def __init__(self):
        self.config = Config()
        self.intelligent_matcher = IntelligentMatcher()

        # Статистика для оптимизации
        self.stats = {
            'total_requests': 0,
            'successful_matches': 0,
            'failed_matches': 0,
            'average_confidence': 0.0
        }

        logger.info("DeepLink Handler инициализирован")

    def create_session(
        self,
        promo_id: str,
        domain: str,
        user_agent: str,
        timezone: Optional[str] = None,
        language: Optional[str] = None,
        screen_size: Optional[str] = None,
        model: Optional[str] = None,
        ttl_hours: Optional[int] = None,
        ip_address: Optional[str] = None
    ) -> str:
        """
        Создание новой браузерной сессии
        """
        try:
            session_id = str(uuid.uuid4())
            ttl_hours = ttl_hours or self.config.DEFAULT_TTL_HOURS

            # Вычисление времени истечения
            expires_at = datetime.now() + timedelta(hours=ttl_hours)

            query = """
                INSERT INTO deeplink_sessions
                (session_id, promo_id, domain, user_agent, timezone, language,
                 screen_size, model, expires_at, ip_address, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """

            params = (
                session_id, promo_id, domain, user_agent, timezone,
                language, screen_size, model, expires_at, ip_address
            )

            db_manager.execute_insert(query, params)

            logger.info(f"Создана новая сессия: {session_id}")

            # Логирование аналитики
            self._log_analytics_event("session_created", {
                'session_id': session_id,
                'promo_id': promo_id,
                'domain': domain,
                'user_agent': user_agent[:100] if user_agent else None,
                'ip_address': ip_address,
            })

            return session_id

        except Exception as e:
            logger.error(f"Ошибка создания сессии: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось создать сессию"
            )

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Получение сессии по ID"""
        try:
            query = """
                SELECT * FROM deeplink_sessions
                WHERE session_id = ? AND expires_at > CURRENT_TIMESTAMP
            """
            results = db_manager.execute_query(query, (session_id,))
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Ошибка получения сессии {session_id}: {e}")
            return None

    def find_matching_session(self, fingerprint: FingerprintData) -> Optional[Dict[str, Any]]:
        """
        Поиск подходящей браузерной сессии с использованием ИИ алгоритма
        """
        try:
            self.stats['total_requests'] += 1

            # Получение кандидатов из базы данных
            query = """
                SELECT session_id, promo_id, domain, created_at, user_agent,
                       timezone, language, screen_size, model, ip_address,
                       match_confidence, match_details
                FROM deeplink_sessions
                WHERE expires_at > CURRENT_TIMESTAMP
                AND is_resolved = FALSE
                ORDER BY created_at DESC
                LIMIT 50
            """

            candidates = db_manager.execute_query(query)

            if not candidates:
                logger.info("Нет кандидатов для сопоставления")
                self.stats['failed_matches'] += 1
                return None

            # Нормализация fingerprint для передачи в matcher
            app_fingerprint = self._normalize_fingerprint(fingerprint)

            # Использование ИИ алгоритма для поиска лучшего совпадения
            match_result = self.intelligent_matcher.find_best_match(app_fingerprint, candidates)

            # Логирование результата сопоставления
            logger.info(f"Результат ИИ сопоставления: match={match_result.is_match}, "
                       f"confidence={match_result.confidence_score:.3f}, "
                       f"session_id={match_result.session_id}")

            if match_result.is_match and match_result.session_id:
                # Обновление статистики
                self.stats['successful_matches'] += 1
                self._update_average_confidence(match_result.confidence_score)

                # Поиск полной информации о сессии
                session = next((s for s in candidates if s['session_id'] == match_result.session_id), None)
                if session:
                    session['match_confidence'] = match_result.confidence_score
                    session['match_details'] = match_result.details
                    return session

            self.stats['failed_matches'] += 1
            return None

        except Exception as e:
            logger.error(f"Критическая ошибка при поиске сессии: {e}")
            self.stats['failed_matches'] += 1
            return None

    def mark_session_resolved(
        self,
        session_id: str,
        confidence_score: Optional[float] = None,
        match_details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Отметка сессии как разрешенной"""
        try:
            match_details_json = json.dumps(match_details) if match_details else None

            query = """
                UPDATE deeplink_sessions
                SET is_resolved = TRUE,
                    resolved_at = CURRENT_TIMESTAMP,
                    match_confidence = ?,
                    match_details = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ?
            """

            rows_affected = db_manager.execute_update(
                query, (confidence_score, match_details_json, session_id)
            )

            if rows_affected > 0:
                logger.info(f"Сессия {session_id} отмечена как разрешенная")
                self._log_analytics_event("session_resolved", {
                    'session_id': session_id,
                    'confidence_score': confidence_score
                })
                return True

            return False

        except Exception as e:
            logger.error(f"Ошибка отметки сессии как разрешенной: {e}")
            return False

    def cleanup_expired_sessions(self) -> int:
        """Очистка истекших сессий"""
        try:
            query = "DELETE FROM deeplink_sessions WHERE expires_at <= CURRENT_TIMESTAMP"
            deleted_count = db_manager.execute_update(query)

            if deleted_count > 0:
                logger.info(f"Удалено {deleted_count} истекших сессий")

            return deleted_count

        except Exception as e:
            logger.error(f"Ошибка очистки истекших сессий: {e}")
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """
        Получение статистики работы системы
        """
        try:
            # Общая статистика из БД
            query_total = "SELECT COUNT(*) as count FROM deeplink_sessions"
            total_result = db_manager.execute_query(query_total)
            total_sessions = total_result[0]['count'] if total_result else 0

            query_resolved = "SELECT COUNT(*) as count FROM deeplink_sessions WHERE is_resolved = TRUE"
            resolved_result = db_manager.execute_query(query_resolved)
            resolved_sessions = resolved_result[0]['count'] if resolved_result else 0

            query_active = """
                SELECT COUNT(*) as count FROM deeplink_sessions
                WHERE expires_at > CURRENT_TIMESTAMP AND is_resolved = FALSE
            """
            active_result = db_manager.execute_query(query_active)
            active_sessions = active_result[0]['count'] if active_result else 0

            # Средняя уверенность
            query_confidence = """
                SELECT AVG(match_confidence) as avg_confidence
                FROM deeplink_sessions
                WHERE match_confidence IS NOT NULL
            """
            confidence_result = db_manager.execute_query(query_confidence)
            avg_confidence = confidence_result[0]['avg_confidence'] if confidence_result else 0.0

            # Статистика за последний час
            query_last_hour = """
                SELECT COUNT(*) as count FROM deeplink_sessions
                WHERE created_at >= datetime('now', '-1 hour')
            """
            last_hour_result = db_manager.execute_query(query_last_hour)
            sessions_last_hour = last_hour_result[0]['count'] if last_hour_result else 0

            success_rate = (resolved_sessions / total_sessions * 100) if total_sessions > 0 else 0.0

            return {
                'total_sessions': total_sessions,
                'resolved_sessions': resolved_sessions,
                'active_sessions': active_sessions,
                'success_rate': success_rate,
                'sessions_last_hour': sessions_last_hour,
                'average_confidence': float(avg_confidence or 0.0),
                'matcher_stats': self.stats,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {
                'error': 'Не удалось получить статистику',
                'matcher_stats': self.stats,
                'timestamp': datetime.now().isoformat()
            }

    def optimize_algorithm_weights(self) -> Dict[str, float]:
        """Автоматическая оптимизация весов алгоритма на основе истории"""
        try:
            # Получение статистики успешных сопоставлений
            query = """
                SELECT match_details, match_confidence
                FROM deeplink_sessions
                WHERE is_resolved = TRUE
                AND match_details IS NOT NULL
                AND match_confidence > 0.7
                ORDER BY resolved_at DESC
                LIMIT 1000
            """

            results = db_manager.execute_query(query)

            if len(results) < 10:  # Недостаточно данных для оптимизации
                logger.info("Недостаточно данных для оптимизации весов")
                return self.intelligent_matcher.weights

            # Анализ компонентных scores для оптимизации весов
            component_performance = {}
            total_samples = 0

            for result in results:
                try:
                    details = json.loads(result['match_details'])
                    component_scores = details.get('component_scores', {})
                    confidence = result['match_confidence']

                    for component, score in component_scores.items():
                        if component not in component_performance:
                            component_performance[component] = {'total_score': 0, 'count': 0}

                        # Взвешиваем по итоговой уверенности
                        component_performance[component]['total_score'] += score * confidence
                        component_performance[component]['count'] += 1

                    total_samples += 1

                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Ошибка парсинга match_details: {e}")
                    continue

            # Вычисление новых весов на основе производительности компонентов
            new_weights = {}
            total_performance = 0

            for component, perf in component_performance.items():
                if perf['count'] > 0:
                    avg_performance = perf['total_score'] / perf['count']
                    weight_key = self.intelligent_matcher._map_score_key_to_weight(component)
                    if weight_key in self.intelligent_matcher.weights:
                        new_weights[weight_key] = avg_performance
                        total_performance += avg_performance

            # Нормализация весов
            if total_performance > 0:
                for key in new_weights:
                    new_weights[key] = new_weights[key] / total_performance

                # Применение новых весов с сглаживанием (80% старые, 20% новые)
                optimized_weights = {}
                for key, old_weight in self.intelligent_matcher.weights.items():
                    if key in new_weights:
                        optimized_weights[key] = 0.8 * old_weight + 0.2 * new_weights[key]
                    else:
                        optimized_weights[key] = old_weight

                self.intelligent_matcher.update_weights(optimized_weights)
                logger.info(f"Веса алгоритма оптимизированы на основе {total_samples} образцов")

                return optimized_weights

            return self.intelligent_matcher.weights

        except Exception as e:
            logger.error(f"Ошибка оптимизации весов алгоритма: {e}")
            return self.intelligent_matcher.weights

    def detect_potential_fraud(self, fingerprint_dict: Dict[str, Any], ip_address: str) -> Dict[str, Any]:
        """Детекция потенциального фрода (базовая реализация)"""
        try:
            risk_score = 0.0
            risk_factors = []
            recommendations = []

            # Проверка на слишком частые запросы с одного IP
            query = """
                SELECT COUNT(*) as count FROM deeplink_sessions
                WHERE ip_address = ? AND created_at >= datetime('now', '-1 hour')
            """
            ip_results = db_manager.execute_query(query, (ip_address,))
            ip_count = ip_results[0]['count'] if ip_results else 0

            if ip_count > 50:
                risk_score += 0.3
                risk_factors.append(f"Слишком много запросов с IP {ip_address} за час: {ip_count}")

            if ip_count > 100:
                risk_score += 0.5
                recommendations.append("block_request")

            # Проверка на подозрительные fingerprint
            user_agent = fingerprint_dict.get('user_agent', '')
            if not user_agent or len(user_agent) < 50:
                risk_score += 0.2
                risk_factors.append("Подозрительно короткий User-Agent")

            # Проверка на отсутствие ключевых параметров
            required_params = ['timezone', 'language', 'model']
            missing_params = [p for p in required_params if not fingerprint_dict.get(p)]

            if len(missing_params) >= 2:
                risk_score += 0.3
                risk_factors.append(f"Отсутствуют ключевые параметры: {missing_params}")

            return {
                'risk_score': min(risk_score, 1.0),
                'risk_factors': risk_factors,
                'recommendations': recommendations,
                'ip_requests_last_hour': ip_count
            }

        except Exception as e:
            logger.error(f"Ошибка детекции фрода: {e}")
            return {'risk_score': 0.0, 'risk_factors': [], 'recommendations': []}

    def _normalize_fingerprint(self, fingerprint: FingerprintData) -> Dict[str, Any]:
        """
        Нормализация fingerprint для передачи в IntelligentMatcher
        """
        try:
            # Формирование screen_size из width/height или использование существующего
            screen_size = fingerprint.screen_size
            if not screen_size and fingerprint.screen_width and fingerprint.screen_height:
                screen_size = f"{fingerprint.screen_width}x{fingerprint.screen_height}"

            # Стандартизированный формат для ИИ алгоритма
            normalized = {
                'timezone': fingerprint.timezone or '',
                'screen_size': screen_size or '',
                'language': fingerprint.language or '',
                'model': fingerprint.device_model or '',
                'user_agent': fingerprint.user_agent or '',
                'platform': fingerprint.platform or '',
                'version': fingerprint.app_version or '',
            }

            # Валидация и очистка данных
            for key, value in normalized.items():
                if not isinstance(value, str):
                    normalized[key] = str(value) if value is not None else ''

            return normalized

        except Exception as e:
            logger.warning(f"Ошибка нормализации fingerprint: {e}")
            return {
                'timezone': '',
                'screen_size': '',
                'language': '',
                'model': '',
                'user_agent': '',
                'platform': '',
                'version': '',
            }

    def _log_analytics_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Логирование аналитических событий
        """
        try:
            if not self.config.ENABLE_ANALYTICS:
                return

            # Вставка в таблицу аналитики
            query = """
                INSERT INTO analytics_events (session_id, event_type, metadata, timestamp)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """

            session_id = data.get('session_id')
            metadata = json.dumps(data)

            db_manager.execute_insert(query, (session_id, event_type, metadata))

        except Exception as e:
            logger.warning(f"Ошибка логирования аналитики: {e}")

    def _update_average_confidence(self, new_confidence: float) -> None:
        """Обновление скользящего среднего уверенности"""
        try:
            current_avg = self.stats['average_confidence']
            total_requests = self.stats['total_requests']

            if total_requests > 1:
                # Скользящее среднее
                self.stats['average_confidence'] = (
                    (current_avg * (total_requests - 1) + new_confidence) / total_requests
                )
            else:
                self.stats['average_confidence'] = new_confidence

        except Exception as e:
            logger.warning(f"Ошибка обновления средней уверенности: {e}")


# Глобальный экземпляр обработчика (будет использоваться в main.py)
deeplink_handler = DeepLinkHandler()