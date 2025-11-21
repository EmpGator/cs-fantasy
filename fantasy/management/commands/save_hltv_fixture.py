"""
Management command to save HLTV HTML fixtures for testing.

Usage:
    python manage.py save_hltv_fixture --url https://www.hltv.org/events/7148/... --name swiss_results_sample
    python manage.py save_hltv_fixture --url https://www.hltv.org/stats/leaderboards/kills?event=7148 --name stats_kills
"""

import json
from datetime import datetime
from pathlib import Path
from django.core.management.base import BaseCommand
from fantasy.services import fetcher

import logging

logging.getLogger("fantasy.services").setLevel(logging.DEBUG)


class Command(BaseCommand):
    help = "Save HLTV HTML fixture for testing"

    def add_arguments(self, parser):
        parser.add_argument("--url", type=str, required=True, help="HLTV URL to fetch")
        parser.add_argument(
            "--name",
            type=str,
            required=True,
            help="Fixture name (without .html extension)",
        )
        parser.add_argument(
            "--description",
            type=str,
            default="",
            help="Description of what this fixture contains",
        )
        parser.add_argument(
            "--tournament", type=str, default="", help="Tournament name"
        )

    def handle(self, *args, **options):
        url = options["url"]
        name = options["name"]
        description = options["description"]
        tournament = options["tournament"]

        # Ensure .html extension
        if not name.endswith(".html"):
            name += ".html"

        # Fixtures directory
        fixtures_dir = (
            Path(__file__).parent.parent.parent / "tests" / "fixtures" / "hltv"
        )
        fixtures_dir.mkdir(parents=True, exist_ok=True)

        # Fetch HTML
        self.stdout.write(f"Fetching {url}...")
        try:
            html = fetcher.fetch(url, force_refresh=False)
            self.stdout.write(self.style.SUCCESS(f"Fetched {len(html)} characters"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to fetch: {e}"))
            return

        # Save HTML
        html_path = fixtures_dir / name
        html_path.write_text(html)
        self.stdout.write(self.style.SUCCESS(f"Saved HTML to {html_path}"))

        # Update metadata
        metadata_path = fixtures_dir / "metadata.json"
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())
        else:
            metadata = {}

        metadata[name] = {
            "captured_at": datetime.now().isoformat(),
            "source_url": url,
            "description": description or f"HLTV HTML fixture: {name}",
            "tournament": tournament,
            "notes": "Update periodically to catch HTML format changes",
        }

        metadata_path.write_text(json.dumps(metadata, indent=2))
        self.stdout.write(self.style.SUCCESS(f"Updated metadata: {metadata_path}"))

        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("✓ Fixture saved successfully!"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"Location: {html_path}")
        self.stdout.write(f"Size: {len(html):,} characters")
        self.stdout.write(f"URL: {url}")
        self.stdout.write("\nRun tests with:")
        self.stdout.write("  python manage.py test fantasy.tests.test_parser")
