"""
Autonomous Collection Engine — Phase 1
=======================================
Continuous collector that fetches real-market data from The Odds API,
tracks odds over time for CLV computation, generates paper trades, and
produces daily research reports.

Usage:
    python -m backend.research.collector          # single pass
    python -m backend.research.collector --watch   # continuous loop
    python -m backend.research.collector --hours 168  # run for 7 days then stop

Not modifying any platform code — this is a standalone research tool.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time as time_mod
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API_KEY = os.getenv("THE_ODDS_API_KEY", "")
API_BASE = "https://api.the-odds-api.com/v4"
REGIONS = ["us", "uk", "eu", "au"]
MARKETS = ["h2h", "spreads", "totals"]

# Target sports that reliably return odds data (confirmed in Phase 2)
TARGET_SPORTS = [
    "americanfootball_cfl",
    "americanfootball_ncaaf",
    "americanfootball_nfl",
    "americanfootball_nfl_preseason",
    "americanfootball_ufl",
    "aussierules_afl",
    "baseball_kbo",
    "baseball_milb",
    "baseball_mlb",
    "baseball_ncaa",
]

# --- DB setup ---
from backend.app.database import engine, SessionLocal, init_db
from backend.app.models.real_market import (
    init_real_market_tables,
    RealMarketEvent,
    RealMarketOdds,
    RealMarketPaperTrade,
    RealMarketClvRecord,
    RealMarketSnapshot,
    RealMarketOpportunity,
)
from backend.app.models.real_market import Base

init_db()
init_real_market_tables()

# Ensure research tables exist (we add our own tracking if needed)
_research_base = Base

import aiohttp

logger = print


async def _fetch_json(session, path, params=None):
    url = f"{API_BASE}{path}"
    p = {"apiKey": API_KEY, **(params or {})}
    try:
        async with session.get(url, params=p, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 429:
                logger(f"[RATE LIMITED] {path}")
                return None
            if resp.status == 401:
                logger(f"[AUTH FAILED] {path} — check API key")
                return None
            if resp.status != 200:
                return None
            return await resp.json()
    except Exception as e:
        logger(f"[ERROR] {path}: {e}")
        return None


async def _fetch_list(session, path, params=None):
    result = await _fetch_json(session, path, params)
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return [result]
    return []


def _get_db():
    return SessionLocal()


class RequestTracker:
    """Tracks API request count to respect rate limits."""
    def __init__(self, limit=500):
        self.count = 0
        self.limit = limit
        self._load()

    def _load(self):
        p = Path(__file__).parent / ".api_usage.json"
        if p.exists():
            try:
                data = json.loads(p.read_text())
                if data.get("date") == datetime.now(timezone.utc).strftime("%Y-%m"):
                    self.count = data.get("count", 0)
            except Exception:
                pass

    def _save(self):
        p = Path(__file__).parent / ".api_usage.json"
        try:
            p.write_text(json.dumps({
                "date": datetime.now(timezone.utc).strftime("%Y-%m"),
                "count": self.count,
            }))
        except Exception:
            pass

    def add(self, n=1):
        self.count += n
        self._save()

    @property
    def remaining(self):
        return self.limit - self.count

    @property
    def ok(self):
        return self.remaining > 0


# ============================================================
#  PHASE 1: COLLECTION
# ============================================================

async def collect_events(session, tracker: RequestTracker) -> dict:
    """Fetch events for all target sports. Returns {sport_key: [fixtures]}."""
    if not tracker.ok:
        logger(f"[SKIP] API quota near limit ({tracker.remaining} remaining)")
        return {}

    all_events: dict[str, list] = {}

    for sport_key in TARGET_SPORTS:
        if not tracker.ok:
            break
        fixtures = await _fetch_list(session, f"/sports/{sport_key}/events", {
            "regions": ",".join(REGIONS[:2]),
        })
        tracker.add(1)
        if fixtures:
            all_events[sport_key] = fixtures
        await asyncio.sleep(0.3)

    event_count = sum(len(v) for v in all_events.values())
    logger(f"[COLLECT] Events: {event_count} from {len(all_events)} sports (API: {tracker.count})")

    return all_events


async def collect_odds(session, tracker: RequestTracker, all_events: dict, existing_event_ids: set, force_refresh: bool = False) -> int:
    """
    Fetch odds for events. Returns count of odds stored.
    If force_refresh=True, fetches for ALL events (existing + new).
    """
    if not tracker.ok:
        return 0

    odds_stored = 0
    db = _get_db()
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

    for sport_key, fixtures in all_events.items():
        for fxt in fixtures:
            eid = fxt.get("id", "")
            if not force_refresh and eid in existing_event_ids:
                continue
            if not tracker.ok:
                break

            odds_data = await _fetch_json(
                session,
                f"/sports/{sport_key}/events/{eid}/odds",
                {"regions": ",".join(REGIONS), "markets": ",".join(MARKETS)},
            )
            tracker.add(1)
            if not odds_data or not isinstance(odds_data, dict):
                continue

            bookmakers = odds_data.get("bookmakers", [])
            for bm in bookmakers:
                bm_name = bm.get("title", "Unknown")
                markets = bm.get("markets", [])
                for mkt in markets:
                    mkt_key = mkt.get("key", "h2h")
                    outcomes = mkt.get("outcomes", [])
                    for outcome in outcomes:
                        rec = RealMarketOdds(
                            event_id=eid,
                            market=mkt_key,
                            outcome=outcome.get("name", ""),
                            bookmaker=bm_name,
                            odd=Decimal(str(outcome.get("price", 2.0))),
                            market_type="real",
                            provider_source=f"the_odds_api/{sport_key}",
                            timestamp=now_naive,
                            is_real_market=True,
                        )
                        db.add(rec)
                        odds_stored += 1
            db.commit()
            await asyncio.sleep(0.3)

        if not tracker.ok:
            break

    db.close()
    if odds_stored:
        logger(f"[COLLECT] Odds stored: {odds_stored} (API: {tracker.count})")
    return odds_stored


# ============================================================
#  PHASE 3: CLV COMPUTATION
# ============================================================

def compute_clv() -> dict:
    """
    Compute CLV for all events that have started.
    For each (event_id, bookmaker, market, outcome):
      - Opening odd = earliest timestamp
      - Closing odd = latest timestamp before event start
    CLV% = (closing - opening) / opening * 100
    """
    db = _get_db()
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

    # Find events that have started
    started_events = db.query(RealMarketEvent).filter(
        RealMarketEvent.start_time < now_naive
    ).all()

    results = []
    stored_clv = 0

    for evt in started_events:
        eid = evt.event_id

        # Get all odds for this event, ordered by timestamp
        odds_rows = db.query(RealMarketOdds).filter(
            RealMarketOdds.event_id == eid,
            RealMarketOdds.timestamp < evt.start_time,
        ).order_by(RealMarketOdds.timestamp).all()

        if len(odds_rows) < 2:
            continue

        # Group by (bookmaker, market, outcome)
        groups: dict[tuple, list] = defaultdict(list)
        for row in odds_rows:
            key = (row.bookmaker, row.market, row.outcome)
            groups[key].append(row)

        for key, rows in groups.items():
            bm, market, outcome = key
            rows_sorted = sorted(rows, key=lambda r: r.timestamp)
            opening = rows_sorted[0]
            closing = rows_sorted[-1]

            if opening.odd == 0 or closing.odd == 0:
                continue

            clv_pct = (float(closing.odd) - float(opening.odd)) / float(opening.odd) * 100

            # Store CLV record
            existing = db.query(RealMarketClvRecord).filter(
                RealMarketClvRecord.event_id == eid,
                RealMarketClvRecord.bookmaker == bm,
                RealMarketClvRecord.market == market,
                RealMarketClvRecord.outcome == outcome,
            ).first()
            if not existing:
                rec = RealMarketClvRecord(
                    event_id=eid,
                    market=market,
                    outcome=outcome,
                    bookmaker=bm,
                    entry_odd=opening.odd,
                    closing_odd=closing.odd,
                    entry_timestamp=opening.timestamp,
                    closing_timestamp=closing.timestamp,
                    clv_pct=Decimal(str(round(clv_pct, 4))),
                    market_type="real",
                    provider_source=f"the_odds_api",
                    is_real_market=True,
                    closing_source="sportsbook",
                )
                db.add(rec)
                stored_clv += 1

            results.append({
                "event_id": eid,
                "bookmaker": bm,
                "market": market,
                "outcome": outcome,
                "opening_odd": float(opening.odd),
                "closing_odd": float(closing.odd),
                "clv_pct": round(clv_pct, 4),
            })

    db.commit()
    db.close()

    if stored_clv:
        logger(f"[CLV] Records generated: {stored_clv} (from {len(started_events)} events)")
    return {
        "clv_records_generated": stored_clv,
        "events_analyzed": len(started_events),
        "total_clv_records": len(results),
    }


# ============================================================
#  PHASE 4: PAPER TRADE SIMULATION
# ============================================================

def simulate_paper_trades() -> dict:
    """
    Simulate paper trades using market-consensus EV.
    For each event/bookmaker/outcome:
      - Market consensus = average implied probability across all bookmakers
      - EV = consensus_prob * decimal_odds - 1
      - If EV > 2% → place paper trade (stake = 1 unit)
      - Track P&L at closing odds
    """
    db = _get_db()
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    trades_opened = 0

    # Get events with odds that haven't been paper-traded yet
    existing_trade_events = set(
        r[0] for r in db.query(RealMarketPaperTrade.event_id).distinct().all()
    )

    events_with_odds = db.query(RealMarketOdds.event_id).distinct().all()
    event_ids = [r[0] for r in events_with_odds if r[0] not in existing_trade_events]

    for eid in event_ids:
        # Get all odds for this event
        all_odds = db.query(RealMarketOdds).filter(
            RealMarketOdds.event_id == eid
        ).all()
        if not all_odds:
            continue

        # Compute market consensus per (market, outcome)
        consensus: dict[tuple, list] = defaultdict(list)
        for row in all_odds:
            if row.odd > 0:
                consensus[(row.market, row.outcome)].append(float(row.odd))

        fair_probs: dict[tuple, float] = {}
        for key, odds_list in consensus.items():
            avg_odd = sum(odds_list) / len(odds_list)
            fair_probs[key] = 1.0 / avg_odd if avg_odd > 0 else 0

        # Find positive EV trades
        trade_seq = 0
        for row in all_odds:
            key = (row.market, row.outcome)
            fair_prob = fair_probs.get(key, 0)
            if fair_prob <= 0:
                continue
            decimal_odd = float(row.odd)
            ev = fair_prob * decimal_odd - 1

            if ev > 0.02:  # 2% EV threshold
                trade_seq += 1
                position_id = f"paper_{eid}_{row.bookmaker}_{row.market}_{row.outcome}_{int(now_naive.timestamp())}_{trade_seq}"
                # Check if this position already exists
                existing = db.query(RealMarketPaperTrade).filter(
                    RealMarketPaperTrade.position_id == position_id
                ).first()
                if existing:
                    continue
                trade = RealMarketPaperTrade(
                    position_id=position_id,
                    event_id=eid,
                    market=row.market,
                    outcome=row.outcome,
                    bookmaker=row.bookmaker,
                    entry_odd=row.odd,
                    entry_ev=Decimal(str(round(ev, 4))),
                    stake=Decimal("1.00"),
                    market_type="real",
                    provider_source="the_odds_api",
                    is_open=True,
                    is_real_market=True,
                )
                db.add(trade)
                trades_opened += 1

        db.commit()

    # Now close any trades for events that have started
    closed_trades = 0
    open_trades = db.query(RealMarketPaperTrade).filter(
        RealMarketPaperTrade.is_open == True
    ).all()

    for trade in open_trades:
        # Find closing odds for this event/bookmaker/market/outcome
        evt = db.query(RealMarketEvent).filter(
            RealMarketEvent.event_id == trade.event_id
        ).first()
        if not evt or (evt.start_time and evt.start_time >= now_naive):
            continue

        # Get latest odds before event start for this combo
        closing_odds = db.query(RealMarketOdds).filter(
            RealMarketOdds.event_id == trade.event_id,
            RealMarketOdds.bookmaker == trade.bookmaker,
            RealMarketOdds.market == trade.market,
            RealMarketOdds.outcome == trade.outcome,
            RealMarketOdds.timestamp < evt.start_time,
        ).order_by(RealMarketOdds.timestamp.desc()).first()

        if closing_odds:
            exit_odd = float(closing_odds.odd)
            entry_odd = float(trade.entry_odd)
            pnl = (exit_odd / entry_odd - 1) * float(trade.stake)
            trade.is_open = False
            trade.exit_odd = closing_odds.odd
            trade.exit_timestamp = datetime.now(timezone.utc)
            trade.pnl = Decimal(str(round(pnl, 4)))
            trade.pnl_pct = Decimal(str(round(pnl / float(trade.stake) * 100, 4)))
            closed_trades += 1

    db.commit()
    db.close()

    if trades_opened or closed_trades:
        logger(f"[PAPER] Opened: {trades_opened}, Closed: {closed_trades}")
    return {"opened": trades_opened, "closed": closed_trades}


# ============================================================
#  PHASE 1: SNAPSHOT
# ============================================================

def take_snapshot() -> dict:
    """Record point-in-time snapshot of real-market state."""
    db = _get_db()
    now = datetime.now(timezone.utc)

    events = db.query(RealMarketEvent).count()
    odds = db.query(RealMarketOdds).count()
    opportunities = db.query(RealMarketOpportunity).count()
    trades = db.query(RealMarketPaperTrade).count()
    clv = db.query(RealMarketClvRecord).count()

    snapshot_id = f"snap_{now.strftime('%Y%m%d_%H%M%S')}"
    snap = RealMarketSnapshot(
        snapshot_id=snapshot_id,
        timestamp=now,
        market_type="real",
        event_count=events,
        total_odds_points=odds,
        total_opportunities=opportunities,
        provider_count=len(TARGET_SPORTS),
        snapshot_json=json.dumps({
            "events": events,
            "odds": odds,
            "opportunities": opportunities,
            "trades": trades,
            "clv_records": clv,
        }),
    )
    db.add(snap)
    db.commit()
    db.close()

    return {
        "snapshot_id": snapshot_id,
        "events": events,
        "odds": odds,
        "opportunities": opportunities,
        "trades": trades,
        "clv_records": clv,
    }


# ============================================================
#  PHASE 2: DAILY REPORT
# ============================================================

DAILY_REPORT_DIR = Path(__file__).parent / "daily_reports"

def generate_daily_report() -> dict:
    """Generate and store daily report."""
    DAILY_REPORT_DIR.mkdir(exist_ok=True)
    db = _get_db()
    now = datetime.now(timezone.utc)

    day_num = (now - datetime(2026, 6, 5, tzinfo=timezone.utc)).days + 1
    day_label = f"DAY_{day_num}"

    events = db.query(RealMarketEvent).count()
    odds = db.query(RealMarketOdds).count()
    trades = db.query(RealMarketPaperTrade).count()
    clv = db.query(RealMarketClvRecord).count()

    sports = [r[0] for r in db.query(RealMarketEvent.sport).distinct().all()]
    bookmakers = [r[0] for r in db.query(RealMarketOdds.bookmaker).distinct().all()]

    trades_open = db.query(RealMarketPaperTrade).filter(
        RealMarketPaperTrade.is_open == True
    ).count()
    trades_closed = db.query(RealMarketPaperTrade).filter(
        RealMarketPaperTrade.is_open == False
    ).count()

    report = {
        "day": day_label,
        "date": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "events_collected": events,
        "odds_collected": odds,
        "bookmakers_seen": len(bookmakers),
        "sports_seen": len(sports),
        "paper_trades_opened": trades_open + trades_closed,
        "paper_trades_closed": trades_closed,
        "paper_trades_open": trades_open,
        "clv_records_generated": clv,
    }

    report_path = DAILY_REPORT_DIR / f"{day_label}.json"
    report_path.write_text(json.dumps(report, indent=2))
    logger(f"[REPORT] {day_label}: events={events} odds={odds} trades={trades_open+trades_closed} clv={clv}")

    db.close()
    return report


# ============================================================
#  MAIN COLLECTION LOOP
# ============================================================

async def collect_once(session, tracker: RequestTracker, existing_ids: set, force_refresh: bool = False):
    """Single pass of the collection cycle."""
    all_events = await collect_events(session, tracker)
    if all_events:
        # Filter to events starting within next 48 hours (API conservation)
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        window = timedelta(hours=48)
        filtered_events: dict[str, list] = {}
        for sport_key, fixtures in all_events.items():
            recent = []
            for fxt in fixtures:
                start_str = fxt.get("commence_time", "")
                try:
                    start = datetime.fromisoformat(start_str.replace("Z", "+00:00")).replace(tzinfo=None) if start_str else now_naive
                    if start < now_naive + window and start >= now_naive - timedelta(hours=6):
                        recent.append(fxt)
                except Exception:
                    recent.append(fxt)
            if recent:
                filtered_events[sport_key] = recent
        logger(f"[FILTER] Events within 48h: {sum(len(v) for v in filtered_events.values())}")
        await collect_odds(session, tracker, filtered_events, existing_ids, force_refresh=force_refresh)
    clv_result = compute_clv()
    paper_result = simulate_paper_trades()
    snapshot = take_snapshot()
    return {
        "events": sum(len(v) for v in all_events.values()) if all_events else 0,
        "odds_stored": 0,
        "clv": clv_result,
        "paper": paper_result,
        "snapshot": snapshot,
    }


async def main_loop(run_hours: float = 0):
    """
    Main collection loop.
    - Fetches events + odds on each cycle
    - Computes CLV for started events
    - Simulates paper trades
    - Records snapshots
    - Generates daily reports
    """
    if not API_KEY or API_KEY == "your_api_key_here":
        logger("[FATAL] THE_ODDS_API_KEY not configured")
        return

    tracker = RequestTracker(limit=500)
    start_time = datetime.now(timezone.utc)
    end_time = start_time + timedelta(hours=run_hours) if run_hours > 0 else None

    day_count = 0
    last_day_report = None

    logger(f"[START] Longitudinal collector — target: {TARGET_SPORTS}")
    logger(f"[START] API remaining: {tracker.remaining}")
    logger(f"[START] End time: {end_time or 'manual stop'}")

    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        cycle = 0
        while True:
            now = datetime.now(timezone.utc)
            if end_time and now >= end_time:
                logger(f"[STOP] Collection period ended ({run_hours}h)")
                break

            cycle += 1
            logger(f"\n{'='*60}")
            logger(f"[CYCLE {cycle}] {now.isoformat()} [{tracker.count} API calls used]")

            # Get existing event IDs
            db = _get_db()
            existing_ids = set(r[0] for r in db.query(RealMarketEvent.event_id).all())
            db.close()

            # Even cycles do full refresh; odd cycles do events-only
            force_refresh = (cycle % 2 == 0)
            result = await collect_once(session, tracker, existing_ids, force_refresh=force_refresh)

            # Daily report
            day_num = (datetime.now(timezone.utc) - datetime(2026, 6, 5, tzinfo=timezone.utc)).days
            if day_num != last_day_report:
                generate_daily_report()
                last_day_report = day_num
                day_count += 1

            # Sleep: 12h between cycles (2 cycles/day)
            cycle_interval = 12 * 3600
            logger(f"[SLEEP] Next cycle in {cycle_interval}s (API remaining: {tracker.remaining})")
            if tracker.remaining < 10:
                logger(f"[WARN] API quota nearly exhausted — consider upgrading tier")
            await asyncio.sleep(cycle_interval)


# ============================================================
#  ENTRY POINT
# ============================================================

if __name__ == "__main__":
    watch = "--watch" in sys.argv or "-w" in sys.argv
    hours = 0
    for arg in sys.argv:
        if arg.startswith("--hours="):
            hours = float(arg.split("=")[1])
        elif arg.startswith("--days="):
            hours = float(arg.split("=")[1]) * 24

    if watch or hours > 0:
        asyncio.run(main_loop(run_hours=hours))
    else:
        async def single_pass():
            tracker = RequestTracker(limit=500)
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                db = _get_db()
                existing_ids = set(r[0] for r in db.query(RealMarketEvent.event_id).all())
                db.close()
                result = await collect_once(session, tracker, existing_ids)
                generate_daily_report()
                logger(f"\n[DONE] Single pass complete. API usage: {tracker.count}")
        asyncio.run(single_pass())
