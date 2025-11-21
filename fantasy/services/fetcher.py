"""
External data fetcher for HLTV and other sources.

Fetches HTML pages using curl_cffi with smart caching.
Returns raw HTML for parsers to process.
"""

import logging
from .cache import response_cache

logger = logging.getLogger(__name__)


class Fetcher:
    """
    Unified fetcher for scraping external data sources.

    Uses curl_cffi to bypass Cloudflare protection with browser impersonation.
    Caches raw HTML responses automatically.
    """

    def __init__(self, cache=None):
        """
        Initialize fetcher.

        Args:
            cache: ResponseCache instance (default: global response_cache)
        """
        self.cache = cache or response_cache
        self._session = None

    @property
    def session(self):
        """Lazy-load curl_cffi session"""
        if self._session is None:
            try:
                from curl_cffi.requests import Session

                self._session = Session(impersonate="firefox")
                logger.debug("Created curl_cffi session with Firefox impersonation")
            except ImportError:
                logger.error(
                    "curl_cffi not installed. Install with: pip install curl_cffi"
                )
                raise
        return self._session

    def _get_stored_cookies(self, domain="www.hltv.org"):
        """
        Get stored Cloudflare cookies from database.

        Returns:
            dict: Cookie dictionary or empty dict if no cookies stored
        """
        try:
            from fantasy.models import CloudflareCookie

            cookie = CloudflareCookie.get_latest(domain)
            if cookie:
                cookies = {"cf_clearance": cookie.cf_clearance}
                if cookie.cf_bm:
                    cookies["__cf_bm"] = cookie.cf_bm
                return cookies, cookie
        except Exception as e:
            logger.warning(f"Failed to get stored cookies: {e}")

        return {}, None

    def fetch(
        self, url: str, module=None, force_refresh: bool = False, timeout: int = 30
    ) -> str:
        """
        Fetch HTML from URL with caching.

        Args:
            url: Full URL to fetch
            module: Module instance for smart TTL caching (optional)
            force_refresh: Skip cache and fetch fresh data
            timeout: Request timeout in seconds

        Returns:
            str: Raw HTML content

        Raises:
            FetchError: If fetch fails after retries

        Examples:
            html = fetcher.fetch('https://www.hltv.org/events/7148/...')
            html = fetcher.fetch(tournament.hltv_url, module=swiss_module)
        """
        if not url:
            raise ValueError("URL cannot be empty")

        cache_key_data = self._get_cache_identifier(url)

        if not force_refresh:
            cached_html = self.cache.get(
                source="hltv", identifier=cache_key_data, module=module
            )
            if cached_html is not None:
                logger.debug(f"Cache HIT for {url}")
                return cached_html

        logger.debug(f"Cache MISS for {url}")
        logger.info(f"Fetching URL: {url}")
        html = self._fetch_from_source(url, timeout)

        self.cache.set(
            source="hltv", identifier=cache_key_data, data=html, module=module
        )

        return html

    def _fetch_from_source(self, url: str, timeout: int) -> str:
        """
        Fetch HTML from source using curl_cffi.

        Uses stored Cloudflare cookies if available for protected pages.

        Args:
            url: URL to fetch
            timeout: Request timeout

        Returns:
            str: Raw HTML content

        Raises:
            FetchError: If fetch fails
        """
        cookies, cookie_obj = self._get_stored_cookies()

        try:
            if cookies:
                logger.debug(f"Using stored cookies (age: {cookie_obj.age_minutes}m)")
                headers = {}
                if cookie_obj and cookie_obj.user_agent:
                    headers["User-Agent"] = cookie_obj.user_agent
                response = self.session.get(url, timeout=timeout, cookies=cookies, headers=headers)
            else:
                response = self.session.get(url, timeout=timeout)

            response.raise_for_status()

            if cookie_obj:
                cookie_obj.mark_used(success=True)

            logger.info(f"Successfully fetched {url} ({len(response.text)} chars)")
            return response.text

        except Exception as e:
            if cookie_obj and "403" in str(e):
                cookie_obj.mark_used(success=False, error=str(e))
                logger.warning(f"Cookies may be expired. Consider refreshing them.")

            logger.error(f"Failed to fetch {url}: {e}")
            raise FetchError(f"Failed to fetch {url}: {e}") from e

    def _get_cache_identifier(self, url: str) -> str:
        """
        Generate cache identifier from URL.

        Extracts meaningful parts of URL for cache key.

        Args:
            url: Full URL

        Returns:
            str: Cache identifier
        """
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            path = parsed.path.strip("/")

            identifier = path.replace("/", "_")
            if parsed.query:
                identifier += f"__{parsed.query[:50]}"

            return identifier
        except Exception:
            import hashlib

            return hashlib.md5(url.encode()).hexdigest()[:16]

    def invalidate_cache(self, url: str):
        """
        Manually invalidate cache for specific URL.

        Args:
            url: URL to invalidate
        """
        cache_key_data = self._get_cache_identifier(url)
        self.cache.invalidate(source="hltv", identifier=cache_key_data)
        logger.info(f"Invalidated cache for {url}")


class FetchError(Exception):
    """Raised when fetching fails"""

    pass


fetcher = Fetcher()
