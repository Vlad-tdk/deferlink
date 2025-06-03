"""
Core Package - Intelligent matching algorithms
Основные алгоритмы интеллектуального сопоставления
"""

try:
    from .intelligent_matcher import IntelligentMatcher, MatchResult
    INTELLIGENT_MATCHER_AVAILABLE = True
except ImportError:
    # Graceful fallback если модуль недоступен
    INTELLIGENT_MATCHER_AVAILABLE = False
    IntelligentMatcher = None
    MatchResult = None

# Экспорт основных компонентов
__all__ = [
    "IntelligentMatcher",
    "MatchResult",
    "INTELLIGENT_MATCHER_AVAILABLE",
]