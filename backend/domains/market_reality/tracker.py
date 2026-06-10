from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from .models import OddsTick, OddsTimeSeries


class OddsTracker:
    """
    Tracks odds ticks over time, building time series per
    (event, market, outcome, bookmaker) key.
    """

    def __init__(self):
        self._series: dict[str, OddsTimeSeries] = {}

    def _key(self, event_id: str, market: str, outcome: str, bookmaker: str) -> str:
        return f"{event_id}:{market}:{outcome}:{bookmaker}"

    def record_tick(
        self,
        event_id: str,
        market: str,
        outcome: str,
        bookmaker: str,
        odd: Decimal,
        timestamp: Optional[datetime] = None,
        is_opening: bool = False,
        is_closing: bool = False,
    ) -> OddsTick:
        ts = timestamp or datetime.now(timezone.utc)
        tick = OddsTick(
            event_id=event_id,
            market=market,
            outcome=outcome,
            bookmaker=bookmaker,
            odd=odd,
            timestamp=ts,
            is_opening=is_opening,
            is_closing=is_closing,
        )
        key = self._key(event_id, market, outcome, bookmaker)
        if key not in self._series:
            self._series[key] = OddsTimeSeries(
                event_id=event_id,
                market=market,
                outcome=outcome,
                bookmaker=bookmaker,
            )
        self._series[key].ticks.append(tick)
        return tick

    def get_series(
        self,
        event_id: str,
        market: str,
        outcome: str,
        bookmaker: str,
    ) -> Optional[OddsTimeSeries]:
        return self._series.get(self._key(event_id, market, outcome, bookmaker))

    def get_series_for_event(self, event_id: str) -> list[OddsTimeSeries]:
        return [s for k, s in self._series.items() if k.startswith(f"{event_id}:")]

    def get_series_for_market(self, event_id: str, market: str) -> list[OddsTimeSeries]:
        return [s for k, s in self._series.items() if k.startswith(f"{event_id}:{market}:")]

    def get_all_series(self) -> list[OddsTimeSeries]:
        return list(self._series.values())

    def ticks_since(
        self,
        event_id: str,
        market: str,
        since: datetime,
    ) -> list[OddsTick]:
        ticks = []
        for s in self.get_series_for_market(event_id, market):
            for t in s.ticks:
                if t.timestamp >= since:
                    ticks.append(t)
        return sorted(ticks, key=lambda t: t.timestamp)

    def latest_tick(
        self,
        event_id: str,
        market: str,
        outcome: str,
        bookmaker: str,
    ) -> Optional[OddsTick]:
        series = self.get_series(event_id, market, outcome, bookmaker)
        if not series or not series.ticks:
            return None
        return series.ticks[-1]

    def remove_series(self, event_id: str) -> int:
        to_remove = [k for k in self._series if k.startswith(f"{event_id}:")]
        for k in to_remove:
            del self._series[k]
        return len(to_remove)

    def clear(self):
        self._series.clear()

    @property
    def series_count(self) -> int:
        return len(self._series)

    def build_synthetic_series(
        self,
        event_id: str,
        market: str,
        outcome: str,
        bookmaker: str,
        opening_odd: Decimal,
        closing_odd: Decimal,
        num_ticks: int = 20,
        open_hours_before: float = 48.0,
        seed: int = 42,
    ) -> OddsTimeSeries:
        import random
        rng = random.Random(seed)

        base = datetime.now(timezone.utc)
        series = OddsTimeSeries(
            event_id=event_id,
            market=market,
            outcome=outcome,
            bookmaker=bookmaker,
        )

        for i in range(num_ticks):
            frac = i / (num_ticks - 1) if num_ticks > 1 else 0
            noise = rng.gauss(0, 0.005)
            drift = float(opening_odd) + (float(closing_odd) - float(opening_odd)) * frac
            odd_val = drift * (1 + noise)
            odd_val = max(1.01, odd_val)
            odd = Decimal(str(round(odd_val, 2)))

            ts = base.replace(hour=0, minute=0, second=0, microsecond=0)
            ts = ts.replace(hour=min(int(frac * 24), 23))

            tick = OddsTick(
                event_id=event_id,
                market=market,
                outcome=outcome,
                bookmaker=bookmaker,
                odd=odd,
                timestamp=ts,
                is_opening=(i == 0),
                is_closing=(i == num_ticks - 1),
            )
            series.ticks.append(tick)

        key = self._key(event_id, market, outcome, bookmaker)
        self._series[key] = series
        return series
