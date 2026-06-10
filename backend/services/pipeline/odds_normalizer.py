from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


NORMALIZED_SPORTS = {
    "soccer", "football", "basketball", "tennis",
    "americanfootball", "baseball", "hockey", "mma", "boxing",
    "cricket", "rugby", "handball", "volleyball", "darts", "snooker",
}

SPORT_ALIASES: dict[str, str] = {
    "football": "soccer",
    "futbol": "soccer",
    "calcio": "soccer",
    "fußball": "soccer",
    "soccer": "soccer",
    "basketball": "basketball",
    "baloncesto": "basketball",
    "basquetebol": "basketball",
    "tennis": "tennis",
    "tenis": "tennis",
    "americanfootball": "american_football",
    "american football": "american_football",
    "nfl": "american_football",
    "baseball": "baseball",
    "hockey": "hockey",
    "ice hockey": "hockey",
    "mma": "mma",
    "boxing": "boxing",
    "cricket": "cricket",
    "rugby": "rugby",
}

MARKET_MAP: dict[str, str] = {
    "h2h": "h2h",
    "1x2": "h2h",
    "win": "h2h",
    "match_winner": "h2h",
    "match winner": "h2h",
    "moneyline": "h2h",
    "spread": "spread",
    "handicap": "spread",
    "point_spread": "spread",
    "point spread": "spread",
    "totals": "totals",
    "over_under": "totals",
    "over/under": "totals",
    "ou": "totals",
    "total_points": "totals",
}

BOOKMAKER_MAP: dict[str, str] = {
    "pinnacle": "Pinnacle",
    "pinny": "Pinnacle",
    "bet365": "Bet365",
    "bet 365": "Bet365",
    "betfair": "Betfair",
    "betfair exchange": "Betfair",
    "draftkings": "DraftKings",
    "dk": "DraftKings",
    "fanduel": "FanDuel",
    "fan duel": "FanDuel",
    "fd": "FanDuel",
    "betway": "Betway",
    "bet way": "Betway",
    "william hill": "WilliamHill",
    "williamhill": "WilliamHill",
    "unibet": "Unibet",
    "betmgm": "BetMGM",
    "bet mgm": "BetMGM",
    "mgm": "BetMGM",
    "pointsbet": "PointsBet",
    "points bet": "PointsBet",
    "betrivers": "BetRivers",
    "bet rivers": "BetRivers",
    "rivers": "BetRivers",
    "888sport": "888sport",
    "888 sport": "888sport",
    "sport888": "888sport",
    "bwin": "Bwin",
    "bwinbet": "Bwin",
    "sportingbet": "SportingBet",
    "sporting bet": "SportingBet",
}

TEAM_CLEANUP_PATTERNS = [
    (r'\s+(FC|CF|SC|AFC|US)$', ''),
    (r'^(FC|CF|SC|AFC)\s+', ''),
    (r'\s+United\s+(FC|CF)$', ' United'),
    (r'\s+-\s+', ' '),
    (r'\s*\([^)]*\)\s*', ' '),
    (r'"', ''),
    (r'\s{2,}', ' '),
]

ACRONYM_SUFFIXES = {"FC", "CF", "SC", "AFC", "NBA", "NFL", "MLB", "NHL", "UFC", "ATP", "WTA"}


@dataclass
class NormalizedEvent:
    raw_sport: str
    raw_home: str
    raw_away: str
    raw_league: str
    sport: str
    home_team: str
    away_team: str
    league: str
    confidence: float


def normalize_sport(raw: str) -> str:
    cleaned = raw.strip().lower().replace("_", " ").replace("-", " ")
    return SPORT_ALIASES.get(cleaned, cleaned)


def normalize_market(raw: str) -> str:
    cleaned = raw.strip().lower().replace("_", " ").replace("-", " ")
    cleaned_snake = raw.strip().lower().replace(" ", "_").replace("-", "_")
    return MARKET_MAP.get(cleaned) or MARKET_MAP.get(cleaned_snake) or cleaned


def normalize_bookmaker(raw: str) -> str:
    cleaned = raw.strip().lower().replace("_", " ").replace("-", " ")
    return BOOKMAKER_MAP.get(cleaned, cleaned)


def normalize_team(raw: str) -> str:
    name = raw.strip()
    for pattern, replacement in TEAM_CLEANUP_PATTERNS:
        name = re.sub(pattern, replacement, name)
    name = name.strip()
    parts = name.split()
    if len(parts) > 1 and parts[-1] in ACRONYM_SUFFIXES:
        name = " ".join(parts[:-1])
    return name


def guess_sport_from_league(league: str) -> Optional[str]:
    league_lower = league.lower()
    mapping: list[tuple[re.Pattern, str]] = [
        (re.compile(r'premier\s*league|epl|champions\s*league|la\s*liga|serie\s*a|bundesliga|ligue\s*1|eredivisie|primeira\s*liga'), "soccer"),
        (re.compile(r'nba|euroleague|basketball'), "basketball"),
        (re.compile(r'atp|wta|grand\s*slam|us\s*open|wimbledon|roland\s*garros|australian\s*open'), "tennis"),
        (re.compile(r'nfl|super\s* bowl|american\s*football'), "american_football"),
        (re.compile(r'nhl|stanley\s*cup'), "hockey"),
        (re.compile(r'mlb|world\s*series|baseball'), "baseball"),
        (re.compile(r'ufc|mma|bellator'), "mma"),
    ]
    for pattern, sport in mapping:
        if pattern.search(league_lower):
            return sport
    return None


def normalize_event(
    sport: str,
    home: str,
    away: str,
    league: str = "",
) -> NormalizedEvent:
    ns = normalize_sport(sport)

    # If sport didn't normalize to a known value, try guessing from league
    if ns not in NORMALIZED_SPORTS and league:
        guessed = guess_sport_from_league(league)
        if guessed:
            ns = guessed

    nh = normalize_team(home)
    na = normalize_team(away)
    nl = league.strip()

    name_sim = _compute_name_similarity(home.strip(), nh)

    return NormalizedEvent(
        raw_sport=sport,
        raw_home=home,
        raw_away=away,
        raw_league=league,
        sport=ns,
        home_team=nh,
        away_team=na,
        league=nl,
        confidence=name_sim,
    )


def _compute_name_similarity(original: str, normalized: str) -> float:
    if original.lower() == normalized.lower():
        return 1.0
    if original.lower().replace(" ", "") == normalized.lower().replace(" ", ""):
        return 0.95
    return 0.85


def normalize_outcome(outcome: str) -> str:
    cleaned = outcome.strip().lower()
    mapping = {
        "home": "home", "1": "home", "h": "home", "local": "home",
        "away": "away", "2": "away", "a": "away", "visitor": "away",
        "draw": "draw", "x": "draw", "tie": "draw",
        "over": "over", "o": "over",
        "under": "under", "u": "under",
    }
    return mapping.get(cleaned, cleaned)


def normalize_sport_for_api(sport: str) -> str:
    mapping: dict[str, str] = {
        "soccer": "soccer",
        "basketball": "basketball",
        "tennis": "tennis",
        "american_football": "americanfootball",
        "baseball": "baseball",
        "hockey": "icehockey",
        "mma": "mma",
        "boxing": "boxing",
    }
    return mapping.get(sport, sport)


def denormalize_sport_from_api(api_sport: str) -> str:
    known_bases: dict[str, str] = {
        "soccer": "soccer",
        "basketball": "basketball",
        "tennis": "tennis",
        "americanfootball": "american_football",
        "baseball": "baseball",
        "icehockey": "hockey",
        "mma": "mma",
        "boxing": "boxing",
        "aussierules": "aussierules",
        "cricket": "cricket",
        "golf": "golf",
        "handball": "handball",
        "lacrosse": "lacrosse",
        "politics": "politics",
        "rugbyleague": "rugbyleague",
    }
    direct = known_bases.get(api_sport)
    if direct:
        return direct
    base = api_sport.split("_")[0] if "_" in api_sport else api_sport
    return known_bases.get(base, base)
