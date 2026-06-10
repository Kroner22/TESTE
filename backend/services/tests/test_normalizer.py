from __future__ import annotations

import pytest
from datetime import datetime, timezone

from backend.services.pipeline.odds_normalizer import (
    normalize_sport, normalize_market, normalize_bookmaker,
    normalize_team, normalize_outcome, normalize_event,
    guess_sport_from_league, normalize_sport_for_api, denormalize_sport_from_api,
)


class TestNormalizeSport:
    def test_soccer_aliases(self):
        assert normalize_sport("football") == "soccer"
        assert normalize_sport("soccer") == "soccer"
        assert normalize_sport("Futbol") == "soccer"

    def test_direct_mapping(self):
        assert normalize_sport("basketball") == "basketball"
        assert normalize_sport("tennis") == "tennis"

    def test_american_football(self):
        assert normalize_sport("american_football") == "american_football"
        assert normalize_sport("nfl") == "american_football"

    def test_unknown_sport_preserved(self):
        assert normalize_sport("handball") == "handball"


class TestNormalizeMarket:
    def test_h2h_variants(self):
        assert normalize_market("h2h") == "h2h"
        assert normalize_market("1X2") == "h2h"
        assert normalize_market("match_winner") == "h2h"
        assert normalize_market("moneyline") == "h2h"

    def test_spread_variants(self):
        assert normalize_market("spread") == "spread"
        assert normalize_market("handicap") == "spread"
        assert normalize_market("point_spread") == "spread"

    def test_totals_variants(self):
        assert normalize_market("totals") == "totals"
        assert normalize_market("over_under") == "totals"
        assert normalize_market("ou") == "totals"


class TestNormalizeBookmaker:
    def test_pinnacle_variants(self):
        assert normalize_bookmaker("Pinnacle") == "Pinnacle"
        assert normalize_bookmaker("pinny") == "Pinnacle"

    def test_bet365(self):
        assert normalize_bookmaker("Bet365") == "Bet365"
        assert normalize_bookmaker("bet 365") == "Bet365"

    def test_draftkings(self):
        assert normalize_bookmaker("DraftKings") == "DraftKings"
        assert normalize_bookmaker("DK") == "DraftKings"

    def test_fanduel(self):
        assert normalize_bookmaker("FanDuel") == "FanDuel"
        assert normalize_bookmaker("FD") == "FanDuel"

    def test_unknown_preserved(self):
        assert normalize_bookmaker("UnknownBook") == "unknownbook"


class TestNormalizeTeam:
    def test_strip_fc_suffix(self):
        assert normalize_team("Barcelona FC") == "Barcelona"
        assert normalize_team("FC Barcelona") == "Barcelona"

    def test_strip_cf(self):
        assert normalize_team("Real Madrid CF") == "Real Madrid"

    def test_strip_parentheses(self):
        assert normalize_team("Team A (1X2)") == "Team A"

    def test_collapse_spaces(self):
        assert normalize_team("  Team   A  ") == "Team A"

    def test_short_acronym_suffix(self):
        assert normalize_team("LA Lakers") == "LA Lakers"
        assert normalize_team("Boston NBA") == "Boston"

    def test_already_clean(self):
        assert normalize_team("Arsenal") == "Arsenal"


class TestNormalizeOutcome:
    def test_home_variants(self):
        assert normalize_outcome("home") == "home"
        assert normalize_outcome("1") == "home"
        assert normalize_outcome("H") == "home"
        assert normalize_outcome("local") == "home"

    def test_away_variants(self):
        assert normalize_outcome("away") == "away"
        assert normalize_outcome("2") == "away"
        assert normalize_outcome("A") == "away"

    def test_draw_variants(self):
        assert normalize_outcome("draw") == "draw"
        assert normalize_outcome("X") == "draw"
        assert normalize_outcome("tie") == "draw"

    def test_over_under(self):
        assert normalize_outcome("over") == "over"
        assert normalize_outcome("under") == "under"
        assert normalize_outcome("O") == "over"
        assert normalize_outcome("U") == "under"


class TestGuessSportFromLeague:
    def test_soccer_leagues(self):
        assert guess_sport_from_league("Premier League") == "soccer"
        assert guess_sport_from_league("Champions League") == "soccer"
        assert guess_sport_from_league("La Liga") == "soccer"

    def test_basketball(self):
        assert guess_sport_from_league("NBA") == "basketball"
        assert guess_sport_from_league("Euroleague") == "basketball"

    def test_tennis(self):
        assert guess_sport_from_league("ATP Finals") == "tennis"
        assert guess_sport_from_league("Wimbledon") == "tennis"

    def test_american_football(self):
        assert guess_sport_from_league("NFL") == "american_football"

    def test_unknown(self):
        assert guess_sport_from_league("Unknown Tournament") is None


class TestNormalizeEvent:
    def test_basic_normalization(self):
        result = normalize_event("soccer", "FC Barcelona", "Real Madrid CF", "La Liga")
        assert result.sport == "soccer"
        assert result.home_team == "Barcelona"
        assert result.away_team == "Real Madrid"
        assert result.confidence > 0.8

    def test_sport_guessed_from_league(self):
        result = normalize_event("unknown", "Team A", "Team B", "Premier League")
        assert result.sport == "soccer"


class TestApiConversion:
    def test_sport_for_api(self):
        assert normalize_sport_for_api("american_football") == "americanfootball"
        assert normalize_sport_for_api("soccer") == "soccer"

    def test_denormalize_from_api(self):
        assert denormalize_sport_from_api("americanfootball") == "american_football"
        assert denormalize_sport_from_api("icehockey") == "hockey"
