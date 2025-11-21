"""
Management command for cache control operations.

Usage:
    python manage.py cache_control --clear-all
    python manage.py cache_control --clear-pattern "hltv:tournament_*"
    python manage.py cache_control --clear-tournament 1234
    python manage.py cache_control --stats
"""
from django.core.management.base import BaseCommand
from fantasy.services.cache import response_cache


class Command(BaseCommand):
    help = "Manage API response cache"

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear-all',
            action='store_true',
            help='Clear all cached responses'
        )
        parser.add_argument(
            '--clear-pattern',
            type=str,
            help='Clear cache entries matching pattern (e.g., hltv:tournament_*)'
        )
        parser.add_argument(
            '--clear-tournament',
            type=int,
            help='Clear all cache for specific tournament ID'
        )
        parser.add_argument(
            '--clear-stat',
            type=str,
            help='Clear specific stat type cache (e.g., mvp)'
        )
        parser.add_argument(
            '--stats',
            action='store_true',
            help='Show cache statistics (Redis only)'
        )

    def handle(self, *args, **options):
        if options['clear_all']:
            self._clear_all()
        elif options['clear_pattern']:
            self._clear_pattern(options['clear_pattern'])
        elif options['clear_tournament']:
            self._clear_tournament(options['clear_tournament'])
        elif options['clear_stat']:
            self._clear_stat(options['clear_stat'])
        elif options['stats']:
            self._show_stats()
        else:
            self.stdout.write(
                self.style.ERROR('No action specified. Use --help for options.')
            )

    def _clear_all(self):
        """Clear all cache"""
        response_cache.clear_all()
        self.stdout.write(
            self.style.SUCCESS('Successfully cleared all cache')
        )

    def _clear_pattern(self, pattern):
        """Clear cache matching pattern"""
        count = response_cache.invalidate_pattern(pattern)
        self.stdout.write(
            self.style.SUCCESS(
                f'Cleared {count} cache entries matching pattern: {pattern}'
            )
        )

    def _clear_tournament(self, tournament_id):
        """Clear all cache for a tournament"""
        pattern = f'hltv:*tournament_{tournament_id}*'
        count = response_cache.invalidate_pattern(pattern)
        self.stdout.write(
            self.style.SUCCESS(
                f'Cleared {count} cache entries for tournament {tournament_id}'
            )
        )

    def _clear_stat(self, stat_type):
        """Clear specific stat type cache"""
        pattern = f'hltv:stats_{stat_type}:*'
        count = response_cache.invalidate_pattern(pattern)
        self.stdout.write(
            self.style.SUCCESS(
                f'Cleared {count} cache entries for stat type: {stat_type}'
            )
        )

    def _show_stats(self):
        """Show cache statistics"""
        # This requires Redis backend
        if hasattr(response_cache.cache, 'client'):
            try:
                from django_redis import get_redis_connection
                redis_conn = get_redis_connection('default')
                info = redis_conn.info('stats')

                self.stdout.write(self.style.SUCCESS('Cache Statistics:'))
                self.stdout.write(f"  Total keys: {redis_conn.dbsize()}")
                self.stdout.write(f"  Hits: {info.get('keyspace_hits', 'N/A')}")
                self.stdout.write(f"  Misses: {info.get('keyspace_misses', 'N/A')}")

                # Show sample keys
                keys = redis_conn.keys('hltv:*')[:10]
                if keys:
                    self.stdout.write('\nSample cache keys:')
                    for key in keys:
                        ttl = redis_conn.ttl(key)
                        self.stdout.write(f"  {key.decode()} (TTL: {ttl}s)")
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error getting stats: {e}')
                )
        else:
            self.stdout.write(
                self.style.WARNING('Cache stats only available with Redis backend')
            )
