"""
Database Growth Monitor — Phase 4
==================================
Generates hourly snapshots of real-market table counts.

Usage:
    python -m backend.monitor_growth          # single snapshot
    python -m backend.monitor_growth --watch   # every 60 min
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, ".")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from backend.app.database import SessionLocal, init_db
from backend.app.models.real_market import (
    RealMarketEvent, RealMarketOdds, RealMarketOpportunity,
    RealMarketPaperTrade, RealMarketClvRecord, RealMarketSnapshot,
)

from backend.app.models.real_market import init_real_market_tables
init_db()
init_real_market_tables()


def snapshot() -> dict:
    db = SessionLocal()
    counts = {
        "real_market_events": db.query(RealMarketEvent).count(),
        "real_market_odds": db.query(RealMarketOdds).count(),
        "real_market_opportunities": db.query(RealMarketOpportunity).count(),
        "real_market_paper_trades": db.query(RealMarketPaperTrade).count(),
        "real_market_clv_records": db.query(RealMarketClvRecord).count(),
        "real_market_snapshots": db.query(RealMarketSnapshot).count(),
    }
    db.close()
    return counts


def print_snapshot(counts: dict, label: str = ""):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"\n[{ts}] {label}")
    print(f"  {'Table':40s} {'Count':>8s}")
    print(f"  {'-'*40} {'-'*8}")
    for table, count in counts.items():
        print(f"  {table:40s} {count:>8d}")


if __name__ == "__main__":
    watch = "--watch" in sys.argv or "-w" in sys.argv

    if watch:
        interval = 3600
        print(f"Growth monitor: snapshot every {interval}s. Ctrl+C to stop.")
        while True:
            counts = snapshot()
            print_snapshot(counts, "Hourly snapshot")
            time.sleep(interval)
    else:
        counts = snapshot()
        print_snapshot(counts, "Single snapshot")
