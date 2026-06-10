from __future__ import annotations

import math
import random
import time
from collections import defaultdict
from typing import Optional

from backend.app.log_config import get_logger

logger = get_logger(__name__)


class EmulatedProvider:
    name: str
    base_weight: float
    latency_ms: float
    noise_std: float

    def __init__(self, name: str, base_weight: float, latency_ms: float, noise_std: float):
        self.name = name
        self.base_weight = base_weight
        self.latency_ms = latency_ms
        self.noise_std = noise_std


class EmulatedMarketEvent:
    event_id: str
    home_team: str
    away_team: str
    sport: str
    league: str
    market: str
    base_odds: list[float]
    outcomes: list[str]
    hours_to_start: float

    def __init__(self, event_id: str, home_team: str, away_team: str, sport: str, league: str, market: str, base_odds: list[float], outcomes: list[str], hours_to_start: float):
        self.event_id = event_id
        self.home_team = home_team
        self.away_team = away_team
        self.sport = sport
        self.league = league
        self.market = market
        self.base_odds = base_odds
        self.outcomes = outcomes
        self.hours_to_start = hours_to_start


class MarketEmulator:
    """
    Generates realistic market behavior patterns when no live feed is available.

    Patterns:
    - Brownian drift (existing)
    - Spike patterns (odds jump and revert)
    - Correction bursts (sharp movement followed by correction)
    - Liquidity shocks (sudden volatility expansion)
    - Steam moves (coordinated moves across providers)
    """

    PATTERNS = ["brownian", "spike", "correction", "liquidity_shock", "steam"]

    def __init__(self, seed: int = 42):
        self._rng = random.Random(seed)
        self._drift_states: dict[str, dict[int, float]] = defaultdict(dict)
        self._current_pattern: str = "brownian"
        self._pattern_timer: float = time.time()
        self._pattern_duration: float = self._rng.uniform(10.0, 30.0)
        self._spike_active: dict[str, bool] = defaultdict(bool)
        self._spike_targets: dict[str, float] = {}

        self._providers: list[EmulatedProvider] = [
            EmulatedProvider("Betano", 1.00, 15.0, 0.003),
            EmulatedProvider("bet365", 0.95, 25.0, 0.004),
            EmulatedProvider("Sportingbet", 0.90, 40.0, 0.005),
            EmulatedProvider("Bwin", 0.90, 35.0, 0.004),
            EmulatedProvider("Betfair", 0.98, 10.0, 0.002),
        ]

        self._events: list[EmulatedMarketEvent] = []
        self._init_events()

    def _init_events(self):
        sports = [
            ("Flamengo", "Palmeiras", "soccer", "Brasileirão Série A"),
            ("Real Madrid", "Barcelona", "soccer", "La Liga"),
            ("Manchester City", "Arsenal", "soccer", "Premier League"),
            ("Lakers", "Celtics", "basketball", "NBA"),
            ("Djokovic", "Alcaraz", "tennis", "ATP Finals"),
            ("Chiefs", "49ers", "american_football", "NFL"),
        ]

        for i, (home, away, sport, league) in enumerate(sports):
            eid = f"em_{i}"
            prob = self._rng.uniform(0.35, 0.55)
            prob2 = self._rng.uniform(0.20, 0.35)
            prob3 = 1.0 - prob - prob2
            probs = [prob, prob2, prob3]
            base_odds = [round(1.0 / p, 2) for p in probs]
            base_odds = [max(1.01, o) for o in base_odds]

            self._events.append(EmulatedMarketEvent(
                event_id=eid,
                home_team=home,
                away_team=away,
                sport=sport,
                league=league,
                market="1X2",
                base_odds=base_odds,
                outcomes=["home", "draw", "away"],
                hours_to_start=self._rng.uniform(1.0, 48.0),
            ))

    def set_pattern(self, pattern: str):
        if pattern in self.PATTERNS:
            self._current_pattern = pattern
            self._pattern_timer = time.time()
            self._pattern_duration = self._rng.uniform(8.0, 20.0)
            logger.info("emulator_pattern_changed", pattern=pattern, duration=self._pattern_duration)

    def get_providers(self) -> list[EmulatedProvider]:
        return self._providers

    def get_events(self) -> list[EmulatedMarketEvent]:
        return self._events

    def generate_odds(self, event: EmulatedMarketEvent, tick: int) -> list[tuple[str, str, float]]:
        """
        Generate (provider, outcome, odd) tuples for this event at this tick.
        """
        self._maybe_switch_pattern()
        results = []

        for provider in self._providers:
            for idx, outcome in enumerate(event.outcomes):
                odd = self._compute_odd(event, provider, idx, tick)
                results.append((provider.name, outcome, round(odd, 2)))

        return results

    def _compute_odd(self, event: EmulatedMarketEvent, provider: EmulatedProvider, outcome_idx: int, tick: int) -> float:
        base = event.base_odds[outcome_idx]
        state_key = f"{event.event_id}:{provider.name}:{outcome_idx}"
        prior = self._drift_states[state_key].get(tick - 1, base)

        pattern = self._current_pattern

        if pattern == "spike" and outcome_idx == self._rng.randint(0, len(event.outcomes) - 1):
            spike_key = f"spike:{state_key}"
            if not self._spike_active.get(spike_key, False):
                if self._rng.random() < 0.05:
                    direction = 1 if self._rng.random() > 0.5 else -1
                    spike_mag = base * 0.02 * direction
                    self._spike_active[spike_key] = True
                    self._spike_targets[spike_key] = prior + spike_mag
                    return round(prior + spike_mag, 2)

            if self._spike_active.get(spike_key, False):
                target = self._spike_targets.get(spike_key, prior)
                reversion = (target - prior) * 0.3
                new_val = prior + reversion
                if abs(new_val - prior) < base * 0.001:
                    self._spike_active[spike_key] = False
                    return round(prior, 2)
                return round(new_val, 2)

        if pattern == "steam":
            if outcome_idx == 0 and self._rng.random() < 0.03:
                steam_dir = 1 if self._rng.random() > 0.5 else -1
                steam_mag = base * 0.015 * steam_dir
                return round(prior + steam_mag, 2)

        if pattern == "liquidity_shock":
            noise_std = provider.noise_std * 5.0
        else:
            noise_std = provider.noise_std

        drift = self._rng.gauss(0, noise_std * base)
        hours_factor = max(0.1, event.hours_to_start)
        time_drift = (base * 0.0001) / hours_factor
        new_val = prior + drift + time_drift
        new_val = max(1.01, min(50.0, new_val))

        return new_val

    def _maybe_switch_pattern(self):
        now = time.time()
        if now - self._pattern_timer > self._pattern_duration:
            self._current_pattern = self._rng.choice(self.PATTERNS)
            self._pattern_timer = now
            self._pattern_duration = self._rng.uniform(10.0, 30.0)
            self._spike_active.clear()
            self._spike_targets.clear()
            logger.info("emulator_pattern_auto_switch", pattern=self._current_pattern)
