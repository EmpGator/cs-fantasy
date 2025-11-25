"""
Debug command to test fetching and parsing HLTV pages.

Usage:
    # List all cached entries
    python manage.py debug_fetch_parse --list-cache

    # Debug a specific tournament (auto-detects cache keys)
    python manage.py debug_fetch_parse --tournament-id 1 --save-html

    # Debug specific URL
    python manage.py debug_fetch_parse <url> [--save-html]

    # Debug specific cache key
    python manage.py debug_fetch_parse --cached <cache_identifier> [--save-html /path/to/file.html]
"""

from django.core.management.base import BaseCommand, CommandError
from fantasy.services.fetcher import Fetcher
from fantasy.services.cache import response_cache
from fantasy.services.hltv_parser import (
    parse_swiss,
    parse_brackets,
    parse_leaderboard,
    parse_teams_attending,
)
import os


class Command(BaseCommand):
    help = "Debug fetch and parse operations for HLTV pages"

    def add_arguments(self, parser):
        parser.add_argument("url", nargs="?", type=str, help="URL to fetch and parse")
        parser.add_argument(
            "--tournament-id",
            type=int,
            help="Tournament ID to debug (fetches all related cache entries)",
        )
        parser.add_argument(
            "--list-cache", action="store_true", help="List all cached HLTV entries"
        )
        parser.add_argument(
            "--cached", type=str, help="Use cached data by cache identifier"
        )
        parser.add_argument(
            "--save-html",
            nargs="?",
            const="/tmp",
            help="Save HTML to file(s). If no path given, saves to /tmp/debug_N.html",
        )
        parser.add_argument(
            "--parser",
            type=str,
            choices=["swiss", "brackets", "leaderboard", "teams", "auto"],
            default="auto",
            help="Which parser to use (default: auto-detect)",
        )
        parser.add_argument(
            "--force-refresh", action="store_true", help="Force refresh (skip cache)"
        )

    def handle(self, *args, **options):
        url = options.get("url")
        cached_id = options.get("cached")
        tournament_id = options.get("tournament_id")
        list_cache = options.get("list_cache")
        save_path = options.get("save_html")
        parser_type = options["parser"]
        force_refresh = options["force_refresh"]

        if list_cache:
            self._list_cache_entries()
            return

        if tournament_id:
            self._debug_tournament(tournament_id, save_path)
            return

        if cached_id:
            self.stdout.write(f"Loading from cache: {cached_id}")
            html = response_cache.get(source="hltv", identifier=cached_id)
            if not html:
                raise CommandError(f"No cached data found for identifier: {cached_id}")
            self.stdout.write(
                self.style.SUCCESS(f"Loaded {len(html)} chars from cache")
            )
        elif url:
            self.stdout.write(f"Fetching: {url}")
            if force_refresh:
                self.stdout.write(
                    self.style.WARNING("Force refresh enabled - skipping cache")
                )

            fetcher = Fetcher()
            try:
                html = fetcher.fetch(url, force_refresh=force_refresh)
                self.stdout.write(self.style.SUCCESS(f"Fetched {len(html)} chars"))
            except Exception as e:
                raise CommandError(f"Fetch failed: {e}")
        else:
            raise CommandError("Must provide either url or --cached")

        if save_path:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(html)
            self.stdout.write(self.style.SUCCESS(f"Saved HTML to: {save_path}"))

        if parser_type == "auto":
            if "/stats/leaderboards/" in (url or cached_id or ""):
                parser_type = "leaderboard"
            elif "/events/" in (url or cached_id or ""):
                parser_type = "teams"
            else:
                self.stdout.write(
                    self.style.WARNING(
                        "Could not auto-detect parser. Use --parser to specify."
                    )
                )
                return

        self.stdout.write(f"\nUsing parser: {parser_type}")
        self.stdout.write("=" * 60)

        try:
            if parser_type == "swiss":
                results = parse_swiss(html)
                self.stdout.write(f"Parsed {len(results)} Swiss results:")
                for result in results[:10]:
                    self.stdout.write(
                        f"  - Team {result.team_hltv_id}: {result.record}"
                    )

            elif parser_type == "brackets":
                results = parse_brackets(html)
                self.stdout.write(f"Parsed {len(results)} brackets:")
                for bracket in results:
                    self.stdout.write(
                        f"  - {bracket.name} ({bracket.bracket_type}): {len(bracket.matches)} matches"
                    )

            elif parser_type == "leaderboard":
                results = parse_leaderboard(html)
                self.stdout.write(f"Parsed {len(results)} leaderboard entries:")
                for entry in results[:10]:
                    self.stdout.write(
                        f"  {entry.position}. {entry.name} (ID: {entry.hltv_id}): {entry.value}"
                    )

            elif parser_type == "teams":
                results = parse_teams_attending(html)
                teams = results.get("teams", [])
                players = results.get("players", [])
                self.stdout.write(f"Parsed {len(teams)} teams, {len(players)} players:")
                for team in teams[:5]:
                    self.stdout.write(f"  - Team: {team.name} (ID: {team.hltv_id})")
                for player in players[:10]:
                    self.stdout.write(
                        f"  - Player: {player.name} (ID: {player.hltv_id})"
                    )

            if not results or (isinstance(results, (list, dict)) and len(results) == 0):
                self.stdout.write(
                    self.style.WARNING("\nNo data parsed! Possible causes:")
                )
                self.stdout.write("  - HTML structure has changed")
                self.stdout.write("  - Page requires JavaScript (SPA)")
                self.stdout.write("  - Event has no data yet")
                self.stdout.write(
                    f"\nInspect HTML at: {save_path or '(use --save-html)'}"
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Parse error: {e}"))
            import traceback

            traceback.print_exc()

    def _list_cache_entries(self):
        """List all cached HLTV entries."""
        try:
            from django.core.cache import cache

            if hasattr(cache, "keys"):
                keys = cache.keys("hltv:*")
            else:
                from django_redis import get_redis_connection

                redis_conn = get_redis_connection("default")
                keys = redis_conn.keys("hltv:*")

            if not keys:
                self.stdout.write(self.style.WARNING("No cached entries found"))
                return

            self.stdout.write(f"Found {len(keys)} cached HLTV entries:\n")

            from collections import defaultdict

            by_type = defaultdict(list)

            for key in sorted(keys):
                key_str = key.decode() if isinstance(key, bytes) else key
                parts = key_str.split(":")
                if len(parts) >= 2:
                    identifier = parts[1]

                    if "events" in identifier:
                        by_type["Tournaments"].append((key_str, identifier))
                    elif "stats_leaderboards" in identifier:
                        by_type["Stat Leaderboards"].append((key_str, identifier))
                    else:
                        by_type["Other"].append((key_str, identifier))

            for category, entries in sorted(by_type.items()):
                self.stdout.write(self.style.SUCCESS(f"\n{category} ({len(entries)}):"))
                for i, (full_key, identifier) in enumerate(entries, 1):
                    self.stdout.write(f"  {i}. {identifier}")
                    self.stdout.write(f"     Cache key: {full_key}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error listing cache: {e}"))

    def _debug_tournament(self, tournament_id, save_dir):
        """Debug all cache entries for a tournament."""
        from fantasy.models import Tournament

        try:
            tournament = Tournament.objects.get(id=tournament_id)
        except Tournament.DoesNotExist:
            raise CommandError(f"Tournament {tournament_id} not found")

        self.stdout.write(
            f"Debugging tournament: {tournament.name} (ID: {tournament_id})"
        )

        if not tournament.hltv_url:
            raise CommandError("Tournament has no HLTV URL")

        import re

        match = re.search(r"/events/(\d+)/", tournament.hltv_url)
        if not match:
            raise CommandError(
                f"Could not extract event ID from URL: {tournament.hltv_url}"
            )

        event_id = match.group(1)
        self.stdout.write(f"Event ID: {event_id}\n")

        try:
            from django_redis import get_redis_connection

            redis_conn = get_redis_connection("default")

            tournament_keys = redis_conn.keys(f"hltv:*{event_id}*")

            if not tournament_keys:
                self.stdout.write(
                    self.style.WARNING("No cached entries found for this tournament")
                )
                return

            self.stdout.write(f"Found {len(tournament_keys)} cached entries:\n")

            for i, key in enumerate(sorted(tournament_keys), 1):
                key_str = key.decode() if isinstance(key, bytes) else key
                parts = key_str.split(":")
                identifier = parts[1] if len(parts) >= 2 else key_str

                self.stdout.write(f"\n{i}. {identifier}")

                html = response_cache.get(source="hltv", identifier=identifier)
                if not html:
                    self.stdout.write(self.style.WARNING("   (No data in cache)"))
                    continue

                self.stdout.write(f"   Size: {len(html):,} bytes")

                parser_type = None
                if "stats_leaderboards" in identifier:
                    parser_type = "leaderboard"
                elif "events" in identifier:
                    parser_type = "teams"

                if parser_type:
                    try:
                        if parser_type == "leaderboard":
                            results = parse_leaderboard(html)
                            self.stdout.write(
                                f"   Parsed: {len(results)} leaderboard entries"
                            )
                        elif parser_type == "teams":
                            results = parse_teams_attending(html)
                            teams = results.get("teams", [])
                            players = results.get("players", [])
                            self.stdout.write(
                                f"   Parsed: {len(teams)} teams, {len(players)} players"
                            )
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"   Parse error: {e}"))

                if save_dir:
                    if os.path.isdir(save_dir):
                        filename = f"debug_{i}_{identifier[:50].replace('/', '_')}.html"
                        filepath = os.path.join(save_dir, filename)
                    else:
                        filepath = (
                            save_dir
                            if i == 1
                            else f"{save_dir.rsplit('.', 1)[0]}_{i}.html"
                        )

                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(html)
                    self.stdout.write(f"   Saved to: {filepath}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error debugging tournament: {e}"))
