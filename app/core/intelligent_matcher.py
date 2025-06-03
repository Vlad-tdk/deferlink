"""
Intelligent fingerprint matching algorithm for production
Интеллектуальный алгоритм сопоставления отпечатков для продакшена
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Результат сопоставления"""
    is_match: bool
    confidence_score: float
    details: Dict[str, Any]
    session_id: Optional[str] = None


class IntelligentMatcher:
    """Продвинутый алгоритм сопоставления fingerprint'ов"""

    def __init__(self):
        # Динамические веса (могут обучаться)
        self.weights = {
            'timezone': 0.35,           # Высокая стабильность
            'screen_dimensions': 0.25,  # Точная характеристика
            'language': 0.20,          # Стабильный параметр
            'device_model': 0.15,      # Может варьироваться
            'user_agent_similarity': 0.05  # Низкая надежность
        }

        # Пороги уверенности
        self.confidence_thresholds = {
            'high': 0.85,      # Высокая уверенность
            'medium': 0.70,    # Средняя уверенность
            'low': 0.50        # Низкая уверенность
        }

        # Кэш для оптимизации
        self._device_similarity_cache: Dict[str, float] = {}
        self._timezone_cache: Dict[str, float] = {}

    def find_best_match(self, target_fingerprint: Dict[str, Any],
                       candidate_sessions: List[Dict[str, Any]]) -> MatchResult:
        """
        Поиск наилучшего совпадения среди кандидатов

        Args:
            target_fingerprint: Fingerprint из приложения
            candidate_sessions: Список сессий-кандидатов из браузера

        Returns:
            MatchResult с результатом сопоставления
        """
        if not candidate_sessions:
            return MatchResult(
                is_match=False,
                confidence_score=0.0,
                details={'reason': 'no_candidates'}
            )

        best_match = None
        best_score = 0.0
        best_details = {}

        for session in candidate_sessions:
            score, details = self._calculate_match_score(
                session, target_fingerprint
            )

            # Дополнительные проверки
            temporal_score = self._validate_temporal_patterns(session, target_fingerprint)
            final_score = score * temporal_score

            if final_score > best_score:
                best_score = final_score
                best_match = session
                best_details = {
                    **details,
                    'temporal_score': temporal_score,
                    'final_score': final_score
                }

        # Определение результата на основе лучшего score
        threshold = self._get_dynamic_threshold(target_fingerprint)
        is_match = best_score >= threshold

        return MatchResult(
            is_match=is_match,
            confidence_score=best_score,
            details=best_details,
            session_id=best_match['session_id'] if best_match else None
        )

    def _calculate_match_score(self, browser_session: Dict[str, Any],
                              app_fingerprint: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        """Расчет общего score сопоставления"""

        scores = {}
        details = {}

        # 1. Timezone similarity (высокий приоритет)
        tz_score = self._timezone_similarity(browser_session, app_fingerprint)
        scores['timezone'] = tz_score
        details['timezone_details'] = {
            'browser_tz': browser_session.get('timezone'),
            'app_tz': app_fingerprint.get('timezone'),
            'score': tz_score
        }

        # 2. Screen dimensions (точная характеристика)
        screen_score = self._screen_similarity(browser_session, app_fingerprint)
        scores['screen'] = screen_score
        details['screen_details'] = {
            'browser_screen': browser_session.get('screen_size'),
            'app_screen': app_fingerprint.get('screen_size'),
            'score': screen_score
        }

        # 3. Language matching
        lang_score = self._language_similarity(browser_session, app_fingerprint)
        scores['language'] = lang_score
        details['language_details'] = {
            'browser_lang': browser_session.get('language'),
            'app_lang': app_fingerprint.get('language'),
            'score': lang_score
        }

        # 4. Device model (с фаззи-логикой)
        device_score = self._device_similarity(browser_session, app_fingerprint)
        scores['device'] = device_score
        details['device_details'] = {
            'browser_model': browser_session.get('model'),
            'app_model': app_fingerprint.get('model'),
            'score': device_score
        }

        # 5. User agent similarity (низкий вес)
        ua_score = self._user_agent_similarity(browser_session, app_fingerprint)
        scores['user_agent'] = ua_score

        # Weighted average
        total_score = 0.0
        total_weight = 0.0

        for param, score in scores.items():
            weight_key = self._map_score_key_to_weight(param)
            if weight_key in self.weights:
                total_score += score * self.weights[weight_key]
                total_weight += self.weights[weight_key]

        final_score = total_score / total_weight if total_weight > 0 else 0.0

        details['component_scores'] = scores
        details['weights_used'] = self.weights
        details['weighted_score'] = final_score

        return final_score, details

    def _map_score_key_to_weight(self, score_key: str) -> str:
        """Маппинг ключей score к ключам весов"""
        mapping = {
            'timezone': 'timezone',
            'screen': 'screen_dimensions',
            'language': 'language',
            'device': 'device_model',
            'user_agent': 'user_agent_similarity'
        }
        return mapping.get(score_key, score_key)

    def _timezone_similarity(self, browser_session: Dict[str, Any],
                            app_fingerprint: Dict[str, Any]) -> float:
        """Интеллектуальное сравнение часовых поясов"""
        browser_tz = browser_session.get('timezone')
        app_tz = app_fingerprint.get('timezone')

        # Кэширование для производительности
        cache_key = f"{browser_tz}:{app_tz}"
        if cache_key in self._timezone_cache:
            return self._timezone_cache[cache_key]

        if not browser_tz or not app_tz:
            result = 0.5  # Нейтральная оценка
            self._timezone_cache[cache_key] = result
            return result

        # Точное совпадение
        if browser_tz == app_tz:
            self._timezone_cache[cache_key] = 1.0
            return 1.0

        # Эквивалентные зоны
        equivalent_zones = {
            'Europe/Moscow': ['Europe/Volgograd', 'Europe/Kirov', 'Europe/Simferopol'],
            'America/New_York': ['America/Detroit', 'America/Kentucky/Louisville', 'America/Montreal'],
            'Europe/London': ['Europe/Belfast', 'Europe/Guernsey', 'Europe/Jersey'],
            'Asia/Shanghai': ['Asia/Chongqing', 'Asia/Harbin', 'Asia/Kashgar'],
            'America/Los_Angeles': ['America/Vancouver', 'America/Tijuana'],
        }

        for primary, equivalents in equivalent_zones.items():
            if (browser_tz == primary and app_tz in equivalents) or \
               (app_tz == primary and browser_tz in equivalents):
                self._timezone_cache[cache_key] = 0.95
                return 0.95

        # Проверка UTC offset
        utc_offset_map = {
            'UTC': 0, 'Europe/London': 0, 'Europe/Moscow': 3,
            'America/New_York': -5, 'America/Los_Angeles': -8,
            'Asia/Tokyo': 9, 'Asia/Shanghai': 8
        }

        browser_offset = utc_offset_map.get(browser_tz)
        app_offset = utc_offset_map.get(app_tz)

        if browser_offset is not None and app_offset is not None:
            if browser_offset == app_offset:
                self._timezone_cache[cache_key] = 0.8
                return 0.8

        # Разные часовые пояса
        self._timezone_cache[cache_key] = 0.0
        return 0.0

    def _screen_similarity(self, browser_session: Dict[str, Any],
                          app_fingerprint: Dict[str, Any]) -> float:
        """Умное сравнение размеров экрана с учетом системных элементов"""
        browser_screen = browser_session.get('screen_size')
        app_screen = app_fingerprint.get('screen_size')

        if not browser_screen or not app_screen:
            return 0.3

        def parse_screen(screen_str):
            """Парсинг строки размера экрана"""
            try:
                # Поддерживаем форматы: "390x844", "390*844", "390,844"
                screen_str = str(screen_str).replace('x', '*').replace(',', '*')
                parts = screen_str.split('*')
                return int(parts[0]), int(parts[1])
            except (ValueError, IndexError):
                return None, None

        browser_w, browser_h = parse_screen(browser_screen)
        app_w, app_h = parse_screen(app_screen)

        if not all([browser_w, browser_h, app_w, app_h]):
            return 0.3

        # Точное совпадение (включая поворот экрана)
        if (browser_w == app_w and browser_h == app_h) or \
           (browser_w == app_h and browser_h == app_w):
            return 1.0

        # Допуски для системных элементов
        def within_tolerance(w1, h1, w2, h2, tolerance):
            """Проверка попадания в допуск с учетом поворота"""
            return (abs(w1 - w2) <= tolerance and abs(h1 - h2) <= tolerance) or \
                   (abs(w1 - h2) <= tolerance and abs(h1 - w2) <= tolerance)

        # Высокоточное совпадение (iOS с системными элементами)
        if within_tolerance(browser_w, browser_h, app_w, app_h, 60):
            return 0.95

        # Среднее совпадение (Android или старые iOS)
        if within_tolerance(browser_w, browser_h, app_w, app_h, 100):
            return 0.85

        # Проверка соотношения сторон (aspect ratio)
        def get_aspect_ratio(w, h):
            return max(w, h) / min(w, h) if min(w, h) > 0 else 0

        browser_ratio = get_aspect_ratio(browser_w, browser_h)
        app_ratio = get_aspect_ratio(app_w, app_h)

        if browser_ratio > 0 and app_ratio > 0:
            ratio_diff = abs(browser_ratio - app_ratio)

            if ratio_diff < 0.05:  # Очень похожее соотношение
                return 0.7
            elif ratio_diff < 0.15:  # Похожее соотношение
                return 0.5

        return 0.0

    def _language_similarity(self, browser_session: Dict[str, Any],
                           app_fingerprint: Dict[str, Any]) -> float:
        """Умное сравнение языковых настроек"""
        browser_lang = str(browser_session.get('language', '')).lower()
        app_lang = str(app_fingerprint.get('language', '')).lower()

        if not browser_lang or not app_lang:
            return 0.4

        # Точное совпадение
        if browser_lang == app_lang:
            return 1.0

        # Нормализация языковых кодов
        def normalize_language(lang):
            """Приведение к стандартному формату"""
            lang = lang.replace('-', '_').lower()

            # Маппинг распространенных вариантов
            mappings = {
                'en': 'en_us', 'ru': 'ru_ru', 'de': 'de_de',
                'fr': 'fr_fr', 'es': 'es_es', 'it': 'it_it',
                'ja': 'ja_jp', 'ko': 'ko_kr', 'zh': 'zh_cn'
            }

            if lang in mappings:
                return mappings[lang]

            return lang

        norm_browser = normalize_language(browser_lang)
        norm_app = normalize_language(app_lang)

        if norm_browser == norm_app:
            return 0.95

        # Проверка совпадения основного языка (до '_')
        browser_main = norm_browser.split('_')[0]
        app_main = norm_app.split('_')[0]

        if browser_main == app_main:
            return 0.8  # Тот же язык, разные локали

        # Проверка родственных языков
        related_languages = {
            'en': ['en_us', 'en_gb', 'en_au', 'en_ca'],
            'es': ['es_es', 'es_mx', 'es_ar', 'es_co'],
            'fr': ['fr_fr', 'fr_ca', 'fr_be', 'fr_ch'],
            'de': ['de_de', 'de_at', 'de_ch'],
            'pt': ['pt_pt', 'pt_br'],
            'zh': ['zh_cn', 'zh_tw', 'zh_hk']
        }

        for main_lang, variants in related_languages.items():
            if norm_browser in variants and norm_app in variants:
                return 0.7

        return 0.0

    def _device_similarity(self, browser_session: Dict[str, Any],
                          app_fingerprint: Dict[str, Any]) -> float:
        """Фаззи-сравнение моделей устройств с кэшированием"""
        browser_model = str(browser_session.get('model', '')).lower().strip()
        app_model = str(app_fingerprint.get('model', '')).lower().strip()

        # Кэширование для производительности
        cache_key = f"{browser_model}:{app_model}"
        if cache_key in self._device_similarity_cache:
            return self._device_similarity_cache[cache_key]

        if not browser_model or not app_model:
            result = 0.4
            self._device_similarity_cache[cache_key] = result
            return result

        # Точное совпадение
        if browser_model == app_model:
            self._device_similarity_cache[cache_key] = 1.0
            return 1.0

        # Расширенные маппинги устройств
        device_mappings = {
            # iPhone модели
            'iphone14,2': ['iphone 13 pro', 'iphone13,2', 'a2638', 'a2639'],
            'iphone14,3': ['iphone 13 pro max', 'iphone13,3', 'a2644', 'a2645'],
            'iphone13,2': ['iphone 12', 'iphone12,1', 'a2172', 'a2402'],
            'iphone13,3': ['iphone 12 pro max', 'iphone12,5', 'a2342', 'a2410'],

            # Samsung Galaxy
            'sm-g998b': ['galaxy s21 ultra', 'samsung galaxy s21 ultra', 'sm-g998u'],
            'sm-g991b': ['galaxy s21', 'samsung galaxy s21', 'sm-g991u'],
            'sm-g996b': ['galaxy s21+', 'samsung galaxy s21+', 'sm-g996u'],

            # Google Pixel
            'pixel 6': ['pixel 6a', 'google pixel 6', 'gf5kq', 'gb7n6'],
            'pixel 7': ['pixel 7a', 'google pixel 7', 'gvt4a', 'gp4bc'],

            # OnePlus
            'oneplus 9': ['1+9', 'op9', 'le2113', 'le2115'],
            'oneplus 10': ['1+10', 'op10', 'ne2210', 'ne2215'],
        }

        # Поиск в маппингах
        for canonical, variants in device_mappings.items():
            if browser_model == canonical and app_model in variants:
                self._device_similarity_cache[cache_key] = 0.95
                return 0.95
            if app_model == canonical and browser_model in variants:
                self._device_similarity_cache[cache_key] = 0.95
                return 0.95
            if browser_model in variants and app_model in variants:
                self._device_similarity_cache[cache_key] = 0.9
                return 0.9

        # Текстовое сходство с улучшенным алгоритмом
        similarity = self._advanced_string_similarity(browser_model, app_model)

        if similarity > 0.85:
            result = 0.8
        elif similarity > 0.70:
            result = 0.6
        elif similarity > 0.50:
            result = 0.4
        else:
            result = 0.0

        self._device_similarity_cache[cache_key] = result
        return result

    def _advanced_string_similarity(self, s1: str, s2: str) -> float:
        """Улучшенный алгоритм сходства строк"""
        if not s1 or not s2:
            return 0.0

        # Предобработка строк
        def preprocess(s):
            # Удаление пунктуации и нормализация
            s = re.sub(r'[^\w\s]', '', s.lower())
            # Удаление распространенных слов
            stop_words = ['samsung', 'apple', 'google', 'oneplus', 'xiaomi']
            words = [w for w in s.split() if w not in stop_words]
            return ' '.join(words)

        clean_s1 = preprocess(s1)
        clean_s2 = preprocess(s2)

        # Jaccard similarity для слов
        words1 = set(clean_s1.split())
        words2 = set(clean_s2.split())

        if not words1 and not words2:
            return 1.0 if s1 == s2 else 0.0

        intersection = words1 & words2
        union = words1 | words2

        jaccard = len(intersection) / len(union) if union else 0.0

        # Символьное сходство
        char_similarity = self._char_similarity(clean_s1, clean_s2)

        # Комбинированная оценка
        return (jaccard * 0.7 + char_similarity * 0.3)

    def _char_similarity(self, s1: str, s2: str) -> float:
        """Сходство на уровне символов"""
        if not s1 or not s2:
            return 0.0

        # Множества символов
        chars1 = set(s1.lower())
        chars2 = set(s2.lower())

        intersection = chars1 & chars2
        union = chars1 | chars2

        return len(intersection) / len(union) if union else 0.0

    def _user_agent_similarity(self, browser_session: Dict[str, Any],
                              app_fingerprint: Dict[str, Any]) -> float:
        """Сравнение User-Agent с учетом различий между браузером и приложением"""
        browser_ua = str(browser_session.get('user_agent', '')).lower()
        app_ua = str(app_fingerprint.get('user_agent', '')).lower()

        if not browser_ua or not app_ua:
            return 0.3

        # Извлечение ключевых компонентов
        def extract_ua_components(ua: str) -> Tuple[Dict[str, bool], Dict[str, str]]:
            """Извлечение компонентов User-Agent"""
            # Булевые флаги
            bool_flags = {
                'webkit': 'webkit' in ua,
                'mobile': 'mobile' in ua,
                'iphone': 'iphone' in ua,
                'android': 'android' in ua,
                'safari': 'safari' in ua,
                'chrome': 'chrome' in ua,
            }

            # Строковые версии
            versions = {}

            # Извлечение версий iOS/Android
            ios_match = re.search(r'os (\d+)[_.](\d+)', ua)
            if ios_match:
                versions['ios_version'] = f"{ios_match.group(1)}.{ios_match.group(2)}"

            android_match = re.search(r'android (\d+)[._](\d+)', ua)
            if android_match:
                versions['android_version'] = f"{android_match.group(1)}.{android_match.group(2)}"

            return bool_flags, versions

        browser_bool, browser_versions = extract_ua_components(browser_ua)
        app_bool, app_versions = extract_ua_components(app_ua)

        # Подсчет совпадений булевых флагов
        bool_matches = 0
        bool_total = 0

        for key in browser_bool:
            if key in app_bool:
                bool_total += 1
                if browser_bool[key] == app_bool[key]:
                    bool_matches += 1

        # Подсчет совпадений версий
        version_matches = 0
        version_total = 0

        for key in browser_versions:
            if key in app_versions:
                version_total += 1
                if browser_versions[key] == app_versions[key]:
                    version_matches += 1

        # Общий результат
        total_matches = bool_matches + version_matches
        total_comparisons = bool_total + version_total

        return total_matches / total_comparisons if total_comparisons > 0 else 0.3

    def _validate_temporal_patterns(self, browser_session: Dict[str, Any],
                                   app_fingerprint: Dict[str, Any]) -> float:
        """Валидация временных паттернов"""
        try:
            # Получение времени создания сессии
            created_at_str = browser_session.get('created_at')
            if not created_at_str:
                return 0.8  # Нейтральная оценка если нет данных

            # Парсинг времени (поддержка разных форматов)
            try:
                if 'T' in str(created_at_str):
                    created_at = datetime.fromisoformat(str(created_at_str).replace('Z', '+00:00'))
                else:
                    created_at = datetime.strptime(str(created_at_str), '%Y-%m-%d %H:%M:%S')
            except:
                return 0.8

            # Текущее время (время resolve)
            current_time = datetime.now()
            time_diff = (current_time - created_at).total_seconds()

            # Анализ временных паттернов
            if time_diff < 10:  # Слишком быстро (< 10 сек)
                return 0.2
            elif time_diff < 30:  # Очень быстро (10-30 сек)
                return 0.6
            elif 30 <= time_diff <= 600:  # Оптимальное время (30 сек - 10 мин)
                return 1.0
            elif 600 < time_diff <= 3600:  # Нормальное время (10-60 мин)
                return 0.9
            elif 3600 < time_diff <= 14400:  # Долго (1-4 часа)
                return 0.7
            elif 14400 < time_diff <= 86400:  # Очень долго (4-24 часа)
                return 0.4
            else:  # Подозрительно долго (> 24 часов)
                return 0.1

        except Exception as e:
            logger.warning(f"Error validating temporal patterns: {e}")
            return 0.8

    def _get_dynamic_threshold(self, app_fingerprint: Dict[str, Any]) -> float:
        """Получение динамического порога на основе контекста"""
        base_threshold = self.confidence_thresholds['medium']  # 0.70

        # Корректировки на основе времени
        current_hour = datetime.now().hour
        if 9 <= current_hour <= 21:  # Рабочие часы - более строго
            base_threshold += 0.05
        else:  # Нерабочие часы - более мягко
            base_threshold -= 0.05

        # Корректировка на основе качества fingerprint
        fingerprint_quality = self._assess_fingerprint_quality(app_fingerprint)

        if fingerprint_quality > 0.8:  # Высокое качество - можем быть мягче
            base_threshold -= 0.05
        elif fingerprint_quality < 0.4:  # Низкое качество - нужно быть строже
            base_threshold += 0.10

        # Ограничиваем в разумных пределах
        return max(0.50, min(0.90, base_threshold))

    def _assess_fingerprint_quality(self, fingerprint: Dict[str, Any]) -> float:
        """Оценка качества fingerprint (количество и надежность параметров)"""
        quality_score = 0.0
        max_score = 0.0

        # Высоконадежные параметры
        high_quality_params = {
            'timezone': 0.3,
            'screen_size': 0.25,
            'language': 0.2
        }

        # Средненадежные параметры
        medium_quality_params = {
            'model': 0.15,
            'user_agent': 0.1
        }

        for param, weight in high_quality_params.items():
            max_score += weight
            if fingerprint.get(param):
                quality_score += weight

        for param, weight in medium_quality_params.items():
            max_score += weight
            if fingerprint.get(param):
                quality_score += weight

        return quality_score / max_score if max_score > 0 else 0.0

    def update_weights(self, new_weights: Dict[str, float]) -> None:
        """Обновление весов алгоритма (для машинного обучения)"""
        # Валидация новых весов
        total_weight = sum(new_weights.values())
        if abs(total_weight - 1.0) > 0.01:
            logger.warning("New weights don't sum to 1.0, normalizing...")
            new_weights = {k: v/total_weight for k, v in new_weights.items()}

        self.weights.update(new_weights)
        logger.info(f"Updated matching weights: {self.weights}")

    def clear_cache(self) -> None:
        """Очистка кэшей (для освобождения памяти)"""
        self._device_similarity_cache.clear()
        self._timezone_cache.clear()
        logger.info("Matching algorithm caches cleared")