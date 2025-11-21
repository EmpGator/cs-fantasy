import json
from pathlib import Path
from django.test import SimpleTestCase
from fantasy.services.hltv_parser import (
    parse_swiss,
    parse_teams_attending,
    parse_leaderboard,
    parse_tournament_formats,
    parse_tournament_metadata,
    Team,
    Player,
    ResultRow,
    LeaderboardEntry,
    TournamentStage,
)


# Fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "hltv"


class HLTVParserTest(SimpleTestCase):
    """Test HLTV parser with stored HTML fixtures"""

    def test_parse_swiss_from_fixture(self):
        """
        Test parsing Swiss results from stored HTML fixture.
        """
        html_file_path = FIXTURES_DIR / "finished_swiss_tournament.html"

        if not html_file_path.exists():
            self.fail(
                f"Fixture not found at: {html_file_path}. "
                "Please save HTML content from HLTV."
            )

        html_content = html_file_path.read_text()

        if not html_content.strip():
            self.fail("HTML fixture is empty")

        # Parse swiss results
        results = parse_swiss(html_content)

        # Print for manual verification
        print("\n" + "=" * 60)
        print("Parsed Swiss Results:")
        print("=" * 60)
        print(f"Results: {len(results)}")
        for result in results[:5]:
            print(f"  {result}")
        print("=" * 60)

        # Assertions
        self.assertIsInstance(results, list)

        if results:
            result = results[0]
            self.assertIsInstance(result, ResultRow)
            self.assertIsInstance(result.team_hltv_id, int)
            # Verify record format (e.g., "3 - 0", "2 - 3")
            self.assertRegex(result.record, r"^\d+\s*-\s*\d+$")

    def test_parse_swiss_empty_html(self):
        """Test parser handles empty HTML gracefully"""
        results = parse_swiss("")
        self.assertEqual(results, [])

    def test_parse_swiss_invalid_html(self):
        """Test parser handles invalid HTML without crashing"""
        invalid_html = "<html><body>No swiss data here</body></html>"
        results = parse_swiss(invalid_html)
        self.assertEqual(results, [])

    def test_parse_teams_attending(self):
        """Test parsing teams attending section"""
        html = """
        <div class="teams-attending grid">
            <div class="col standard-box team-box">
                <div class="team-name"><a href="/team/6667/faze">
                    <div class="text-container"><div class="text">FaZe</div></div>
                </a></div>
                <div class="lineup-box hidden">
                    <div class="flag-align player text-ellipsis">
                        <a href="/player/429/karrigan">karrigan</a>
                    </div>
                    <div class="flag-align player text-ellipsis">
                        <a href="/player/9960/frozen">frozen</a>
                    </div>
                </div>
            </div>
            <div class="col standard-box team-box">
                <div class="team-name"><a href="/team/4991/fnatic">
                    <div class="text-container"><div class="text">fnatic</div></div>
                </a></div>
                <div class="lineup-box hidden">
                    <div class="flag-align player text-ellipsis">
                        <a href="/player/7528/krimz">KRIMZ</a>
                    </div>
                </div>
            </div>
        </div>
        """
        data = parse_teams_attending(html)

        self.assertEqual(len(data["teams"]), 2)
        self.assertEqual(len(data["players"]), 3)

        # Check team data
        self.assertEqual(data["teams"][0].name, "FaZe")
        self.assertEqual(data["teams"][0].hltv_id, 6667)
        self.assertEqual(data["teams"][1].name, "fnatic")
        self.assertEqual(data["teams"][1].hltv_id, 4991)

        # Check player data and team association
        karrigan = data["players"][0]
        self.assertEqual(karrigan.name, "karrigan")
        self.assertEqual(karrigan.hltv_id, 429)
        self.assertEqual(karrigan.team_hltv_id, 6667)

        krimz = data["players"][2]
        self.assertEqual(krimz.name, "KRIMZ")
        self.assertEqual(krimz.team_hltv_id, 4991)

    def test_parse_teams_attending_empty(self):
        """Test parser handles missing teams section"""
        html = "<html><body>No teams here</body></html>"
        data = parse_teams_attending(html)
        self.assertEqual(data["teams"], [])
        self.assertEqual(data["players"], [])

    def test_fixture_metadata_exists(self):
        """Test that fixture metadata file exists and is valid"""
        metadata_path = FIXTURES_DIR / "metadata.json"

        self.assertTrue(
            metadata_path.exists(),
            "metadata.json should exist to track fixture freshness",
        )

        metadata = json.loads(metadata_path.read_text())

        # Check metadata has required fields
        self.assertIn("finished_swiss_tournament.html", metadata)
        fixture_meta = metadata["finished_swiss_tournament.html"]

        self.assertIn("captured_at", fixture_meta)
        self.assertIn("source_url", fixture_meta)


class LeaderboardParserTest(SimpleTestCase):
    """Test HLTV leaderboard parser"""

    def test_parse_leaderboard_from_fixture(self):
        """Test parsing leaderboard from stored HTML fixture."""
        html_file_path = FIXTURES_DIR / "leaderboards_clutches.html"

        if not html_file_path.exists():
            self.skipTest(f"Fixture not found at: {html_file_path}")

        html_content = html_file_path.read_text()
        entries = parse_leaderboard(html_content)

        # Print for verification
        print("\n" + "=" * 60)
        print("Parsed Leaderboard:")
        print("=" * 60)
        for entry in entries[:10]:
            print(f"  {entry}")
        print("=" * 60)

        # Assertions
        self.assertIsInstance(entries, list)
        self.assertGreater(len(entries), 0, "Should parse at least one entry")

        # Check first entry structure
        entry = entries[0]
        self.assertIsInstance(entry, LeaderboardEntry)
        self.assertIsInstance(entry.hltv_id, int)
        self.assertIsInstance(entry.name, str)
        self.assertIsInstance(entry.value, float)
        self.assertIsInstance(entry.position, int)
        self.assertEqual(entry.position, 1, "First entry should have position 1")

    def test_parse_leaderboard_empty_html(self):
        """Test parser handles empty HTML gracefully"""
        entries = parse_leaderboard("")
        self.assertEqual(entries, [])

    def test_parse_leaderboard_invalid_html(self):
        """Test parser handles invalid HTML without crashing"""
        invalid_html = "<html><body>No leaderboard here</body></html>"
        entries = parse_leaderboard(invalid_html)
        self.assertEqual(entries, [])

    def test_parse_leaderboard_tie_positions(self):
        """Test that ties result in shared positions"""
        # Create HTML with tied values
        html = """
        <div class="leader">
            <span class="leader-name">
                <a href="/stats/players/1/player1?event=1">Player1</a>
            </span>
            <span class="leader-rating"><span>1.50</span></span>
        </div>
        <div class="leader">
            <span class="leader-name">
                <a href="/stats/players/2/player2?event=1">Player2</a>
            </span>
            <span class="leader-rating"><span>1.50</span></span>
        </div>
        <div class="leader">
            <span class="leader-name">
                <a href="/stats/players/3/player3?event=1">Player3</a>
            </span>
            <span class="leader-rating"><span>1.40</span></span>
        </div>
        """
        entries = parse_leaderboard(html)

        self.assertEqual(len(entries), 3)
        # First two should share position 1
        self.assertEqual(entries[0].position, 1)
        self.assertEqual(entries[1].position, 1)
        # Third should be position 2 (not 3)
        self.assertEqual(entries[2].position, 2)

    def test_parse_leaderboard_sorting(self):
        """Test that entries are sorted by value descending"""
        html = """
        <div class="leader">
            <span class="leader-name">
                <a href="/stats/players/1/low?event=1">Low</a>
            </span>
            <span class="leader-rating"><span>0.80</span></span>
        </div>
        <div class="leader">
            <span class="leader-name">
                <a href="/stats/players/2/high?event=1">High</a>
            </span>
            <span class="leader-rating"><span>1.50</span></span>
        </div>
        """
        entries = parse_leaderboard(html)

        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].name, "High")
        self.assertEqual(entries[0].value, 1.50)
        self.assertEqual(entries[1].name, "Low")
        self.assertEqual(entries[1].value, 0.80)


class TournamentFormatsParserTest(SimpleTestCase):
    """Test HLTV tournament formats parser"""

    def test_parse_formats_from_fixture(self):
        """Test parsing tournament formats from stored HTML fixture."""
        html_file_path = FIXTURES_DIR / "finished_swiss_tournament.html"

        if not html_file_path.exists():
            self.skipTest(f"Fixture not found at: {html_file_path}")

        html_content = html_file_path.read_text()
        stages = parse_tournament_formats(html_content)

        # Print for verification
        print("\n" + "=" * 60)
        print("Parsed Tournament Formats:")
        print("=" * 60)
        for stage in stages:
            print(f"  {stage.name}: {stage.format_type} Bo{stage.best_of}")
        print("=" * 60)

        # Should have at least one stage
        self.assertGreater(len(stages), 0, "Should parse at least one stage")

        # Check structure
        for stage in stages:
            self.assertIsInstance(stage, TournamentStage)
            self.assertIsInstance(stage.name, str)
            self.assertIn(stage.format_type, ["swiss", "bracket"])
            self.assertIn(stage.best_of, [1, 3, 5])

    def test_parse_formats_swiss_detection(self):
        """Test that Swiss format is correctly detected"""
        html = """
        <table class="formats table">
            <tr>
                <th class="format-header">Group stage</th>
                <td class="format-data">Swiss Bo3</td>
            </tr>
        </table>
        """
        stages = parse_tournament_formats(html)

        self.assertEqual(len(stages), 1)
        self.assertEqual(stages[0].name, "Group stage")
        self.assertEqual(stages[0].format_type, "swiss")
        self.assertEqual(stages[0].best_of, 3)

    def test_parse_formats_bracket_detection(self):
        """Test that bracket formats are correctly detected"""
        html = """
        <table class="formats table">
            <tr>
                <th class="format-header">Playoffs</th>
                <td class="format-data">Single elimination Bo3</td>
            </tr>
        </table>
        """
        stages = parse_tournament_formats(html)

        self.assertEqual(len(stages), 1)
        self.assertEqual(stages[0].name, "Playoffs")
        self.assertEqual(stages[0].format_type, "bracket")
        self.assertEqual(stages[0].best_of, 3)

    def test_parse_formats_gsl_detection(self):
        """Test that GSL format is detected as bracket"""
        html = """
        <table class="formats table">
            <tr>
                <th class="format-header">Group stage</th>
                <td class="format-data">GSL Bo1</td>
            </tr>
        </table>
        """
        stages = parse_tournament_formats(html)

        self.assertEqual(len(stages), 1)
        self.assertEqual(stages[0].format_type, "bracket")
        self.assertEqual(stages[0].best_of, 1)

    def test_parse_formats_multiple_stages(self):
        """Test parsing multiple stages"""
        html = """
        <table class="formats table">
            <tr>
                <th class="format-header">Group stage</th>
                <td class="format-data">Swiss Bo1</td>
            </tr>
            <tr>
                <th class="format-header">Playoffs</th>
                <td class="format-data">Single elimination Bo3</td>
            </tr>
        </table>
        """
        stages = parse_tournament_formats(html)

        self.assertEqual(len(stages), 2)
        self.assertEqual(stages[0].name, "Group stage")
        self.assertEqual(stages[0].format_type, "swiss")
        self.assertEqual(stages[1].name, "Playoffs")
        self.assertEqual(stages[1].format_type, "bracket")

    def test_parse_formats_empty_html(self):
        """Test parser handles empty HTML gracefully"""
        stages = parse_tournament_formats("")
        self.assertEqual(stages, [])

    def test_parse_formats_no_table(self):
        """Test parser handles HTML without formats table"""
        html = "<html><body>No formats here</body></html>"
        stages = parse_tournament_formats(html)
        self.assertEqual(stages, [])


class TournamentMetadataParserTest(SimpleTestCase):
    """Test HLTV tournament metadata parser"""

    def test_parse_metadata_from_fixture(self):
        """Test parsing tournament metadata from stored HTML fixture."""
        html_file_path = FIXTURES_DIR / "finished_swiss_tournament.html"

        if not html_file_path.exists():
            self.skipTest(f"Fixture not found at: {html_file_path}")

        html_content = html_file_path.read_text()
        metadata = parse_tournament_metadata(html_content)

        # Print for verification
        print("\n" + "=" * 60)
        print("Parsed Tournament Metadata:")
        print("=" * 60)
        print(f"  Name: {metadata.get('name')}")
        print(f"  Teams: {len(metadata.get('teams', []))}")
        print(f"  Players: {len(metadata.get('players', []))}")
        print(f"  Stages: {len(metadata.get('stages', []))}")
        print(f"  Brackets: {len(metadata.get('brackets', []))}")
        print("=" * 60)

        # Check required fields
        self.assertIn("name", metadata)
        self.assertIn("teams", metadata)
        self.assertIn("players", metadata)
        self.assertIn("stages", metadata)
        self.assertIn("brackets", metadata)

    def test_parse_metadata_includes_stages(self):
        """Test that metadata includes parsed stages"""
        html = """
        <html>
        <div class="event-hub-title">Test Tournament</div>
        <table class="formats table">
            <tr>
                <th class="format-header">Group stage</th>
                <td class="format-data">Swiss Bo3</td>
            </tr>
        </table>
        </html>
        """
        metadata = parse_tournament_metadata(html)

        self.assertEqual(metadata["name"], "Test Tournament")
        self.assertEqual(len(metadata["stages"]), 1)
        self.assertEqual(metadata["stages"][0].name, "Group stage")
        self.assertEqual(metadata["stage_count"], 1)
