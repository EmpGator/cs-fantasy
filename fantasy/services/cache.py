"""
Caching utilities for external API responses.

Provides smart caching with dynamic TTL based on module state,
minimizing requests to external sources while keeping data fresh.
"""
from django.core.cache import caches
from django.utils import timezone
import hashlib
import json
import logging

logger = logging.getLogger(__name__)


class ResponseCache:
    """
    Smart caching for API responses with dynamic TTL based on module state.

    Features:
    - Dynamic TTL based on module completion status
    - Deterministic cache key generation
    - Pattern-based invalidation (Redis)
    - Cache statistics logging
    """

    def __init__(self, cache_name='default'):
        """
        Initialize cache.

        Args:
            cache_name: Name of cache backend from settings.CACHES
        """
        self.cache = caches[cache_name]
        self.cache_name = cache_name

    def get_cache_key(self, source, identifier, **kwargs):
        """
        Generate deterministic cache key from source and identifier.

        Args:
            source: API source (e.g., 'hltv', 'liquipedia')
            identifier: Unique identifier (tournament_id, stat_type, etc.)
            **kwargs: Additional parameters to include in key

        Returns:
            str: Cache key in format 'source:identifier:hash'

        Examples:
            get_cache_key('hltv', 'tournament_1234')
            # Returns: 'hltv:tournament_1234:abc123...'

            get_cache_key('hltv', 'stats', stat_type='mvp', tournament_id=1234)
            # Returns: 'hltv:stats:def456...'
        """
        key_data = {
            'source': source,
            'identifier': identifier,
            **kwargs
        }

        key_string = json.dumps(key_data, sort_keys=True)
        key_hash = hashlib.md5(key_string.encode()).hexdigest()[:12]

        return f"{source}:{identifier}:{key_hash}"

    def get_ttl(self, module=None):
        """
        Calculate dynamic TTL based on module state.

        Strategy:
        - Finalized modules: 1 year (results never change)
        - Recently ended (<1h): 5 minutes (corrections happen)
        - Recently ended (<1d): 30 minutes (still updating)
        - Recently ended (1d+): 1 hour (stable)
        - Ongoing/future: 10 minutes (active updates)

        Args:
            module: Module instance (optional)

        Returns:
            int: TTL in seconds
        """
        if not module:
            return 3600  # 1 hour default

        now = timezone.now()

        if module.is_completed and module.finalized_at:
            return 60 * 60 * 24 * 365  # 1 year

        if module.end_date and module.end_date < now:
            time_since_end = (now - module.end_date).total_seconds()

            if time_since_end < 3600:  # < 1 hour
                return 300  # 5 minutes - frequent updates expected
            elif time_since_end < 86400:  # < 1 day
                return 1800  # 30 minutes
            else:
                return 3600  # 1 hour

        return 600  # 10 minutes

    def get(self, source, identifier, module=None, **kwargs):
        """
        Get cached response.

        Args:
            source: API source
            identifier: Unique identifier
            module: Module instance for TTL calculation (optional)
            **kwargs: Additional key parameters

        Returns:
            Cached data or None if cache miss
        """
        key = self.get_cache_key(source, identifier, **kwargs)
        data = self.cache.get(key)

        if data is not None:
            logger.debug(f"Cache HIT: {key}")
        else:
            logger.debug(f"Cache MISS: {key}")

        return data

    def set(self, source, identifier, data, module=None, ttl=None, **kwargs):
        """
        Set cached response with smart TTL.

        Args:
            source: API source
            identifier: Unique identifier
            data: Data to cache
            module: Module instance for TTL calculation (optional)
            ttl: Manual TTL override in seconds (optional)
            **kwargs: Additional key parameters
        """
        key = self.get_cache_key(source, identifier, **kwargs)
        cache_ttl = ttl if ttl is not None else self.get_ttl(module)

        self.cache.set(key, data, cache_ttl)
        logger.info(f"Cached {key} for {cache_ttl}s (backend: {self.cache_name})")

    def invalidate(self, source, identifier, **kwargs):
        """
        Manually invalidate specific cache entry.

        Args:
            source: API source
            identifier: Unique identifier
            **kwargs: Additional key parameters

        Returns:
            bool: True if key existed and was deleted
        """
        key = self.get_cache_key(source, identifier, **kwargs)
        result = self.cache.delete(key)

        if result:
            logger.info(f"Invalidated cache: {key}")
        else:
            logger.debug(f"Cache key not found: {key}")

        return bool(result)

    def invalidate_pattern(self, pattern):
        """
        Invalidate all keys matching pattern (Redis only).

        Args:
            pattern: Pattern to match (e.g., 'hltv:tournament_123:*')

        Returns:
            int: Number of keys deleted

        Examples:
            # Clear all HLTV tournament data
            invalidate_pattern('hltv:tournament_*')

            # Clear specific tournament
            invalidate_pattern('hltv:tournament_1234:*')
        """
        if hasattr(self.cache, 'delete_pattern'):
            count = self.cache.delete_pattern(pattern)
            logger.info(f"Invalidated {count} keys matching pattern: {pattern}")
            return count
        else:
            logger.warning(
                f"Pattern deletion not supported by cache backend: {self.cache_name}"
            )
            return 0

    def clear_all(self):
        """
        Clear all cache entries.

        Use with caution!
        """
        self.cache.clear()
        logger.warning(f"Cleared all cache for backend: {self.cache_name}")


response_cache = ResponseCache()
