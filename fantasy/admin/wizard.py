"""
Tournament creation wizard for admin.

Multi-step wizard to create tournaments from HLTV event URLs.
"""

import logging
from datetime import datetime
from django import forms
from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import path
from django.db import transaction
from django.utils import timezone

from fantasy.models import Tournament, Stage, Team, Player
from fantasy.models.swiss import (
    SwissModule,
    SwissScore,
    SwissModuleScore,
    SwissScoreGroup,
)
from fantasy.models.bracket import Bracket, BracketMatch
from fantasy.models.stat_predictions import (
    StatPredictionsModule,
    StatPredictionCategory,
    StatPredictionDefinition,
)
from fantasy.services.hltv_parser import parse_tournament_metadata

logger = logging.getLogger(__name__)


TOURNAMENT_FORMATS = {
    "swiss_playoffs": {
        "name": "Swiss + Playoffs",
        "description": "Standard format with Swiss group stage and single elimination playoffs",
        "stages": [
            {
                "name": "Group Stage",
                "order": 1,
                "modules": [
                    {"type": "swiss", "name": "Swiss Stage"},
                    {"type": "stat_predictions", "name": "Group Stage Stats"},
                ],
            },
            {
                "name": "Playoffs",
                "order": 2,
                "modules": [
                    {"type": "bracket", "name": "Playoff Bracket"},
                    {"type": "stat_predictions", "name": "Playoff Stats"},
                ],
            },
        ],
    },
    "bracket_playoffs": {
        "name": "Bracket + Playoffs",
        "description": "Double/Triple elimination group stage with playoffs",
        "stages": [
            {
                "name": "Group Stage",
                "order": 1,
                "modules": [
                    {"type": "bracket", "name": "Group Bracket"},
                    {"type": "stat_predictions", "name": "Group Stage Stats"},
                ],
            },
            {
                "name": "Playoffs",
                "order": 2,
                "modules": [
                    {"type": "bracket", "name": "Playoff Bracket"},
                    {"type": "stat_predictions", "name": "Playoff Stats"},
                ],
            },
        ],
    },
    "major": {
        "name": "Major (4 Stages)",
        "description": "Full major format with multiple qualification stages",
        "stages": [
            {
                "name": "Challengers Stage",
                "order": 1,
                "modules": [
                    {"type": "swiss", "name": "Challengers Swiss"},
                    {"type": "stat_predictions", "name": "Challengers Stats"},
                ],
            },
            {
                "name": "Legends Stage",
                "order": 2,
                "modules": [
                    {"type": "swiss", "name": "Legends Swiss"},
                    {"type": "stat_predictions", "name": "Legends Stats"},
                ],
            },
            {
                "name": "Champions Stage",
                "order": 3,
                "modules": [
                    {"type": "bracket", "name": "Champions Bracket"},
                    {"type": "stat_predictions", "name": "Champions Stats"},
                ],
            },
            {
                "name": "Grand Final",
                "order": 4,
                "modules": [
                    {"type": "bracket", "name": "Grand Final"},
                ],
            },
        ],
    },
}

STAT_PRESETS = {
    "dream_team": {
        "name": "Dream Team",
        "description": "Pick players for a fantasy dream team lineup",
        "categories": [
            {"slug": "clutches-1vsx-won", "title": "Clutch King"},
            {"slug": "awp-kills-per-round", "title": "AWP Master"},
            {"slug": "opening-kills-per-round", "title": "Entry Fragger"},
            {"slug": "deaths-per-round", "title": "Noob", "invert": True},
            {"slug": "round-swing", "title": "Impact Player"},
        ],
    },
}


class TournamentURLForm(forms.Form):
    """Step 1: Enter HLTV URL(s)"""

    hltv_url = forms.URLField(
        label="HLTV Event URL",
        help_text="e.g., https://www.hltv.org/events/1234/tournament-name",
        widget=forms.URLInput(attrs={"class": "vTextField", "style": "width: 100%"}),
    )
    additional_urls = forms.CharField(
        label="Additional URLs (for Majors)",
        required=False,
        help_text="One URL per line for related events",
        widget=forms.Textarea(attrs={"class": "vLargeTextField", "rows": 3}),
    )


class TournamentFormatForm(forms.Form):
    """Step 2: Select format based on parsed data"""

    format_type = forms.ChoiceField(
        label="Tournament Format",
        choices=[(k, v["name"]) for k, v in TOURNAMENT_FORMATS.items()],
        widget=forms.RadioSelect,
    )

    name = forms.CharField(
        max_length=255, widget=forms.TextInput(attrs={"class": "vTextField"})
    )
    start_date = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(
            attrs={"class": "vTextField", "type": "datetime-local"}
        ),
    )
    end_date = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(
            attrs={"class": "vTextField", "type": "datetime-local"}
        ),
    )


class TournamentConfirmForm(forms.Form):
    """Step 3: Confirm and customize modules"""

    pass


class TournamentWizardView:
    """
    Multi-step tournament creation wizard.

    Steps:
    1. Enter HLTV URL(s)
    2. Select format, review parsed metadata
    3. Confirm and create tournament
    """

    def __init__(self, admin_site):
        self.admin_site = admin_site

    def get_urls(self):
        """Return URL patterns for the wizard."""
        return [
            path(
                "wizard/",
                self.admin_site.admin_view(self.wizard_view),
                name="fantasy_tournament_wizard",
            ),
            path(
                "wizard/step2/",
                self.admin_site.admin_view(self.wizard_step2),
                name="fantasy_tournament_wizard_step2",
            ),
            path(
                "wizard/create/",
                self.admin_site.admin_view(self.wizard_create),
                name="fantasy_tournament_wizard_create",
            ),
        ]

    def wizard_view(self, request):
        """Step 1: URL input"""
        if request.method == "POST":
            form = TournamentURLForm(request.POST)
            if form.is_valid():
                request.session["wizard_url"] = form.cleaned_data["hltv_url"]
                request.session["wizard_additional_urls"] = form.cleaned_data[
                    "additional_urls"
                ]
                return redirect("admin:fantasy_tournament_wizard_step2")
        else:
            form = TournamentURLForm()

        context = {
            **self.admin_site.each_context(request),
            "title": "Tournament Wizard - Step 1",
            "form": form,
            "step": 1,
            "total_steps": 3,
        }
        return render(request, "admin/fantasy/tournament/wizard_step1.html", context)

    def wizard_step2(self, request):
        """Step 2: Module selection based on parsed tournament data"""
        hltv_url = request.session.get("wizard_url")
        additional_urls = request.session.get("wizard_additional_urls", "")
        if not hltv_url:
            messages.error(request, "Please start from step 1")
            return redirect("admin:fantasy_tournament_wizard")

        from fantasy.services.fetcher import Fetcher

        # Parse all URLs and build segments
        segments = []

        # Parse main URL
        try:
            html = Fetcher().fetch(url=hltv_url)
            metadata = parse_tournament_metadata(html)
            segments.append(
                {
                    "url": hltv_url,
                    "metadata": metadata,
                    "start_date": metadata.get("start_date"),
                    "end_date": metadata.get("end_date"),
                }
            )
        except Exception as e:
            logger.error(f"Failed to fetch tournament data: {e}")
            metadata = {
                "name": "",
                "teams": [],
                "players": [],
                "stages": [],
                "brackets": [],
                "has_swiss": False,
                "has_bracket": False,
            }
            segments.append(
                {
                    "url": hltv_url,
                    "metadata": metadata,
                    "start_date": None,
                    "end_date": None,
                }
            )

        # Parse additional URLs
        for additional_url in additional_urls.split("\n"):
            additional_url = additional_url.strip()
            if not additional_url:
                continue
            try:
                html = Fetcher().fetch(url=additional_url)
                add_metadata = parse_tournament_metadata(html)
                segments.append(
                    {
                        "url": additional_url,
                        "metadata": add_metadata,
                        "start_date": add_metadata.get("start_date"),
                        "end_date": add_metadata.get("end_date"),
                    }
                )
            except Exception as e:
                logger.error(
                    f"Failed to fetch additional tournament data from {additional_url}: {e}"
                )

        # Sort segments by start_date
        segments.sort(key=lambda s: s["start_date"] or timezone.now())

        # Calculate overall date range
        all_start_dates = [s["start_date"] for s in segments if s["start_date"]]
        all_end_dates = [s["end_date"] for s in segments if s["end_date"]]
        overall_start_date = min(all_start_dates) if all_start_dates else None
        overall_end_date = max(all_end_dates) if all_end_dates else None

        # Use main URL's name as tournament name
        tournament_name = metadata.get("name", "")

        suggested_modules = self._build_suggested_modules_from_segments(segments)

        if request.method == "POST":
            # Build stage data with custom names, dates, and order
            stage_configs = []
            for stage_idx, stage_data in enumerate(suggested_modules):
                stage_modules = []
                for mod_idx, module in enumerate(stage_data["modules"]):
                    checkbox_name = f"module_{stage_idx}_{mod_idx}"
                    if request.POST.get(checkbox_name):
                        # Get custom module name and dates
                        custom_name = request.POST.get(
                            f"module_name_{stage_idx}_{mod_idx}", module["name"]
                        )
                        module_start = request.POST.get(
                            f"module_start_{stage_idx}_{mod_idx}", ""
                        )
                        module_end = request.POST.get(
                            f"module_end_{stage_idx}_{mod_idx}", ""
                        )
                        module_copy = module.copy()
                        module_copy["original_name"] = module[
                            "name"
                        ]  # Preserve for bracket lookup
                        module_copy["name"] = custom_name
                        module_copy["custom_start"] = module_start
                        module_copy["custom_end"] = module_end
                        stage_modules.append(module_copy)

                if stage_modules:
                    # Get custom stage name and dates
                    custom_stage_name = request.POST.get(
                        f"stage_name_{stage_idx}", stage_data["stage_name"]
                    )
                    custom_start = request.POST.get(f"stage_start_{stage_idx}", "")
                    custom_end = request.POST.get(f"stage_end_{stage_idx}", "")
                    stage_order = int(
                        request.POST.get(f"stage_order_{stage_idx}", stage_idx)
                    )

                    stage_configs.append(
                        {
                            "stage_name": custom_stage_name,
                            "best_of": stage_data.get("best_of", 3),
                            "segment_idx": stage_data.get("segment_idx", 0),
                            "modules": stage_modules,
                            "custom_start": custom_start,
                            "custom_end": custom_end,
                            "order": stage_order,
                            "original_idx": stage_idx,
                        }
                    )

            # Sort by custom order
            stage_configs.sort(key=lambda x: x["order"])
            selected_modules = stage_configs

            request.session["wizard_name"] = request.POST.get("name", tournament_name)
            request.session["wizard_selected_modules"] = selected_modules

            request.session["wizard_start_date"] = (
                overall_start_date.isoformat() if overall_start_date else None
            )
            request.session["wizard_end_date"] = (
                overall_end_date.isoformat() if overall_end_date else None
            )

            # Store segments for later use (serialize brackets)
            serialized_segments = []
            for segment in segments:
                seg_meta = segment["metadata"]
                serialized_brackets = [
                    {
                        "name": b.name,
                        "bracket_type": b.bracket_type,
                        "matches": [
                            {
                                "hltv_match_id": m.hltv_match_id,
                                "slot_id": m.slot_id,
                                "team_a_hltv_id": m.team_a_hltv_id,
                                "team_b_hltv_id": m.team_b_hltv_id,
                            }
                            for m in b.matches
                        ],
                    }
                    for b in seg_meta.get("brackets", [])
                ]
                serialized_segments.append(
                    {
                        "url": segment["url"],
                        "start_date": segment["start_date"].isoformat()
                        if segment["start_date"]
                        else None,
                        "end_date": segment["end_date"].isoformat()
                        if segment["end_date"]
                        else None,
                        "teams": seg_meta.get("teams", []),
                        "players": seg_meta.get("players", []),
                        "brackets": serialized_brackets,
                    }
                )
            request.session["wizard_segments"] = serialized_segments

            return redirect("admin:fantasy_tournament_wizard_create")

        context = {
            **self.admin_site.each_context(request),
            "title": "Tournament Wizard - Step 2",
            "step": 2,
            "total_steps": 3,
            "segments": segments,
            "suggested_modules": suggested_modules,
            "stat_presets": STAT_PRESETS,
            "tournament_name": tournament_name,
        }
        return render(request, "admin/fantasy/tournament/wizard_step2.html", context)

    def _build_suggested_modules_from_segments(self, segments):
        """Build suggested modules from all segments, preserving segment index for player scoping."""
        all_suggested = []

        for segment_idx, segment in enumerate(segments):
            metadata = segment["metadata"]
            segment_modules = self._build_suggested_modules(metadata)

            # Add segment_idx and dates to each stage for later player lookup
            for stage_data in segment_modules:
                stage_data["segment_idx"] = segment_idx
                # Format dates for datetime-local input (YYYY-MM-DDTHH:MM)
                start_date = segment.get("start_date")
                end_date = segment.get("end_date")
                stage_data["start_date"] = (
                    start_date.strftime("%Y-%m-%dT%H:%M") if start_date else ""
                )
                stage_data["end_date"] = (
                    end_date.strftime("%Y-%m-%dT%H:%M") if end_date else ""
                )
                all_suggested.append(stage_data)

        return all_suggested

    def _build_suggested_modules(self, metadata):
        """Build suggested modules from parsed tournament metadata."""
        suggested = []
        stages = metadata.get("stages", [])
        brackets = metadata.get("brackets", [])

        if not stages:
            if metadata.get("has_swiss"):
                stages.append(
                    type(
                        "Stage",
                        (),
                        {
                            "name": "Group Stage",
                            "format_type": "swiss",
                            "best_of": 3,
                            "details": "",
                        },
                    )()
                )
            if metadata.get("has_bracket"):
                stages.append(
                    type(
                        "Stage",
                        (),
                        {
                            "name": "Playoffs",
                            "format_type": "bracket",
                            "best_of": 3,
                            "details": "",
                        },
                    )()
                )

        bracket_idx = 0
        for stage in stages:
            stage_modules = []

            if stage.format_type == "swiss":
                stage_modules.append(
                    {
                        "type": "swiss",
                        "name": f"{stage.name} Swiss",
                        "selected": True,
                    }
                )
            elif stage.format_type == "bracket":
                stage_brackets = []
                if brackets:
                    if bracket_idx < len(brackets):
                        stage_brackets.append(brackets[bracket_idx])
                        bracket_idx += 1
                    while bracket_idx < len(brackets):
                        next_bracket = brackets[bracket_idx]
                        if "group" in next_bracket.name.lower():
                            stage_brackets.append(next_bracket)
                            bracket_idx += 1
                        else:
                            break

                if stage_brackets:
                    for bracket in stage_brackets:
                        stage_modules.append(
                            {
                                "type": "bracket",
                                "name": bracket.name,
                                "bracket_data": bracket,
                                "selected": True,
                            }
                        )
                else:
                    stage_modules.append(
                        {
                            "type": "bracket",
                            "name": f"{stage.name} Bracket",
                            "selected": True,
                        }
                    )

            stage_modules.append(
                {
                    "type": "stat_predictions",
                    "name": f"{stage.name} Stats",
                    # TODO: either add more presets, or create some sort of dream_team config wizard
                    "preset": "dream_team",
                    "selected": True,
                }
            )

            suggested.append(
                {
                    "stage_name": stage.name,
                    "best_of": stage.best_of,
                    "modules": stage_modules,
                }
            )

        return suggested

    def wizard_create(self, request):
        """Step 3: Confirm and create"""
        selected_modules = request.session.get("wizard_selected_modules")
        if not selected_modules:
            messages.error(request, "Please complete step 2 first")
            return redirect("admin:fantasy_tournament_wizard")

        segments = request.session.get("wizard_segments", [])

        if request.method == "POST":
            try:
                tournament = self._create_tournament_from_wizard(request)
                messages.success(
                    request,
                    f"Successfully created tournament '{tournament.name}' with {tournament.modules.count()} modules",
                )
                for key in list(request.session.keys()):
                    if key.startswith("wizard_"):
                        del request.session[key]
                return redirect("admin:fantasy_tournament_change", tournament.pk)
            except Exception as e:
                logger.error(f"Failed to create tournament: {e}", exc_info=True)
                messages.error(request, f"Failed to create tournament: {e}")

        context = {
            **self.admin_site.each_context(request),
            "title": "Tournament Wizard - Step 3",
            "step": 3,
            "total_steps": 3,
            "selected_modules": selected_modules,
            "tournament_name": request.session.get("wizard_name"),
            "segments": segments,
        }
        return render(request, "admin/fantasy/tournament/wizard_step3.html", context)

    @transaction.atomic
    def _create_tournament_from_wizard(self, request):
        """Create tournament with all stages and modules."""
        selected_modules = request.session.get("wizard_selected_modules", [])
        segments = request.session.get("wizard_segments", [])

        start_date_str = request.session.get("wizard_start_date")
        end_date_str = request.session.get("wizard_end_date")

        start_date = None
        end_date = None
        if start_date_str:
            start_date = datetime.fromisoformat(start_date_str)
        if end_date_str:
            end_date = datetime.fromisoformat(end_date_str)

        if not start_date:
            start_date = timezone.now()
        if not end_date:
            end_date = start_date

        tournament = Tournament.objects.create(
            name=request.session.get("wizard_name"),
            hltv_url=request.session.get("wizard_url"),
            is_active=False,  # Not active until configured
            start_date=start_date,
            end_date=end_date,
        )

        # Build team_map and players_by_segment from all segments
        team_map = {}
        players_by_segment = {}

        for segment_idx, segment in enumerate(segments):
            segment_players = []

            for team_data in segment.get("teams", []):
                team, _ = Team.objects.get_or_create(
                    hltv_id=team_data["hltv_id"], defaults={"name": team_data["name"]}
                )
                team_map[team_data["hltv_id"]] = team

            for player_data in segment.get("players", []):
                team_hltv_id = player_data.get("team_hltv_id")
                team = team_map.get(team_hltv_id) if team_hltv_id else None

                if team_hltv_id and not team:
                    team, _ = Team.objects.get_or_create(
                        hltv_id=team_hltv_id, defaults={"name": f"Team {team_hltv_id}"}
                    )
                    team_map[team_hltv_id] = team

                player, _ = Player.objects.get_or_create(
                    hltv_id=player_data["hltv_id"],
                    defaults={"name": player_data["name"]},
                )
                if team and player.active_team != team:
                    player.active_team = team
                    player.save()

                segment_players.append(player)

            players_by_segment[segment_idx] = segment_players

        previous_stage = None

        for stage_idx, stage_data in enumerate(selected_modules):
            segment_idx = stage_data.get("segment_idx", 0)
            segment = segments[segment_idx] if segment_idx < len(segments) else {}

            # Use custom dates if provided, then segment dates, then tournament dates
            custom_start = stage_data.get("custom_start", "")
            custom_end = stage_data.get("custom_end", "")

            if custom_start:
                stage_start = datetime.fromisoformat(custom_start)
            else:
                seg_start_str = segment.get("start_date")
                stage_start = (
                    datetime.fromisoformat(seg_start_str)
                    if seg_start_str
                    else start_date
                )

            if custom_end:
                stage_end = datetime.fromisoformat(custom_end)
            else:
                seg_end_str = segment.get("end_date")
                stage_end = (
                    datetime.fromisoformat(seg_end_str) if seg_end_str else end_date
                )

            segment_url = segment.get("url", "")

            stage = Stage.objects.create(
                tournament=tournament,
                name=stage_data["stage_name"],
                order=stage_idx + 1,
                start_date=stage_start,
                end_date=stage_end,
                hltv_url=segment_url,  # Populate stage URL from segment
                is_active=(stage_idx == 0),  # Only first stage is active
            )

            if previous_stage:
                previous_stage.next_stage = stage
                previous_stage.save()

            best_of = stage_data.get("best_of", 3)
            segment_teams = segment.get("teams", [])
            segment_brackets = segment.get("brackets", [])
            segment_players = players_by_segment.get(segment_idx, [])

            for module_config in stage_data["modules"]:
                module_type = module_config["type"]

                # Use custom module dates if provided, otherwise use stage dates
                mod_custom_start = module_config.get("custom_start", "")
                mod_custom_end = module_config.get("custom_end", "")
                module_start = (
                    datetime.fromisoformat(mod_custom_start)
                    if mod_custom_start
                    else stage_start
                )
                module_end = (
                    datetime.fromisoformat(mod_custom_end)
                    if mod_custom_end
                    else stage_end
                )

                if module_type == "swiss":
                    self._create_swiss_module(
                        tournament=tournament,
                        stage=stage,
                        name=module_config["name"],
                        teams=segment_teams,
                        start_date=module_start,
                        end_date=module_end,
                    )
                elif module_type == "bracket":
                    bracket_info = None
                    # Use original_name for lookup (before user customization)
                    lookup_name = module_config.get(
                        "original_name", module_config["name"]
                    )
                    for bd in segment_brackets:
                        if bd["name"] == lookup_name:
                            bracket_info = bd
                            break

                    self._create_bracket_module(
                        tournament=tournament,
                        stage=stage,
                        name=module_config["name"],
                        bracket_data=bracket_info,
                        best_of=best_of,
                        start_date=module_start,
                        end_date=module_end,
                    )
                elif module_type == "stat_predictions":
                    preset_key = module_config.get("preset", "dream_team")
                    self._create_stat_predictions_module(
                        tournament=tournament,
                        stage=stage,
                        name=module_config["name"],
                        preset_key=preset_key,
                        players=segment_players,
                        start_date=module_start,
                        end_date=module_end,
                    )

            previous_stage = stage

        return tournament

    def _create_swiss_module(
        self, tournament, stage, name, teams, start_date, end_date
    ):
        """Create a Swiss module with default scores and teams."""
        module = SwissModule.objects.create(
            tournament=tournament,
            stage=stage,
            name=name,
            start_date=start_date,
            end_date=end_date,
            prediction_deadline=start_date,
        )

        self._create_default_swiss_scores(module)

        if teams:
            team_objs = Team.objects.filter(hltv_id__in=[t["hltv_id"] for t in teams])
            module.teams.set(team_objs)

        return module

    def _create_bracket_module(
        self, tournament, stage, name, bracket_data, best_of, start_date, end_date
    ):
        """Create a Bracket module with matches from parsed data."""
        module = Bracket.objects.create(
            tournament=tournament,
            stage=stage,
            name=name,
            start_date=start_date,
            end_date=end_date,
            prediction_deadline=start_date,
        )

        if bracket_data and bracket_data.get("matches"):
            matches_to_create = []
            for match_data in bracket_data["matches"]:
                round_num = 1
                slot_id = match_data.get("slot_id", "")
                if slot_id:
                    import re

                    round_match = re.search(r"r(\d+)", slot_id)
                    if round_match:
                        round_num = int(round_match.group(1))

                matches_to_create.append(
                    BracketMatch(
                        bracket=module,
                        round=round_num,
                        hltv_match_id=match_data.get("hltv_match_id"),
                        best_of=best_of,
                    )
                )

            if matches_to_create:
                BracketMatch.objects.bulk_create(matches_to_create)

                # Auto-tagging logic
                all_matches = list(module.matches.all())
                if all_matches:
                    max_round = max(m.round for m in all_matches)

                    for match in all_matches:
                        tags = []
                        if match.round == max_round:
                            tags.append("final")
                        elif match.round == max_round - 1:
                            tags.append("semi-final")
                        elif match.round == max_round - 2:
                            tags.append("quarter-final")

                        if tags:
                            match.tags = tags
                            match.save(update_fields=["tags"])

        return module

    def _create_stat_predictions_module(
        self, tournament, stage, name, preset_key, players, start_date, end_date
    ):
        """Create a StatPredictions module with preset definitions and players."""
        module = StatPredictionsModule.objects.create(
            tournament=tournament,
            stage=stage,
            name=name,
            start_date=start_date,
            end_date=end_date,
            prediction_deadline=start_date,
        )

        preset = STAT_PRESETS.get(preset_key)
        if not preset:
            logger.warning(f"Unknown stat preset: {preset_key}")
            return module

        for cat_config in preset["categories"]:
            try:
                category = StatPredictionCategory.objects.get(slug=cat_config["slug"])
            except StatPredictionCategory.DoesNotExist:
                logger.warning(f"Category not found: {cat_config['slug']}")
                continue

            definition = StatPredictionDefinition.objects.create(
                module=module,
                category=category,
                title=cat_config["title"],
                invert_results=cat_config.get("invert", False),
            )

            if players:
                definition.options.set(players)

        return module

    def _create_default_swiss_scores(self, module):
        """Create default Swiss score options for a module."""
        qualified, _ = SwissScoreGroup.objects.get_or_create(name="Qualified")
        eliminated, _ = SwissScoreGroup.objects.get_or_create(name="Eliminated")

        # Standard Swiss records, these could be dynamically calculated
        records = [
            (3, 0, [qualified], 2),
            (3, 1, [qualified], 3),
            (3, 2, [qualified], 3),
            (0, 3, [eliminated], 2),
            (1, 3, [eliminated], 3),
            (2, 3, [eliminated], 3),
        ]  # (wins, losses, groups, limit_per_user)

        for wins, losses, groups, limit_per_user in records:
            score, _ = SwissScore.objects.get_or_create(wins=wins, losses=losses)
            score.groups.set(groups)
            SwissModuleScore.objects.create(
                module=module,
                score=score,
                limit_per_user=limit_per_user,
            )


tournament_wizard = None


def get_tournament_wizard(admin_site):
    """Get or create the tournament wizard instance."""
    global tournament_wizard
    if tournament_wizard is None:
        tournament_wizard = TournamentWizardView(admin_site)
    return tournament_wizard
