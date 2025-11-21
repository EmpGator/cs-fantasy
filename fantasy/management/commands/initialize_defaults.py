from django.core.management.base import BaseCommand
from fantasy.models import (
    SwissScore,
    SwissScoreGroup,
    StatPredictionCategory,
)


class Command(BaseCommand):
    help = "Initialize production defaults: Swiss infrastructure and stat prediction categories"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force recreate even if data exists",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)

        self.stdout.write(self.style.NOTICE("Initializing production defaults..."))

        # Check if data already exists
        if not force:
            if (
                SwissScoreGroup.objects.exists()
                and SwissScore.objects.exists()
                and StatPredictionCategory.objects.exists()
            ):
                self.stdout.write(
                    self.style.WARNING(
                        "Defaults already exist. Use --force to recreate."
                    )
                )
                return

        self._create_swiss_infrastructure()
        self._create_stat_prediction_infrastructure()

        self.stdout.write(
            self.style.SUCCESS("Production defaults initialized successfully!")
        )

    def _create_swiss_infrastructure(self):
        """Create Swiss score groups and scores."""
        self.stdout.write("Creating Swiss infrastructure...")

        # Create score groups
        qualified_group, created = SwissScoreGroup.objects.get_or_create(
            name="Qualified"
        )
        if created:
            self.stdout.write("  ✓ Created SwissScoreGroup: Qualified")
        else:
            self.stdout.write("  - SwissScoreGroup already exists: Qualified")

        eliminated_group, created = SwissScoreGroup.objects.get_or_create(
            name="Eliminated"
        )
        if created:
            self.stdout.write("  ✓ Created SwissScoreGroup: Eliminated")
        else:
            self.stdout.write("  - SwissScoreGroup already exists: Eliminated")

        # Create Swiss scores with group associations
        swiss_scores_data = [
            ("0-3", 0, 3, [eliminated_group]),
            ("1-3", 1, 3, [eliminated_group]),
            ("2-3", 2, 3, [eliminated_group]),
            ("3-0", 3, 0, [qualified_group]),
            ("3-1", 3, 1, [qualified_group]),
            ("3-2", 3, 2, [qualified_group]),
        ]

        for score_name, wins, losses, groups in swiss_scores_data:
            score, created = SwissScore.objects.get_or_create(wins=wins, losses=losses)
            if created:
                score.groups.set(groups)
                self.stdout.write(f"  ✓ Created SwissScore: {score_name}")
            else:
                self.stdout.write(f"  - SwissScore already exists: {score_name}")

        self.stdout.write(
            self.style.SUCCESS("Swiss infrastructure ready: 2 groups, 6 scores")
        )

    def _create_stat_prediction_infrastructure(self):
        """Create stat prediction categories from hardcoded list."""
        self.stdout.write("Creating stat prediction infrastructure...")

        # Get hardcoded categories
        categories_data = self._get_hltv_categories()

        from django.utils.text import slugify

        for name, url_template, prediction_key in categories_data:
            # Generate slug from name
            slug = slugify(name)

            category, created = StatPredictionCategory.objects.get_or_create(
                prediction_key=prediction_key,
                defaults={
                    "name": name,
                    "slug": slug,
                    "description": f"Predict the top {name.lower()} performers",
                    "url_template": url_template,
                },
            )

            # Update slug if category exists but doesn't have one
            if not created and not category.slug:
                category.slug = slug
                category.save(update_fields=["slug"])
                self.stdout.write(
                    f"  ⟳ Updated slug for StatPredictionCategory: {name}"
                )
            elif created:
                self.stdout.write(f"  ✓ Created StatPredictionCategory: {name}")
            else:
                self.stdout.write(f"  - StatPredictionCategory already exists: {name}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Stat prediction infrastructure ready: {len(categories_data)} categories"
            )
        )

    def _get_hltv_categories(self):
        """Return hardcoded HLTV stat categories."""
        # Format: (name, url_template, prediction_key)
        return [
            (
                "Rating 3.0",
                "https://www.hltv.org/stats/leaderboards/rating/rating?event={event_id}",
                "rating",
            ),
            (
                "Damage per round",
                "https://www.hltv.org/stats/leaderboards/adr/damage-per-round?event={event_id}",
                "damage_per_round",
            ),
            (
                "Total kills",
                "https://www.hltv.org/stats/leaderboards/tkills/total-kills?event={event_id}",
                "total_kills",
            ),
            (
                "Deaths per round",
                "https://www.hltv.org/stats/leaderboards/dpr/deaths-per-round?event={event_id}",
                "deaths_per_round",
            ),
            (
                "Total assists",
                "https://www.hltv.org/stats/leaderboards/tassists/total-assists?event={event_id}",
                "total_assists",
            ),
            (
                "KAST",
                "https://www.hltv.org/stats/leaderboards/kast/kast?event={event_id}",
                "kast",
            ),
            (
                "Clutches (1vsX) won",
                "https://www.hltv.org/stats/leaderboards/clutch/clutches-1vsx-won?event={event_id}",
                "clutches_1vsx_won",
            ),
            (
                "Headshots per round",
                "https://www.hltv.org/stats/leaderboards/hpr/headshots-per-round?event={event_id}",
                "headshots_per_round",
            ),
            (
                "Total AWP kills",
                "https://www.hltv.org/stats/leaderboards/tawpk/total-awp-kills?event={event_id}",
                "total_awp_kills",
            ),
            (
                "Total opening kills",
                "https://www.hltv.org/stats/leaderboards/top/total-opening-kills?event={event_id}",
                "total_opening_kills",
            ),
            (
                "Success in opening duels",
                "https://www.hltv.org/stats/leaderboards/duelsuccess/success-in-opening-duels?event={event_id}",
                "success_in_opening_duels",
            ),
            (
                "Round Swing",
                "https://www.hltv.org/stats/leaderboards/rs/round-swing?event={event_id}",
                "round_swing",
            ),
            (
                "KD diff",
                "https://www.hltv.org/stats/leaderboards/kddiff/kd-diff?event={event_id}",
                "kd_diff",
            ),
            (
                "Damage diff per round",
                "https://www.hltv.org/stats/leaderboards/ddiff/damage-diff-per-round?event={event_id}",
                "damage_diff_per_round",
            ),
            (
                "Kills per round",
                "https://www.hltv.org/stats/leaderboards/kpr/kills-per-round?event={event_id}",
                "kills_per_round",
            ),
            (
                "1+ kill rounds",
                "https://www.hltv.org/stats/leaderboards/mk/1-kill-rounds?event={event_id}",
                "1_kill_rounds",
            ),
            (
                "Assists per round",
                "https://www.hltv.org/stats/leaderboards/assistsr/assists-per-round?event={event_id}",
                "assists_per_round",
            ),
            (
                "Support rounds",
                "https://www.hltv.org/stats/leaderboards/supportr/support-rounds?event={event_id}",
                "support_rounds",
            ),
            (
                "Total headshots",
                "https://www.hltv.org/stats/leaderboards/totalhs/total-headshots?event={event_id}",
                "total_headshots",
            ),
            (
                "Headshot percentage",
                "https://www.hltv.org/stats/leaderboards/hsp/headshot-percentage?event={event_id}",
                "headshot_percentage",
            ),
            (
                "AWP kills per round",
                "https://www.hltv.org/stats/leaderboards/awpkr/awp-kills-per-round?event={event_id}",
                "awp_kills_per_round",
            ),
            (
                "Opening kills per round",
                "https://www.hltv.org/stats/leaderboards/opkr/opening-kills-per-round?event={event_id}",
                "opening_kills_per_round",
            ),
            (
                "Impact rating",
                "https://www.hltv.org/stats/leaderboards/impr/impact-rating?event={event_id}",
                "impact_rating",
            ),
            (
                "Multi-kill rating",
                "https://www.hltv.org/stats/leaderboards/mkr/multi-kill-rating?event={event_id}",
                "multi_kill_rating",
            ),
        ]
