from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Numeric, Text,
    Boolean, ForeignKey, Index, create_engine, event as sa_event,
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column,
    relationship, Session, sessionmaker,
)

DB_PATH = os.getenv("MVP_DB_PATH", "data/mvp.db")
os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False,
)


@sa_event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), unique=True, nullable=False, index=True)
    sport = Column(String(32), nullable=False)
    home_team = Column(String(128), nullable=False)
    away_team = Column(String(128), nullable=False)
    start_time = Column(DateTime, nullable=False)
    status = Column(String(16), default="scheduled")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    odds = relationship("OddsRecord", back_populates="event", cascade="all, delete-orphan")
    opportunities = relationship("OpportunityRecord", back_populates="event", cascade="all, delete-orphan")


class OddsRecord(Base):
    __tablename__ = "odds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), ForeignKey("events.event_id"), nullable=False)
    market = Column(String(32), nullable=False)
    outcome = Column(String(64), nullable=False)
    bookmaker = Column(String(64), nullable=False)
    odd = Column(Numeric(10, 4), nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_opening = Column(Boolean, default=False)
    is_closing = Column(Boolean, default=False)

    event = relationship("Event", back_populates="odds")

    __table_args__ = (
        Index("idx_odds_event_market", "event_id", "market"),
        Index("idx_odds_event_bookmaker", "event_id", "bookmaker"),
    )


class OpportunityRecord(Base):
    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), ForeignKey("events.event_id"), nullable=False)
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
    detected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)

    event = relationship("Event", back_populates="opportunities")

    __table_args__ = (
        Index("idx_opp_event_active", "event_id", "is_active"),
    )


class AlertRecord(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), ForeignKey("events.event_id"), nullable=False)
    alert_type = Column(String(32), nullable=False)
    severity = Column(String(16), nullable=False)
    message = Column(Text, nullable=False)
    ev_value = Column(Numeric(10, 4))
    odd_old = Column(Numeric(10, 4))
    odd_new = Column(Numeric(10, 4))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    acknowledged = Column(Boolean, default=False)


class PaperTradeRecord(Base):
    __tablename__ = "paper_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    position_id = Column(String(64), unique=True, nullable=False, index=True)
    event_id = Column(String(64), nullable=False)
    market = Column(String(32), nullable=False)
    outcome = Column(String(64), nullable=False)
    bookmaker = Column(String(64), nullable=False)
    entry_odd = Column(Numeric(10, 4), nullable=False)
    entry_ev = Column(Numeric(10, 4))
    stake = Column(Numeric(10, 4), nullable=False)
    entry_timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_open = Column(Boolean, default=True)
    exit_odd = Column(Numeric(10, 4), nullable=True)
    exit_timestamp = Column(DateTime, nullable=True)
    pnl = Column(Numeric(10, 4), nullable=True)
    pnl_pct = Column(Numeric(8, 4), nullable=True)
    confidence = Column(Numeric(8, 4), default=0)
    kelly_fraction = Column(Numeric(8, 4), default=0.25)


class ClvRecordPersistence(Base):
    __tablename__ = "clv_records"

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class MarketSnapshotRecord(Base):
    __tablename__ = "market_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_id = Column(String(64), unique=True, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False)
    provider_count = Column(Integer, default=0)
    total_odds_points = Column(Integer, default=0)
    total_opportunities = Column(Integer, default=0)
    event_count = Column(Integer, default=0)
    snapshot_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ProviderTelemetryRecord(Base):
    __tablename__ = "provider_telemetry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_name = Column(String(64), nullable=False, index=True)
    event = Column(String(32), nullable=False)
    healthy = Column(Boolean, default=True)
    failure_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    consecutive_failures = Column(Integer, default=0)
    latency_ms = Column(Numeric(10, 2), nullable=True)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def init_db():
    Base.metadata.create_all(bind=engine)
