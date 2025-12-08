from bs4 import BeautifulSoup
import re
import json
import html
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Team:
    name: str
    hltv_id: int


@dataclass
class Player:
    name: str
    hltv_id: int
    team_hltv_id: int | None = None


@dataclass
class ResultRow:
    team_hltv_id: int
    record: str


@dataclass
class LeaderboardEntry:
    hltv_id: int
    name: str
    value: float
    position: int


@dataclass
class TournamentStage:
    """Represents a stage parsed from HLTV formats table."""

    name: str  # "Group stage", "Playoffs"
    format_type: str  # "swiss", "bracket"
    best_of: int  # 1, 3, 5
    details: str  # Raw format text


def parse_teams_attending(html_content: str) -> dict:
    """
    Parses HLTV teams attending section to extract teams and their players.

    Returns dict with 'teams' and 'players' lists.
    """
    if not html_content:
        return {"teams": [], "players": []}

    soup = BeautifulSoup(html_content, "html.parser")

    teams = []
    players = []

    # Find teams attending grid
    teams_grid = soup.select_one(".teams-attending.grid")
    if not teams_grid:
        return {"teams": [], "players": []}

    for team_box in teams_grid.select(".team-box"):
        team_link = team_box.select_one(".team-name a")
        if not team_link:
            continue

        href = team_link.get("href", "")
        team_match = re.search(r"/team/(\d+)/", href)
        if not team_match:
            continue

        team_hltv_id = int(team_match.group(1))

        team_name_el = team_link.select_one(".text")
        team_name = team_name_el.text.strip() if team_name_el else ""

        if not team_name:
            continue

        teams.append(Team(name=team_name, hltv_id=team_hltv_id))

        lineup_box = team_box.select_one(".lineup-box")
        if lineup_box:
            for player_el in lineup_box.select(
                ".flag-align.player a[href*='/player/']"
            ):
                player_name = player_el.text.strip()
                player_href = player_el.get("href", "")
                player_match = re.search(r"/player/(\d+)/", player_href)
                if player_match:
                    player_hltv_id = int(player_match.group(1))
                    players.append(
                        Player(
                            name=player_name,
                            hltv_id=player_hltv_id,
                            team_hltv_id=team_hltv_id,
                        )
                    )

    return {
        "teams": teams,
        "players": players,
    }


def parse_swiss(html_content: str) -> list[ResultRow]:
    """
    Parses HLTV swiss HTML and extracts swiss results.

    Returns list of ResultRow with team records.
    """
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, "html.parser")

    results = []
    top_rows = soup.select(".group.swiss-mode .top-row")
    for row in top_rows:
        team_link = row.select_one(".group-name .team a")
        if team_link:
            href = team_link.get("href", "")
            match = re.search(r"/team/(\d+)/", href)
            if match:
                team_hltv_id = int(match.group(1))
                record_element = row.select_one(".points.cell-width-record")
                if record_element:
                    record = record_element.text.strip()
                    results.append(ResultRow(team_hltv_id=team_hltv_id, record=record))

    return results


def parse_leaderboard(html_content: str) -> list[LeaderboardEntry]:
    """
    Parses HLTV stats leaderboard HTML and extracts player rankings.

    Returns list of LeaderboardEntry with hltv_id, name, value, position.
    Ties result in shared positions (e.g., two 1st places, then 3rd).
    """
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, "html.parser")

    entries = []
    leader_divs = soup.select("div.leader")

    for div in leader_divs:
        player_link = div.select_one("span.leader-name a")
        if not player_link:
            continue

        href = player_link.get("href", "")
        match = re.search(r"/stats/players/(\d+)/([^?]+)", href)
        if not match:
            continue

        hltv_id = int(match.group(1))
        name = player_link.text.strip()

        rating_span = div.select_one("span.leader-rating span")
        if not rating_span:
            continue

        try:
            text = rating_span.text.strip().replace("%", "")
            value = float(text)
        except ValueError:
            value = rating_span.text.strip()

        entries.append({"hltv_id": hltv_id, "name": name, "value": value})

    # Can't soret by value as it's not known if bigger is better
    # They should be sorted by default anyways
    entries.sort(key=lambda x: x["value"], reverse=True)

    result = []
    current_rank = 1
    previous_value = None

    for i, entry in enumerate(entries):
        if previous_value is not None and entry["value"] < previous_value:
            current_rank += 1

        result.append(
            LeaderboardEntry(
                hltv_id=entry["hltv_id"],
                name=entry["name"],
                value=entry["value"],
                position=current_rank,
            )
        )
        previous_value = entry["value"]

    return result


@dataclass
class TournamentMetadata:
    name: str
    hltv_id: int | None
    start_date: str | None
    end_date: str | None
    teams: list
    has_swiss: bool
    has_bracket: bool
    stage_count: int
    related_events: list


@dataclass
class BracketMatchResult:
    hltv_match_id: int
    slot_id: str
    team_a_hltv_id: int
    team_b_hltv_id: int
    team_a_score: int
    team_b_score: int
    winner_hltv_id: int | None
    best_of: int = 3


@dataclass
class ParsedBracket:
    name: str
    bracket_type: str
    matches: list[BracketMatchResult]


def parse_brackets(html_content: str) -> list[ParsedBracket]:
    """
    Parses HLTV bracket HTML and extracts structured bracket data.

    Returns list of ParsedBracket containing match results.
    """
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, "html.parser")
    brackets = []

    for el in soup.select("[data-slotted-bracket-json]"):
        json_str = html.unescape(el.get("data-slotted-bracket-json", ""))
        if not json_str:
            continue

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            continue

        bracket_name = data.get("name", "")
        bracket_type = data.get("type", "").split(".")[-1]
        matches = []

        for round_data in data.get("rounds", []):
            for slot in round_data.get("slots", []):
                slot_id = slot.get("slotId", {}).get("id", "")
                matchup = slot.get("matchup", {})

                if not matchup:
                    continue

                match_info = matchup.get("match", {})
                if not match_info:
                    continue

                hltv_match_id = match_info.get("matchId")
                if not hltv_match_id:
                    continue

                team1_slot = matchup.get("team1", {})
                team2_slot = matchup.get("team2", {})

                team1_info = team1_slot.get("team")
                team2_info = team2_slot.get("team")

                team_a_hltv_id = team1_info.get("id") if team1_info else None
                team_b_hltv_id = team2_info.get("id") if team2_info else None

                # Include all matches, even those without teams (future rounds)
                result = matchup.get("result", {}) or {}
                match_score = result.get("matchScore", {})
                team_a_score = match_score.get("team1Score", 0)
                team_b_score = match_score.get("team2Score", 0)

                winner_hltv_id = None
                if match_score.get("team1Winner") and team_a_hltv_id:
                    winner_hltv_id = team_a_hltv_id
                elif match_score.get("team2Winner") and team_b_hltv_id:
                    winner_hltv_id = team_b_hltv_id

                # Extract best_of from numberOfMaps
                best_of = match_info.get("numberOfMaps", 3)

                matches.append(
                    BracketMatchResult(
                        hltv_match_id=hltv_match_id,
                        slot_id=slot_id,
                        team_a_hltv_id=team_a_hltv_id,
                        team_b_hltv_id=team_b_hltv_id,
                        team_a_score=team_a_score,
                        team_b_score=team_b_score,
                        winner_hltv_id=winner_hltv_id,
                        best_of=best_of,
                    )
                )

        if matches:
            brackets.append(
                ParsedBracket(
                    name=bracket_name,
                    bracket_type=bracket_type,
                    matches=matches,
                )
            )

    return brackets


def parse_tournament_formats(html_content: str) -> list[TournamentStage]:
    """
    Parse HLTV formats table to extract tournament stages.

    Returns list of TournamentStage with format type and best_of detected.
    """
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, "html.parser")
    stages = []

    # Find the formats table
    formats_table = soup.select_one("table.formats.table")
    if not formats_table:
        return []

    for row in formats_table.select("tr"):
        header = row.select_one("th.format-header")
        data = row.select_one("td.format-data")

        if not header or not data:
            continue

        stage_name = header.text.strip()
        format_text = data.text.strip()

        format_lower = format_text.lower()
        if "swiss" in format_lower:
            format_type = "swiss"
        elif any(kw in format_lower for kw in ["elimination", "gsl", "bracket"]):
            format_type = "bracket"
        else:
            format_type = "bracket"

        best_of = 3
        bo_match = re.search(r"bo(\d+)", format_lower)
        if bo_match:
            best_of = int(bo_match.group(1))

        stages.append(
            TournamentStage(
                name=stage_name,
                format_type=format_type,
                best_of=best_of,
                details=format_text,
            )
        )

    return stages


def parse_tournament_metadata(html_content: str) -> dict:
    """
    Parse HLTV event page to extract tournament metadata.

    Returns dict with tournament info for wizard.
    """
    if not html_content:
        return {}

    soup = BeautifulSoup(html_content, "html.parser")

    name_el = soup.select_one(".event-hub-title")
    name = name_el.text.strip() if name_el else ""

    hltv_id = None
    canonical = soup.select_one('link[rel="canonical"]')
    if canonical:
        href = canonical.get("href", "")
        match = re.search(r"/events/(\d+)/", href)
        if match:
            hltv_id = int(match.group(1))

    teams = []
    players = []
    parsed_attending = parse_teams_attending(html_content)
    if parsed_attending.get("teams"):
        teams = [
            {"hltv_id": t.hltv_id, "name": t.name} for t in parsed_attending["teams"]
        ]
    if parsed_attending.get("players"):
        players = [
            {"hltv_id": p.hltv_id, "name": p.name, "team_hltv_id": p.team_hltv_id}
            for p in parsed_attending["players"]
        ]

    stages = parse_tournament_formats(html_content)
    brackets = parse_brackets(html_content)
    has_swiss = bool(soup.select(".group.swiss-mode"))
    has_bracket = bool(soup.select("[data-slotted-bracket-json]"))

    if stages:
        stage_count = len(stages)
    else:
        sections = soup.select(".section-header span")
        section_names = [s.text.strip().lower() for s in sections]

        stage_count = 0
        if "group play" in section_names or has_swiss:
            stage_count += 1
        if "brackets" in section_names or has_bracket:
            stage_count += 1
        if stage_count == 0:
            stage_count = 2

    related_events = []
    for rel in soup.select(".related-event a"):
        href = rel.get("href", "")
        rel_name = rel.text.strip()
        match = re.search(r"/events/(\d+)/", href)
        if match:
            related_events.append(
                {
                    "hltv_id": int(match.group(1)),
                    "name": rel_name,
                    "url": f"https://www.hltv.org{href}"
                    if href.startswith("/")
                    else href,
                }
            )

    start_date = None
    end_date = None

    event_meta = soup.select_one("table.eventMeta")
    if event_meta:
        for row in event_meta.select("tr"):
            header = row.select_one("th")
            if not header:
                continue
            header_text = header.text.strip().lower()

            if "start date" in header_text:
                span = row.select_one("td span[data-unix]")
                if span:
                    unix_ms = span.get("data-unix")
                    if unix_ms:
                        start_date = datetime.fromtimestamp(
                            int(unix_ms) / 1000, tz=timezone.utc
                        )
            elif "end date" in header_text:
                span = row.select_one("td span[data-unix]")
                if span:
                    unix_ms = span.get("data-unix")
                    if unix_ms:
                        end_date = datetime.fromtimestamp(
                            int(unix_ms) / 1000, tz=timezone.utc
                        )

    if not start_date or not end_date:
        eventdate = soup.select_one("td.eventdate")
        if eventdate:
            date_spans = eventdate.select("span[data-unix]")
            if len(date_spans) >= 1 and not start_date:
                unix_ms = date_spans[0].get("data-unix")
                if unix_ms:
                    start_date = datetime.fromtimestamp(
                        int(unix_ms) / 1000, tz=timezone.utc
                    )
            if len(date_spans) >= 2 and not end_date:
                unix_ms = date_spans[1].get("data-unix")
                if unix_ms:
                    end_date = datetime.fromtimestamp(
                        int(unix_ms) / 1000, tz=timezone.utc
                    )

    return {
        "name": name,
        "hltv_id": hltv_id,
        "start_date": start_date,
        "end_date": end_date,
        "teams": teams,
        "players": players,
        "stages": stages,
        "brackets": brackets,
        "has_swiss": has_swiss,
        "has_bracket": has_bracket,
        "stage_count": stage_count,
        "related_events": related_events,
    }
