from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import random
from fantasy.models import (
    Tournament,
    Team,
    User,
    Player,
    SwissModule,
    SwissScore,
    SwissModuleScore,
    SwissScoreGroup,
    StatPredictionsModule,
    StatPredictionScoringRule,
    StatPredictionCategory,
    StatPredictionDefinition,
    Bracket,
    BracketMatch,
    Stage,
    SwissPrediction,
    StatPrediction,
    UserBracketPrediction,
    UserMatchPrediction,
    SwissResult,
    StatPredictionResult,
)


class Command(BaseCommand):
    help = "Create test data for tournament submissions"

    def handle(self, *args, **options):
        self.stdout.write("Creating test data...")

        self._clear_data()

        users = self._create_users()
        teams, players = self._create_teams_and_players()
        swiss_scores = self._create_swiss_infra()
        self._create_stat_pred_infra()

        self._create_finished_tournament(users, teams, players, swiss_scores)
        self._create_ongoing_tournament(users, teams, players, swiss_scores)
        self._create_upcoming_tournament(users, teams, players, swiss_scores)

        self.stdout.write(self.style.SUCCESS("Test data created successfully!"))

    def _clear_data(self):
        self.stdout.write("Clearing old test data...")
        # Start with models that have lots of dependencies
        UserMatchPrediction.objects.all().delete()
        UserBracketPrediction.objects.all().delete()
        SwissPrediction.objects.all().delete()
        StatPrediction.objects.all().delete()
        SwissResult.objects.all().delete()
        StatPredictionResult.objects.all().delete()

        # Models that are pointed to
        BracketMatch.objects.all().delete()
        SwissModuleScore.objects.all().delete()
        StatPredictionDefinition.objects.all().delete()

        # Models with fewer dependencies
        Player.objects.all().delete()
        SwissModule.objects.all().delete()
        StatPredictionsModule.objects.all().delete()
        Bracket.objects.all().delete()
        Stage.objects.all().delete()
        Tournament.objects.all().delete()
        Team.objects.all().delete()

        # Scoring infrastructure
        SwissScore.objects.all().delete()
        SwissScoreGroup.objects.all().delete()
        StatPredictionCategory.objects.all().delete()
        StatPredictionScoringRule.objects.all().delete()

        # Users, but keep superusers
        User.objects.filter(is_superuser=False).delete()
        self.stdout.write("Old test data cleared.")

    def _create_ongoing_tournament(self, users, teams, players, swiss_scores):
        self.stdout.write("Creating ongoing tournament...")
        tournament, _ = Tournament.objects.get_or_create(
            slug="iem-cologne-2025",
            defaults={
                "name": "IEM Cologne 2025",
                "description": "A prestigious CS2 tournament.",
                "start_date": timezone.now() - timedelta(days=3),
                "end_date": timezone.now() + timedelta(days=4),
                "is_active": True,
            },
        )
        group_stage, _ = Stage.objects.get_or_create(
            tournament=tournament, name="Group Stage"
        )
        playoff_stage, _ = Stage.objects.get_or_create(
            tournament=tournament, name="Playoff Stage"
        )

        # Completed Group Stage
        swiss_module, _ = SwissModule.objects.get_or_create(
            tournament=tournament,
            stage=group_stage,
            name="Swiss Stage",
            defaults={
                "description": "Swiss system group stage.",
                "start_date": timezone.now() - timedelta(days=3),
                "end_date": timezone.now() - timedelta(days=1),
                "prediction_deadline": timezone.now() - timedelta(days=2),
                "is_active": True,
                "is_completed": True,
            },
        )
        swiss_module.teams.set(teams)
        score_limits = {"0-3": 2, "1-3": 3, "2-3": 3, "3-0": 2, "3-1": 3, "3-2": 3}
        for score_name, limit in score_limits.items():
            swiss_score = swiss_scores[score_name]
            SwissModuleScore.objects.get_or_create(
                module=swiss_module,
                score=swiss_score,
                defaults={"limit_per_user": limit},
            )
        for user in users:
            shuffled_teams = random.sample(list(swiss_module.teams.all()), 16)
            for i, team in enumerate(shuffled_teams):
                score_key = (
                    "3-0"
                    if i < 2
                    else "3-1"
                    if i < 5
                    else "3-2"
                    if i < 8
                    else "2-3"
                    if i < 11
                    else "1-3"
                    if i < 14
                    else "0-3"
                )
                module_score = SwissModuleScore.objects.get(
                    module=swiss_module, score=swiss_scores[score_key]
                )
                SwissPrediction.objects.get_or_create(
                    user=user,
                    swiss_module=swiss_module,
                    team=team,
                    defaults={"predicted_record": module_score},
                )
        teams_for_swiss = list(swiss_module.teams.all())
        random.shuffle(teams_for_swiss)
        score_distribution = (
            ["3-0"] * 2
            + ["3-1"] * 3
            + ["3-2"] * 3
            + ["2-3"] * 3
            + ["1-3"] * 3
            + ["0-3"] * 2
        )
        for i, team in enumerate(teams_for_swiss):
            score_key = score_distribution[i]
            module_score = SwissModuleScore.objects.get(
                module=swiss_module, score=swiss_scores[score_key]
            )
            SwissResult.objects.get_or_create(
                swiss_module=swiss_module, team=team, defaults={"score": module_score}
            )

        stat_module_group, _ = StatPredictionsModule.objects.get_or_create(
            tournament=tournament,
            stage=group_stage,
            name="Group Stage Stat Predictions",
            defaults={
                "description": "Predict various stats for the group stage.",
                "start_date": timezone.now() - timedelta(days=3),
                "end_date": timezone.now() - timedelta(days=1),
                "prediction_deadline": timezone.now() - timedelta(days=2),
                "is_active": True,
                "is_completed": True,
            },
        )
        self._create_stat_definitions(stat_module_group, players, teams)
        self._create_stat_predictions_and_results(stat_module_group, users)

        # Upcoming Playoff Stage (starts in 2 days)
        bracket_module, _ = Bracket.objects.get_or_create(
            tournament=tournament,
            stage=playoff_stage,
            name="Playoffs Bracket",
            defaults={
                "description": "Playoff bracket.",
                "start_date": timezone.now() + timedelta(days=2),
                "end_date": timezone.now() + timedelta(days=6),
                "prediction_deadline": timezone.now() + timedelta(days=2),
                "is_active": True,
                "is_completed": False,
            },
        )

        # Create bracket structure with 8 teams if it doesn't exist
        if not bracket_module.matches.exists():
            # Create finals
            final = BracketMatch.objects.create(
                bracket=bracket_module, round=3, name="Final", best_of=5
            )
            # Create semifinals
            semi1 = BracketMatch.objects.create(
                bracket=bracket_module,
                round=2,
                name="Semifinal 1",
                winner_to_match=final,
            )
            semi2 = BracketMatch.objects.create(
                bracket=bracket_module,
                round=2,
                name="Semifinal 2",
                winner_to_match=final,
            )
            # Create quarterfinals
            qf1 = BracketMatch.objects.create(
                bracket=bracket_module,
                round=1,
                name="Quarterfinal 1",
                winner_to_match=semi1,
            )
            qf2 = BracketMatch.objects.create(
                bracket=bracket_module,
                round=1,
                name="Quarterfinal 2",
                winner_to_match=semi1,
            )
            qf3 = BracketMatch.objects.create(
                bracket=bracket_module,
                round=1,
                name="Quarterfinal 3",
                winner_to_match=semi2,
            )
            qf4 = BracketMatch.objects.create(
                bracket=bracket_module,
                round=1,
                name="Quarterfinal 4",
                winner_to_match=semi2,
            )

            # Get top 8 teams from Swiss results (qualified teams)
            qualified_results = SwissResult.objects.filter(
                swiss_module=swiss_module
            ).select_related("team", "score")
            # Get qualified group (3-0, 3-1, 3-2)
            qualified_group = SwissScoreGroup.objects.get(name="Qualified")
            top_teams = [
                result.team
                for result in qualified_results
                if qualified_group in result.score.score.groups.all()
            ][:8]

            # Seed teams into quarterfinals
            if len(top_teams) >= 8:
                qf1.team_a, qf1.team_b = top_teams[0], top_teams[7]
                qf2.team_a, qf2.team_b = top_teams[3], top_teams[4]
                qf3.team_a, qf3.team_b = top_teams[1], top_teams[6]
                qf4.team_a, qf4.team_b = top_teams[2], top_teams[5]
                qf1.save()
                qf2.save()
                qf3.save()
                qf4.save()

        # Create user predictions for all matches
        for user in users:
            user_bracket, _ = UserBracketPrediction.objects.get_or_create(
                user=user, bracket=bracket_module
            )
            for match in bracket_module.matches.all():
                if match.team_a and match.team_b:
                    winner = random.choice([match.team_a, match.team_b])
                    loser = match.team_b if winner == match.team_a else match.team_a
                    winner_score = (match.best_of // 2) + 1
                    loser_score = random.randint(0, winner_score - 1)
                    UserMatchPrediction.objects.get_or_create(
                        user_bracket=user_bracket,
                        match=match,
                        defaults={
                            "team_a": match.team_a,
                            "team_b": match.team_b,
                            "predicted_winner": winner,
                            "predicted_team_a_score": (
                                winner_score if winner == match.team_a else loser_score
                            ),
                            "predicted_team_b_score": (
                                winner_score if winner == match.team_b else loser_score
                            ),
                        },
                    )

        # Playoff Stat Predictions (also starts in 2 days)
        stat_module_playoff, _ = StatPredictionsModule.objects.get_or_create(
            tournament=tournament,
            stage=playoff_stage,
            name="Playoff Stat Predictions",
            defaults={
                "description": "Predict various stats for the playoffs.",
                "start_date": timezone.now() + timedelta(days=2),
                "end_date": timezone.now() + timedelta(days=6),
                "prediction_deadline": timezone.now() + timedelta(days=2),
                "is_active": True,
                "is_completed": False,
            },
        )
        self._create_stat_definitions(stat_module_playoff, players, teams)
        self._create_stat_predictions_for_module(stat_module_playoff, users)

    def _create_upcoming_tournament(self, users, teams, players, swiss_scores):
        self.stdout.write("Creating upcoming tournament...")
        tournament, _ = Tournament.objects.get_or_create(
            slug="esl-pro-league-s20",
            defaults={
                "name": "ESL Pro League Season 20",
                "description": "Upcoming season of ESL Pro League.",
                "start_date": timezone.now() + timedelta(days=10),
                "end_date": timezone.now() + timedelta(days=20),
                "is_active": True,
            },
        )
        group_stage, _ = Stage.objects.get_or_create(
            tournament=tournament, name="Group Stage"
        )

        # Upcoming Swiss module
        swiss_module, _ = SwissModule.objects.get_or_create(
            tournament=tournament,
            stage=group_stage,
            name="Swiss Stage",
            defaults={
                "description": "Swiss system group stage.",
                "start_date": timezone.now() + timedelta(days=10),
                "end_date": timezone.now() + timedelta(days=14),
                "prediction_deadline": timezone.now() + timedelta(days=9),
                "is_active": True,
                "is_completed": False,
            },
        )
        swiss_module.teams.set(teams)
        score_limits = {"0-3": 2, "1-3": 3, "2-3": 3, "3-0": 2, "3-1": 3, "3-2": 3}
        for score_name, limit in score_limits.items():
            swiss_score = swiss_scores[score_name]
            SwissModuleScore.objects.get_or_create(
                module=swiss_module,
                score=swiss_score,
                defaults={"limit_per_user": limit},
            )
        for user in users:
            shuffled_teams = random.sample(list(swiss_module.teams.all()), 16)
            for i, team in enumerate(shuffled_teams):
                score_key = (
                    "3-0"
                    if i < 2
                    else "3-1"
                    if i < 5
                    else "3-2"
                    if i < 8
                    else "2-3"
                    if i < 11
                    else "1-3"
                    if i < 14
                    else "0-3"
                )
                module_score = SwissModuleScore.objects.get(
                    module=swiss_module, score=swiss_scores[score_key]
                )
                SwissPrediction.objects.get_or_create(
                    user=user,
                    swiss_module=swiss_module,
                    team=team,
                    defaults={"predicted_record": module_score},
                )

        stat_module_group, _ = StatPredictionsModule.objects.get_or_create(
            tournament=tournament,
            stage=group_stage,
            name="Group Stage Stat Predictions",
            defaults={
                "description": "Predict various stats for the group stage.",
                "start_date": timezone.now() + timedelta(days=10),
                "end_date": timezone.now() + timedelta(days=14),
                "prediction_deadline": timezone.now() + timedelta(days=9),
                "is_active": True,
                "is_completed": False,
            },
        )
        self._create_stat_definitions(stat_module_group, players, teams)
        self._create_stat_predictions_for_module(stat_module_group, users)

    def _create_users(self):
        users = []
        for i in range(1, 7):
            user, created = User.objects.get_or_create(
                email=f"test{i}@example.com",
                defaults={"username": f"testuser{i}", "slug": f"testuser{i}"},
            )
            users.append(user)
            if created:
                self.stdout.write(f"Created user: {user.slug}")
        return users

    def _create_teams_and_players(self):
        teams_data = [
            ("FaZe Clan", "faze", 4869),
            ("Navi", "navi", 4608),
            ("G2 Esports", "g2", 5995),
            ("Astralis", "astralis", 6665),
            ("Vitality", "vitality", 9565),
            ("MOUZ", "mouz", 4494),
            ("Heroic", "heroic", 7175),
            ("Liquid", "liquid", 5973),
            ("FURIA", "furia", 8297),
            ("BIG", "big", 7532),
            ("Eternal Fire", "ef", 11251),
            ("Complexity", "col", 5005),
            ("Spirit", "spirit", 5699),
            ("Falcons", "falcons", 11271),
            ("SAW", "saw", 7773),
            ("MIBR", "mibr", 9215),
        ]
        teams = []
        for name, slug, hltv_id in teams_data:
            team, created = Team.objects.get_or_create(
                hltv_id=hltv_id, defaults={"name": name}
            )
            teams.append(team)
            if created:
                self.stdout.write(f"Created team: {team.name}")

        players_data = {
            "FaZe Clan": [
                ("karrigan", 429),
                ("rain", 8183),
                ("Twistzz", 10394),
                ("broky", 18053),
                ("frozen", 13150),
            ],
            "Navi": [
                ("b1t", 18987),
                ("jL", 19847),
                ("Aleksib", 7998),
                ("iM", 14759),
                ("w0nderful", 18222),
            ],
            "G2 Esports": [
                ("huNter-", 3972),
                ("NiKo", 3741),
                ("m0NESY", 19230),
                ("HooXi", 8865),
                ("nexa", 10297),
            ],
            "Astralis": [
                ("device", 7592),
                ("stavn", 10671),
                ("jabbi", 17956),
                ("br0", 15165),
                ("Staehr", 18221),
            ],
            "Vitality": [
                ("ZywOo", 11893),
                ("apEX", 7322),
                ("Spinx", 18223),
                ("flameZ", 18423),
                ("mezii", 16535),
            ],
            "MOUZ": [
                ("torzsi", 16920),
                ("xertioN", 17936),
                ("siuhy", 18123),
                ("Jimpphat", 20373),
                ("Brollan", 13666),
            ],
        }
        players = []
        for team_name, player_details in players_data.items():
            team = Team.objects.get(name=team_name)
            for player_name, hltv_id in player_details:
                player, _ = Player.objects.get_or_create(
                    hltv_id=hltv_id,
                    defaults={"name": player_name, "active_team": team},
                )
                players.append(player)
        return teams, players

    def _create_swiss_infra(self):
        qualified_group, _ = SwissScoreGroup.objects.get_or_create(name="Qualified")
        eliminated_group, _ = SwissScoreGroup.objects.get_or_create(name="Eliminated")
        swiss_scores_data = [
            ("0-3", 0, 3, [eliminated_group]),
            ("1-3", 1, 3, [eliminated_group]),
            ("2-3", 2, 3, [eliminated_group]),
            ("3-0", 3, 0, [qualified_group]),
            ("3-1", 3, 1, [qualified_group]),
            ("3-2", 3, 2, [qualified_group]),
        ]
        swiss_scores = {}
        for score_name, wins, losses, groups in swiss_scores_data:
            score, created = SwissScore.objects.get_or_create(wins=wins, losses=losses)
            if created:
                score.groups.set(groups)
            swiss_scores[score_name] = score
        return swiss_scores

    def _create_stat_pred_infra(self):
        scoring_rule, _ = StatPredictionScoringRule.objects.get_or_create(
            name="Simple Points",
            defaults={
                "description": "Points for correct pick.",
                "scoring_config": {
                    "rules": [
                        {
                            "id": "exact_pick",
                            "description": "Exact correct pick (1st place)",
                            "condition": {
                                "operator": "in_list_within_top_x",
                                "source": "prediction.player.hltv_id",
                                "target_list": "result.results",
                                "list_item_key": "hltv_id",
                                "position_key": "position",
                                "top_x": 1,
                            },
                            "scoring": {"operator": "fixed", "value": 10},
                            "exclusive": True,
                        },
                        {
                            "id": "top_3",
                            "description": "Pick in top 3",
                            "condition": {
                                "operator": "in_list_within_top_x",
                                "source": "prediction.player.hltv_id",
                                "target_list": "result.results",
                                "list_item_key": "hltv_id",
                                "position_key": "position",
                                "top_x": 3,
                            },
                            "scoring": {"operator": "fixed", "value": 5},
                            "exclusive": True,
                        },
                        {
                            "id": "top_5",
                            "description": "Pick in top 5",
                            "condition": {
                                "operator": "in_list_within_top_x",
                                "source": "prediction.player.hltv_id",
                                "target_list": "result.results",
                                "list_item_key": "hltv_id",
                                "position_key": "position",
                                "top_x": 5,
                            },
                            "scoring": {"operator": "fixed", "value": 3},
                            "exclusive": True,
                        },
                    ]
                },
            },
        )
        categories_data = [
            {"name": "Tournament MVP", "key": "mvp", "desc": "Predict the MVP."},
            {
                "name": "Most Kills",
                "key": "most_kills",
                "desc": "Player with most kills.",
            },
            {
                "name": "Tournament Winner",
                "key": "winner",
                "desc": "Team that will win.",
            },
        ]
        for cat_data in categories_data:
            StatPredictionCategory.objects.get_or_create(
                prediction_key=cat_data["key"],
                defaults={
                    "name": cat_data["name"],
                    "description": cat_data["desc"],
                    "default_scoring_rule": scoring_rule,
                },
            )

    def _create_stat_definitions(self, module, players, teams):
        categories = StatPredictionCategory.objects.all()
        for category in categories:
            definition, created = StatPredictionDefinition.objects.get_or_create(
                module=module,
                category=category,
                defaults={
                    "scoring_rule": category.default_scoring_rule,
                    "title": f"{category.name} - {module.name}",
                },
            )
            if created:
                if category.prediction_key in ["mvp", "most_kills"]:
                    definition.options.set(players)
                elif category.prediction_key == "winner":
                    definition.options.set(teams)

    def _create_stat_predictions_for_module(self, module, users):
        for definition in module.definitions.all():
            for user in users:
                option = random.choice(list(definition.options.all()))
                StatPrediction.objects.get_or_create(
                    user=user,
                    definition=definition,
                    defaults={
                        "player": option if isinstance(option, Player) else None,
                        "team": option if isinstance(option, Team) else None,
                    },
                )

    def _create_stat_predictions_and_results(self, module, users):
        self._create_stat_predictions_for_module(module, users)

        # Create results
        for definition in module.definitions.all():
            result_options = list(definition.options.all())
            if not result_options:
                continue

            # Create a plausible result for the stat prediction
            num_results = min(len(result_options), 10)
            leaderboard = random.sample(result_options, num_results)

            results_data = []
            for i, item in enumerate(leaderboard):
                results_data.append(
                    {
                        "name": item.name,
                        "hltv_id": item.hltv_id,
                        "value": random.randint(50, 200),  # Example value
                        "position": i + 1,
                    }
                )

            StatPredictionResult.objects.get_or_create(
                definition=definition,
                defaults={"results": results_data},
            )

    def _create_finished_tournament(self, users, teams, players, swiss_scores):
        self.stdout.write("Creating finished tournament...")
        tournament, _ = Tournament.objects.get_or_create(
            slug="blast-premier-fall-2024",
            defaults={
                "name": "BLAST Premier Fall 2024",
                "description": "Major CS2 tournament featuring the world's best teams",
                "start_date": timezone.now() - timedelta(days=14),
                "end_date": timezone.now() - timedelta(days=7),
                "is_active": True,
            },
        )
        group_stage, _ = Stage.objects.get_or_create(
            tournament=tournament, name="Group Stage"
        )
        playoff_stage, _ = Stage.objects.get_or_create(
            tournament=tournament, name="Playoff Stage"
        )

        # Swiss module
        swiss_module, _ = SwissModule.objects.get_or_create(
            tournament=tournament,
            stage=group_stage,
            name="Swiss Stage",
            defaults={
                "description": "Swiss system group stage with 16 teams",
                "start_date": timezone.now() - timedelta(days=14),
                "end_date": timezone.now() - timedelta(days=11),
                "prediction_deadline": timezone.now() - timedelta(days=12),
                "is_active": True,
                "is_completed": True,
            },
        )
        swiss_module.teams.set(teams)
        score_limits = {"0-3": 2, "1-3": 3, "2-3": 3, "3-0": 2, "3-1": 3, "3-2": 3}
        for score_name, limit in score_limits.items():
            swiss_score = swiss_scores[score_name]
            SwissModuleScore.objects.get_or_create(
                module=swiss_module,
                score=swiss_score,
                defaults={"limit_per_user": limit},
            )

        # Stat Predictions module (Group Stage)
        stat_module_group, _ = StatPredictionsModule.objects.get_or_create(
            tournament=tournament,
            stage=group_stage,
            name="Group Stage Stat Predictions",
            defaults={
                "description": "Predict various stats for the group stage.",
                "start_date": timezone.now() - timedelta(days=14),
                "end_date": timezone.now() - timedelta(days=11),
                "prediction_deadline": timezone.now() - timedelta(days=12),
                "is_active": True,
                "is_completed": True,
            },
        )
        self._create_stat_definitions(stat_module_group, players, teams)

        # Bracket module
        bracket_module, _ = Bracket.objects.get_or_create(
            tournament=tournament,
            stage=playoff_stage,
            name="Playoffs Bracket",
            defaults={
                "description": "8-team single-elimination playoff bracket.",
                "start_date": timezone.now() - timedelta(days=10),
                "end_date": timezone.now() - timedelta(days=7),
                "prediction_deadline": timezone.now() - timedelta(days=8),
                "is_active": True,
                "is_completed": True,
            },
        )

        # Create Bracket structure for 8 teams
        if not bracket_module.matches.exists():
            # Finals
            final = BracketMatch.objects.create(
                bracket=bracket_module, round=3, name="Final"
            )
            # Semifinals
            semi1 = BracketMatch.objects.create(
                bracket=bracket_module,
                round=2,
                name="Semifinal 1",
                winner_to_match=final,
            )
            semi2 = BracketMatch.objects.create(
                bracket=bracket_module,
                round=2,
                name="Semifinal 2",
                winner_to_match=final,
            )
            # Quarterfinals
            BracketMatch.objects.create(
                bracket=bracket_module,
                round=1,
                name="Quarterfinal 1",
                winner_to_match=semi1,
            )
            BracketMatch.objects.create(
                bracket=bracket_module,
                round=1,
                name="Quarterfinal 2",
                winner_to_match=semi1,
            )
            BracketMatch.objects.create(
                bracket=bracket_module,
                round=1,
                name="Quarterfinal 3",
                winner_to_match=semi2,
            )
            BracketMatch.objects.create(
                bracket=bracket_module,
                round=1,
                name="Quarterfinal 4",
                winner_to_match=semi2,
            )

            # Assign initial teams to QFs
            playoff_teams = teams[:8]
            qfs = bracket_module.matches.filter(round=1).order_by("name")
            qfs[0].team_a = playoff_teams[0]
            qfs[0].team_b = playoff_teams[1]
            qfs[0].save()
            qfs[1].team_a = playoff_teams[2]
            qfs[1].team_b = playoff_teams[3]
            qfs[1].save()
            qfs[2].team_a = playoff_teams[4]
            qfs[2].team_b = playoff_teams[5]
            qfs[2].save()
            qfs[3].team_a = playoff_teams[6]
            qfs[3].team_b = playoff_teams[7]
            qfs[3].save()

        # Stat Predictions module (Playoff Stage)
        stat_module_playoff, _ = StatPredictionsModule.objects.get_or_create(
            tournament=tournament,
            stage=playoff_stage,
            name="Playoff Stat Predictions",
            defaults={
                "description": "Predict various stats for the playoffs.",
                "start_date": timezone.now() - timedelta(days=10),
                "end_date": timezone.now() - timedelta(days=7),
                "prediction_deadline": timezone.now() - timedelta(days=8),
                "is_active": True,
                "is_completed": True,
            },
        )
        self._create_stat_definitions(stat_module_playoff, players, teams)

        # Predictions and Results for Swiss
        for user in users:
            shuffled_teams = random.sample(list(swiss_module.teams.all()), 16)
            for i, team in enumerate(shuffled_teams):
                score_key = (
                    "3-0"
                    if i < 2
                    else "3-1"
                    if i < 5
                    else "3-2"
                    if i < 8
                    else "2-3"
                    if i < 11
                    else "1-3"
                    if i < 14
                    else "0-3"
                )
                module_score = SwissModuleScore.objects.get(
                    module=swiss_module, score=swiss_scores[score_key]
                )
                SwissPrediction.objects.get_or_create(
                    user=user,
                    swiss_module=swiss_module,
                    team=team,
                    defaults={"predicted_record": module_score},
                )
        teams_for_swiss = list(swiss_module.teams.all())
        random.shuffle(teams_for_swiss)
        score_distribution = (
            ["3-0"] * 2
            + ["3-1"] * 3
            + ["3-2"] * 3
            + ["2-3"] * 3
            + ["1-3"] * 3
            + ["0-3"] * 2
        )
        for i, team in enumerate(teams_for_swiss):
            score_key = score_distribution[i]
            module_score = SwissModuleScore.objects.get(
                module=swiss_module, score=swiss_scores[score_key]
            )
            SwissResult.objects.get_or_create(
                swiss_module=swiss_module, team=team, defaults={"score": module_score}
            )

        # Predictions and Results for Stat Predictions
        self._create_stat_predictions_and_results(stat_module_group, users)
        self._create_stat_predictions_and_results(stat_module_playoff, users)

        # --- Generate complete Bracket data ---
        self.stdout.write("Generating complete bracket for finished tournament...")
        # 1. Clean slate
        bracket_module.matches.all().delete()

        # 2. Create structure
        final = BracketMatch.objects.create(
            bracket=bracket_module, round=3, name="Final", best_of=5
        )
        semi1 = BracketMatch.objects.create(
            bracket=bracket_module, round=2, name="Semifinal 1", winner_to_match=final
        )
        semi2 = BracketMatch.objects.create(
            bracket=bracket_module, round=2, name="Semifinal 2", winner_to_match=final
        )
        qf1 = BracketMatch.objects.create(
            bracket=bracket_module,
            round=1,
            name="Quarterfinal 1",
            winner_to_match=semi1,
        )
        qf2 = BracketMatch.objects.create(
            bracket=bracket_module,
            round=1,
            name="Quarterfinal 2",
            winner_to_match=semi1,
        )
        qf3 = BracketMatch.objects.create(
            bracket=bracket_module,
            round=1,
            name="Quarterfinal 3",
            winner_to_match=semi2,
        )
        qf4 = BracketMatch.objects.create(
            bracket=bracket_module,
            round=1,
            name="Quarterfinal 4",
            winner_to_match=semi2,
        )

        # 3. Seed initial teams
        playoff_teams = teams[:8]
        qf1.team_a, qf1.team_b = playoff_teams[0], playoff_teams[1]
        qf2.team_a, qf2.team_b = playoff_teams[2], playoff_teams[3]
        qf3.team_a, qf3.team_b = playoff_teams[4], playoff_teams[5]
        qf4.team_a, qf4.team_b = playoff_teams[6], playoff_teams[7]
        qf1.save()
        qf2.save()
        qf3.save()
        qf4.save()

        # 4. Simulate results and propagate winners
        # Process round by round to ensure teams propagate correctly
        for round_num in [1, 2, 3]:
            for match in bracket_module.matches.filter(round=round_num):
                # Refresh match to get latest team data
                match.refresh_from_db()
                if match.team_a and match.team_b and not match.winner:
                    winner = random.choice([match.team_a, match.team_b])
                    loser = match.team_b if winner == match.team_a else match.team_a

                    match.winner = winner
                    winner_score = (match.best_of // 2) + 1
                    loser_score = random.randint(0, winner_score - 1)
                    match.team_a_score = (
                        winner_score if winner == match.team_a else loser_score
                    )
                    match.team_b_score = (
                        winner_score if winner == match.team_b else loser_score
                    )
                    match.save()

                    if match.winner_to_match:
                        if not match.winner_to_match.team_a:
                            match.winner_to_match.team_a = winner
                        else:
                            match.winner_to_match.team_b = winner
                        match.winner_to_match.save()
                    if match.loser_to_match:
                        if not match.loser_to_match.team_a:
                            match.loser_to_match.team_a = loser
                        else:
                            match.loser_to_match.team_b = loser
                        match.loser_to_match.save()

        # 5. Create predictions for all matches with proper bracket flow
        # Build match relationships: which matches feed into which
        match_feeders = {}  # {match_id: [feeder_match_ids]}
        for match in bracket_module.matches.all():
            if match.winner_to_match_id:
                if match.winner_to_match_id not in match_feeders:
                    match_feeders[match.winner_to_match_id] = []
                match_feeders[match.winner_to_match_id].append(match.id)

        for user in users:
            user_bracket, _ = UserBracketPrediction.objects.get_or_create(
                user=user, bracket=bracket_module
            )
            # Track this user's predicted winners
            user_predicted_winners = {}  # {match_id: winner_team}

            # Process rounds in order so winners propagate
            for round_num in [1, 2, 3]:
                for match in bracket_module.matches.filter(round=round_num):
                    # Determine teams for this prediction
                    if round_num == 1:
                        # First round uses actual seeded teams
                        pred_team_a = match.team_a
                        pred_team_b = match.team_b
                    else:
                        # Later rounds use predicted winners from feeder matches
                        feeder_ids = match_feeders.get(match.id, [])
                        feeder_winners = [
                            user_predicted_winners.get(fid)
                            for fid in feeder_ids
                            if fid in user_predicted_winners
                        ]
                        if len(feeder_winners) >= 2:
                            pred_team_a = feeder_winners[0]
                            pred_team_b = feeder_winners[1]
                        elif len(feeder_winners) == 1:
                            pred_team_a = feeder_winners[0]
                            pred_team_b = None
                        else:
                            pred_team_a = None
                            pred_team_b = None

                    if pred_team_a and pred_team_b:
                        winner = random.choice([pred_team_a, pred_team_b])
                        user_predicted_winners[match.id] = winner

                        winner_score = (match.best_of // 2) + 1
                        loser_score = random.randint(0, winner_score - 1)
                        UserMatchPrediction.objects.get_or_create(
                            user_bracket=user_bracket,
                            match=match,
                            defaults={
                                "team_a": pred_team_a,
                                "team_b": pred_team_b,
                                "predicted_winner": winner,
                                "predicted_team_a_score": (
                                    winner_score if winner == pred_team_a else loser_score
                                ),
                                "predicted_team_b_score": (
                                    winner_score if winner == pred_team_b else loser_score
                                ),
                            },
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Skipping prediction for match {match.id} ({match.name}) due to missing teams."
                            )
                        )
