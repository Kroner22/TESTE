from __future__ import annotations

import math
import time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Callable, Awaitable

from backend.app.database import SessionLocal, PaperTradeRecord
from backend.app.log_config import get_logger

logger = get_logger(__name__)


class PaperPosition:
    position_id: str
    event_id: str
    market: str
    outcome: str
    bookmaker: str
    entry_odd: float
    entry_prob: float
    entry_ev: float
    stake: float
    entry_timestamp: float
    is_open: bool
    exit_odd: Optional[float]
    exit_timestamp: Optional[float]
    pnl: Optional[float]
    pnl_pct: Optional[float]
    confidence: float
    kelly_fraction: float

    def __init__(self, position_id: str, event_id: str, market: str, outcome: str, bookmaker: str, entry_odd: float, entry_ev: float, stake: float, entry_timestamp: float, confidence: float = 0.0, kelly_fraction: float = 0.25):
        self.position_id = position_id
        self.event_id = event_id
        self.market = market
        self.outcome = outcome
        self.bookmaker = bookmaker
        self.entry_odd = entry_odd
        self.entry_prob = 1.0 / entry_odd if entry_odd > 1 else 0.0
        self.entry_ev = entry_ev
        self.stake = stake
        self.entry_timestamp = entry_timestamp
        self.is_open = True
        self.exit_odd = None
        self.exit_timestamp = None
        self.pnl = None
        self.pnl_pct = None
        self.confidence = confidence
        self.kelly_fraction = kelly_fraction

    def close(self, exit_odd: float, exit_timestamp: float):
        self.exit_odd = exit_odd
        self.exit_timestamp = exit_timestamp
        self.is_open = False

        actual_prob = 1.0 / exit_odd if exit_odd > 1 else 0.0

        if actual_prob > self.entry_prob:
            self.pnl = self.stake * (self.entry_odd - 1)
        else:
            self.pnl = -self.stake

        self.pnl_pct = (self.pnl / self.stake) * 100 if self.stake > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "position_id": self.position_id,
            "event_id": self.event_id,
            "market": self.market,
            "outcome": self.outcome,
            "bookmaker": self.bookmaker,
            "entry_odd": self.entry_odd,
            "entry_ev": self.entry_ev,
            "stake": self.stake,
            "is_open": self.is_open,
            "pnl": round(self.pnl, 2) if self.pnl is not None else None,
            "pnl_pct": round(self.pnl_pct, 2) if self.pnl_pct is not None else None,
            "duration_hours": round((self.exit_timestamp - self.entry_timestamp) / 3600, 1) if self.exit_timestamp and self.entry_timestamp else None,
        }


class PaperTradingEngine:
    """
    Full paper trading simulation.

    Features:
    - Position management (open/close)
    - Bankroll tracking with configurable initial capital
    - Kelly fraction stake sizing
    - PnL computation per position and total
    - Order history with timestamps
    - Batch close for stale positions
    - Performance metrics: Sharpe, drawdown, hit rate
    """

    def __init__(self, initial_bankroll: float = 1000.0):
        self._initial_bankroll = initial_bankroll
        self._bankroll = initial_bankroll
        self._peak_bankroll = initial_bankroll
        self._positions: dict[str, PaperPosition] = {}
        self._closed_positions: list[PaperPosition] = []
        self._position_counter = 0
        self._max_concurrent = 20
        self._max_stake_pct = 0.05
        self._broadcast_callback: Optional[Callable[[dict], Awaitable[None]]] = None

    def set_broadcast_callback(self, callback: Callable[[dict], Awaitable[None]]):
        self._broadcast_callback = callback

    @property
    def bankroll(self) -> float:
        return self._bankroll

    @property
    def total_pnl(self) -> float:
        return self._bankroll - self._initial_bankroll

    @property
    def roi_pct(self) -> float:
        return (self.total_pnl / self._initial_bankroll) * 100 if self._initial_bankroll > 0 else 0.0

    @property
    def drawdown_pct(self) -> float:
        if self._peak_bankroll <= 0:
            return 0.0
        return ((self._peak_bankroll - self._bankroll) / self._peak_bankroll) * 100

    def open_position(self, event_id: str, market: str, outcome: str, bookmaker: str, entry_odd: float, entry_ev: float, confidence: float = 0.0, kelly_fraction: float = 0.25) -> Optional[PaperPosition]:
        open_count = sum(1 for p in self._positions.values() if p.is_open)
        if open_count >= self._max_concurrent:
            logger.warning("paper_trading_max_positions", count=self._max_concurrent)
            return None

        stake = self._compute_stake(entry_ev, confidence, entry_odd)
        self._position_counter += 1
        position_id = f"pos_{self._position_counter}_{int(time.time())}"

        position = PaperPosition(
            position_id=position_id,
            event_id=event_id,
            market=market,
            outcome=outcome,
            bookmaker=bookmaker,
            entry_odd=entry_odd,
            entry_ev=entry_ev,
            stake=stake,
            entry_timestamp=time.time(),
            confidence=confidence,
            kelly_fraction=kelly_fraction,
        )

        self._bankroll -= stake
        self._positions[position_id] = position

        self._persist_position(position)

        logger.info("paper_position_opened", pos=position_id, event_id=event_id, stake=round(stake, 2), bankroll=round(self._bankroll, 2))

        if self._broadcast_callback:
            import asyncio
            asyncio.ensure_future(self._broadcast_callback({
                "type": "paper_trade",
                "data": {
                    "action": "open",
                    "position_id": position_id,
                    "event_id": event_id,
                    "outcome": outcome,
                    "entry_odd": entry_odd,
                    "stake": round(stake, 2),
                    "entry_ev": round(entry_ev, 4),
                    "bankroll": round(self._bankroll, 2),
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))

        return position

    def close_position(self, position_id: str, exit_odd: float) -> Optional[PaperPosition]:
        position = self._positions.get(position_id)
        if not position or not position.is_open:
            return None

        position.close(exit_odd, time.time())
        self._bankroll += (position.stake + (position.pnl or 0))
        if self._bankroll > self._peak_bankroll:
            self._peak_bankroll = self._bankroll

        self._closed_positions.append(position)
        self._update_position_in_db(position)

        logger.info("paper_position_closed", pos=position_id, pnl=round(position.pnl or 0, 2), bankroll=round(self._bankroll, 2))

        if self._broadcast_callback:
            import asyncio
            asyncio.ensure_future(self._broadcast_callback({
                "type": "paper_trade",
                "data": {
                    "action": "close",
                    "position_id": position_id,
                    "event_id": position.event_id,
                    "entry_odd": position.entry_odd,
                    "exit_odd": exit_odd,
                    "pnl": round(position.pnl or 0, 2),
                    "pnl_pct": round(position.pnl_pct or 0, 2),
                    "bankroll": round(self._bankroll, 2),
                    "duration_hours": round((position.exit_timestamp - position.entry_timestamp) / 3600, 1),
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))

        return position

    def get_open_positions(self) -> list[PaperPosition]:
        return [p for p in self._positions.values() if p.is_open]

    def get_closed_positions(self) -> list[PaperPosition]:
        return list(self._closed_positions)

    def get_position(self, position_id: str) -> Optional[PaperPosition]:
        return self._positions.get(position_id)

    def close_stale_positions(self, max_age_hours: float = 24.0, exit_odd: float = 1.0):
        now = time.time()
        for pos in self.get_open_positions():
            age_hours = (now - pos.entry_timestamp) / 3600
            if age_hours > max_age_hours:
                self.close_position(pos.position_id, exit_odd)

    def get_performance_summary(self) -> dict:
        closed = self._closed_positions
        n = len(closed)

        if n == 0:
            return {
                "total_positions": 0,
                "open_positions": len(self.get_open_positions()),
                "bankroll": round(self._bankroll, 2),
                "total_pnl": round(self.total_pnl, 2),
                "roi_pct": round(self.roi_pct, 2),
                "drawdown_pct": round(self.drawdown_pct, 2),
                "hit_rate": 0.0,
                "avg_pnl": 0.0,
                "sharpe_ratio": 0.0,
            }

        pnls = [p.pnl or 0 for p in closed]
        wins = [p for p in closed if (p.pnl or 0) > 0]
        losses = [p for p in closed if (p.pnl or 0) <= 0]

        avg_pnl = sum(pnls) / n
        hit_rate = len(wins) / n * 100

        if len(pnls) > 1:
            std_pnl = (sum((p - avg_pnl) ** 2 for p in pnls) / (n - 1)) ** 0.5
            sharpe = (avg_pnl / std_pnl) * (252 ** 0.5) if std_pnl > 0 else 0
        else:
            sharpe = 0.0

        return {
            "total_positions": n,
            "open_positions": len(self.get_open_positions()),
            "bankroll": round(self._bankroll, 2),
            "total_pnl": round(self.total_pnl, 2),
            "roi_pct": round(self.roi_pct, 2),
            "drawdown_pct": round(self.drawdown_pct, 2),
            "hit_rate": round(hit_rate, 1),
            "avg_pnl": round(avg_pnl, 2),
            "wins": len(wins),
            "losses": len(losses),
            "sharpe_ratio": round(sharpe, 2),
        }

    def load_from_db(self):
        """Load open positions from database on startup."""
        db = SessionLocal()
        try:
            open_positions = db.query(PaperTradeRecord).filter(
                PaperTradeRecord.is_open == True
            ).all()
            for rec in open_positions:
                pos = PaperPosition(
                    position_id=rec.position_id,
                    event_id=rec.event_id,
                    market=rec.market,
                    outcome=rec.outcome,
                    bookmaker=rec.bookmaker,
                    entry_odd=float(rec.entry_odd),
                    entry_ev=float(rec.entry_ev or 0),
                    stake=float(rec.stake),
                    entry_timestamp=rec.entry_timestamp.timestamp(),
                    confidence=float(rec.confidence or 0),
                    kelly_fraction=float(rec.kelly_fraction or 0.25),
                )
                pos.is_open = True
                self._positions[pos.position_id] = pos
                self._bankroll -= pos.stake

            self._position_counter = len(open_positions)
            if open_positions:
                logger.info("paper_trades_loaded_from_db", count=len(open_positions))
        except Exception as e:
            logger.error("paper_trades_load_failed", error=str(e))
        finally:
            db.close()

    def _persist_position(self, position: PaperPosition):
        db = SessionLocal()
        try:
            rec = PaperTradeRecord(
                position_id=position.position_id,
                event_id=position.event_id,
                market=position.market,
                outcome=position.outcome,
                bookmaker=position.bookmaker,
                entry_odd=Decimal(str(position.entry_odd)),
                entry_ev=Decimal(str(position.entry_ev)),
                stake=Decimal(str(position.stake)),
                entry_timestamp=datetime.fromtimestamp(position.entry_timestamp, tz=timezone.utc),
                is_open=True,
                confidence=Decimal(str(position.confidence)),
                kelly_fraction=Decimal(str(position.kelly_fraction)),
            )
            db.add(rec)
            db.commit()
        except Exception as e:
            logger.error("paper_trade_persist_failed", pos=position.position_id, error=str(e))
        finally:
            db.close()

    def _update_position_in_db(self, position: PaperPosition):
        db = SessionLocal()
        try:
            rec = db.query(PaperTradeRecord).filter(
                PaperTradeRecord.position_id == position.position_id
            ).first()
            if rec:
                rec.is_open = False
                rec.exit_odd = Decimal(str(position.exit_odd)) if position.exit_odd else None
                rec.exit_timestamp = datetime.fromtimestamp(position.exit_timestamp, tz=timezone.utc) if position.exit_timestamp else None
                rec.pnl = Decimal(str(position.pnl)) if position.pnl is not None else None
                rec.pnl_pct = Decimal(str(position.pnl_pct)) if position.pnl_pct is not None else None
                db.commit()
        except Exception as e:
            logger.error("paper_trade_update_failed", pos=position.position_id, error=str(e))
        finally:
            db.close()

    def _compute_stake(self, entry_ev: float, confidence: float, entry_odd: float) -> float:
        if entry_odd <= 1:
            return 0.0
        kelly = (entry_ev * 100) / (entry_odd - 1) if entry_odd > 1 else 0
        kelly = max(0.0, min(kelly, self._max_stake_pct))
        kelly *= confidence
        stake = self._bankroll * min(kelly, self._max_stake_pct)
        return min(stake, self._bankroll * 0.1)
