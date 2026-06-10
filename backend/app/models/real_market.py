"""
Real-market data models — segregated storage for market-authentic data.

These models exist alongside the original (simulation) models to
provide strict data segregation between simulated and real data.
No statistical contamination is allowed.

When operating in HYBRID or REAL_MARKET mode, opportunities, trades,
CLV records, and snapshots from real providers are stored here with
market_type = "real" and full provenance tracking.

The original models are left UNCHANGED per the non-modification rule.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Numeric, Text,
    Boolean, ForeignKey, Index, create_engine,
)
from sqlalchemy.orm import DeclarativeBase

from backend.app.database import Base
from backend.app.database import DB_PATH, engine as main_engine


class RealMarketEvent(Base):
    """Real market event — sourced from a real provider API."""

    __tablename__ = "real_market_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), unique=True, nullable=False, index=True)
    sport = Column(String(32), nullable=False)
    home_team = Column(String(128), nullable=False)
    away_team = Column(String(128), nullable=False)
    start_time = Column(DateTime, nullable=False)
    market_type = Column(String(16), default="real")  # real, hybrid
    provider_source = Column(String(64), nullable=False)
    provider_timestamp = Column(DateTime, nullable=True)
    status = Column(String(16), default="scheduled")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class RealMarketOdds(Base):
    """Real market odds — each row is a single bookmaker/outcome/odd."""

    __tablename__ = "real_market_odds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), ForeignKey("real_market_events.event_id"), nullable=False, index=True)
    market = Column(String(32), nullable=False)
    outcome = Column(String(64), nullable=False)
    bookmaker = Column(String(64), nullable=False)
    odd = Column(Numeric(10, 4), nullable=False)
    market_type = Column(String(16), default="real")
    provider_source = Column(String(64), nullable=False)
    latency_ms = Column(Numeric(10, 2), nullable=True)
    provider_timestamp = Column(DateTime, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_opening = Column(Boolean, default=False)
    is_closing = Column(Boolean, default=False)
    is_real_market = Column(Boolean, default=True)

    __table_args__ = (
        Index("idx_real_odds_event_market", "event_id", "market"),
    )


class RealMarketOpportunity(Base):
    """Real market opportunity — EV edge detected from real data."""

    __tablename__ = "real_market_opportunities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), ForeignKey("real_market_events.event_id"), nullable=False)
    market = Column(String(32), nullable=False)
    outcome = Column(String(64), nullable=False)
    bookmaker = Column(String(64), nullable=False)
    odd = Column(Numeric(10, 4), nullable=False)
    implied_prob = Column(Numeric(8, 4))
    fair_prob = Column(Numeric(8, 4))
    ev = Column(Numeric(10, 4))
    edge_score = Column(Numeric(8, 4))
    confidence_score = Column(Numeric(8, 4))
    kelly_stake = Column(Numeric(10, 4))
    value_grade = Column(String(16))
    risk_level = Column(String(16))
    market_type = Column(String(16), default="real")
    provider_source = Column(String(64), nullable=False)
    detected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)
    is_real_market = Column(Boolean, default=True)

    __table_args__ = (
        Index("idx_real_opp_event_active", "event_id", "is_active"),
    )


class RealMarketPaperTrade(Base):
    """Real market paper trade — trade executed on real market data."""

    __tablename__ = "real_market_paper_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    position_id = Column(String(64), unique=True, nullable=False, index=True)
    event_id = Column(String(64), nullable=False)
    market = Column(String(32), nullable=False)
    outcome = Column(String(64), nullable=False)
    bookmaker = Column(String(64), nullable=False)
    entry_odd = Column(Numeric(10, 4), nullable=False)
    entry_ev = Column(Numeric(10, 4))
    stake = Column(Numeric(10, 4), nullable=False)
    market_type = Column(String(16), default="real")
    provider_source = Column(String(64), nullable=False)
    entry_timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_open = Column(Boolean, default=True)
    exit_odd = Column(Numeric(10, 4), nullable=True)
    exit_timestamp = Column(DateTime, nullable=True)
    pnl = Column(Numeric(10, 4), nullable=True)
    pnl_pct = Column(Numeric(8, 4), nullable=True)
    confidence = Column(Numeric(8, 4), default=0)
    kelly_fraction = Column(Numeric(8, 4), default=0.25)
    is_real_market = Column(Boolean, default=True)
    # Execution realism tracking
    execution_delay_ms = Column(Numeric(10, 2), nullable=True)
    slippage_pct = Column(Numeric(8, 4), nullable=True)
    quote_stale_at_entry = Column(Boolean, default=False)
    market_depth_at_entry = Column(Numeric(10, 4), nullable=True)


class RealMarketClvRecord(Base):
    """Real market CLV — closing line value from real market data."""

    __tablename__ = "real_market_clv_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), nullable=False, index=True)
    market = Column(String(32), nullable=False)
    outcome = Column(String(64), nullable=False)
    bookmaker = Column(String(64), nullable=False)
    entry_odd = Column(Numeric(10, 4), nullable=False)
    closing_odd = Column(Numeric(10, 4), nullable=False)
    entry_timestamp = Column(DateTime, nullable=False)
    closing_timestamp = Column(DateTime, nullable=False)
    clv_pct = Column(Numeric(10, 4), nullable=False)
    clv_grade = Column(String(16))
    simulated_ev = Column(Numeric(10, 4))
    timing_efficiency = Column(String(16))
    hours_to_close = Column(Numeric(8, 2))
    market_type = Column(String(16), default="real")
    provider_source = Column(String(64), nullable=False)
    is_real_market = Column(Boolean, default=True)
    closing_source = Column(String(32), default="sportsbook")  # sportsbook, exchange, consensus
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class RealMarketSnapshot(Base):
    """Real market snapshot — point-in-time real market state."""

    __tablename__ = "real_market_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_id = Column(String(64), unique=True, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False)
    market_type = Column(String(16), default="real")
    provider_count = Column(Integer, default=0)
    total_odds_points = Column(Integer, default=0)
    total_opportunities = Column(Integer, default=0)
    event_count = Column(Integer, default=0)
    provider_quality_scores = Column(Text, nullable=True)
    provider_latency_ms = Column(Text, nullable=True)
    provider_reliability_scores = Column(Text, nullable=True)
    market_capture_delay_ms = Column(Numeric(10, 2), nullable=True)
    snapshot_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def init_real_market_tables():
    """Create real-market tables if they don't exist."""
    from backend.app.database import engine
    Base.metadata.create_all(bind=engine, tables=[
        RealMarketEvent.__table__,
        RealMarketOdds.__table__,
        RealMarketOpportunity.__table__,
        RealMarketPaperTrade.__table__,
        RealMarketClvRecord.__table__,
        RealMarketSnapshot.__table__,
    ])
