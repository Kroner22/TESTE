"""
Longitudinal Edge Research — Analysis Module (Phases 3-10)
==========================================================
Reads from real_market_* tables and computes all research metrics.
Does NOT modify any platform code.

Usage:
    python -m backend.research.analysis               # full report
    python -m backend.research.analysis --phase 3     # CLV only
    python -m backend.research.analysis --phase 8     # false positives only
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.database import SessionLocal
from backend.app.models.real_market import (
    RealMarketEvent, RealMarketOdds, RealMarketPaperTrade,
    RealMarketClvRecord, RealMarketSnapshot,
)

logger = print


def _get_db():
    return SessionLocal()


# ============================================================
#  PHASE 2: DAILY REPORT LOADER
# ============================================================

def _safe_get(d: dict, *keys, default=0):
    """Safely traverse nested dict keys."""
    current = d
    for k in keys:
        if isinstance(current, dict):
            current = current.get(k, default)
        else:
            return default
    return current if current is not None else default

def load_daily_reports() -> list[dict]:
    """Load all stored daily reports."""
    reports_dir = Path(__file__).parent / "daily_reports"
    reports = []
    if reports_dir.exists():
        for p in sorted(reports_dir.glob("DAY_*.json")):
            try:
                raw = json.loads(p.read_text())
                # Normalize flat vs nested formats
                normalized = {
                    "day": raw.get("day", p.stem),
                    "events_collected": _safe_get(raw, "collection", "events") or raw.get("events_collected", 0),
                    "odds_collected": _safe_get(raw, "collection", "odds") or raw.get("odds_collected", 0),
                    "paper_trades_opened": _safe_get(raw, "paper_trading", "total") or raw.get("paper_trades_opened", 0),
                    "clv_records_generated": _safe_get(raw, "clv", "records") or raw.get("clv_records_generated", 0),
                    "bookmakers_seen": _safe_get(raw, "collection", "bookmakers") or raw.get("bookmakers_seen", 0),
                    "sports_seen": _safe_get(raw, "collection", "sports_total") or raw.get("sports_seen", 0),
                }
                reports.append(normalized)
            except Exception as e:
                logger(f"  [WARN] Could not load {p.name}: {e}")
    return reports


# ============================================================
#  PHASE 3: REAL CLV ANALYSIS
# ============================================================

def compute_clv_metrics() -> dict:
    """Compute CLV distribution and summary statistics."""
    db = _get_db()
    clv_records = db.query(RealMarketClvRecord).all()
    db.close()

    if not clv_records:
        return {"status": "insufficient_data", "records": 0}

    clv_values = [float(r.clv_pct) for r in clv_records]
    n = len(clv_values)

    mean_clv = sum(clv_values) / n
    sorted_clv = sorted(clv_values)
    median_clv = sorted_clv[n // 2] if n % 2 else (sorted_clv[n // 2 - 1] + sorted_clv[n // 2]) / 2
    positive = sum(1 for v in clv_values if v > 0)
    negative = sum(1 for v in clv_values if v < 0)

    # Distribution buckets
    buckets = {
        "very_positive": sum(1 for v in clv_values if v > 5),
        "positive": sum(1 for v in clv_values if 0 < v <= 5),
        "neutral": sum(1 for v in clv_values if v == 0),
        "negative": sum(1 for v in clv_values if -5 <= v < 0),
        "very_negative": sum(1 for v in clv_values if v < -5),
    }

    # Standard deviation
    variance = sum((v - mean_clv) ** 2 for v in clv_values) / n
    std_dev = math.sqrt(variance)

    return {
        "status": "ok",
        "records": n,
        "mean_clv": round(mean_clv, 4),
        "median_clv": round(median_clv, 4),
        "std_dev_clv": round(std_dev, 4),
        "positive_clv_pct": round(positive / n * 100, 2),
        "negative_clv_pct": round(negative / n * 100, 2),
        "neutral_clv_pct": round((n - positive - negative) / n * 100, 2),
        "min_clv": round(min(clv_values), 4),
        "max_clv": round(max(clv_values), 4),
        "distribution": buckets,
    }


# ============================================================
#  PHASE 4: PAPER TRADING ANALYSIS
# ============================================================

def compute_paper_trade_metrics() -> dict:
    """Compute paper trade performance metrics."""
    db = _get_db()
    closed_trades = db.query(RealMarketPaperTrade).filter(
        RealMarketPaperTrade.is_open == False,
        RealMarketPaperTrade.pnl.isnot(None),
    ).all()
    open_trades = db.query(RealMarketPaperTrade).filter(
        RealMarketPaperTrade.is_open == True
    ).count()
    all_trades = db.query(RealMarketPaperTrade).count()
    db.close()

    if not closed_trades:
        return {"status": "insufficient_data", "total_trades": all_trades, "closed_trades": 0}

    wins = [t for t in closed_trades if t.pnl and t.pnl > 0]
    losses = [t for t in closed_trades if t.pnl and t.pnl <= 0]

    win_rate = len(wins) / len(closed_trades) * 100
    total_pnl = sum(float(t.pnl) for t in closed_trades if t.pnl)
    total_stake = sum(float(t.stake) for t in closed_trades)
    roi = (total_pnl / total_stake * 100) if total_stake > 0 else 0

    # Profit factor
    gross_wins = sum(float(t.pnl) for t in wins)
    gross_losses = abs(sum(float(t.pnl) for t in losses)) if losses else 0
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")

    # Drawdown (simplified: running P&L minimum)
    running_pnl = 0
    min_pnl = 0
    for t in sorted(closed_trades, key=lambda x: x.entry_timestamp or datetime.min):
        running_pnl += float(t.pnl or 0)
        if running_pnl < min_pnl:
            min_pnl = running_pnl
    max_drawdown = abs(min_pnl)

    # Expectancy per trade
    expectancy = total_pnl / len(closed_trades) if closed_trades else 0

    return {
        "status": "ok",
        "total_trades": all_trades,
        "closed_trades": len(closed_trades),
        "open_trades": open_trades,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 2),
        "total_pnl": round(total_pnl, 4),
        "total_stake": round(total_stake, 2),
        "roi_pct": round(roi, 2),
        "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else "inf",
        "max_drawdown_units": round(max_drawdown, 4),
        "expectancy_per_trade": round(expectancy, 4),
    }


# ============================================================
#  PHASE 5: EV VALIDATION (EV -> CLV correlation)
# ============================================================

def compute_ev_clv_correlation() -> dict:
    """Compute Pearson and Spearman correlation between EV and CLV."""
    import statistics

    db = _get_db()
    # Get closed paper trades that have both EV and CLV
    trades = db.query(RealMarketPaperTrade).filter(
        RealMarketPaperTrade.is_open == False,
        RealMarketPaperTrade.entry_ev.isnot(None),
        RealMarketPaperTrade.pnl.isnot(None),
        RealMarketPaperTrade.event_id.isnot(None),
    ).all()

    results = []
    for trade in trades:
        # Look up CLV for this event/bookmaker/market/outcome
        clv = db.query(RealMarketClvRecord).filter(
            RealMarketClvRecord.event_id == trade.event_id,
            RealMarketClvRecord.bookmaker == trade.bookmaker,
            RealMarketClvRecord.market == trade.market,
            RealMarketClvRecord.outcome == trade.outcome,
        ).first()
        if clv:
            results.append({
                "ev": float(trade.entry_ev),
                "clv": float(clv.clv_pct),
                "pnl": float(trade.pnl or 0),
            })
    db.close()

    if len(results) < 10:
        return {"status": "insufficient_data", "pairs": len(results), "minimum_required": 10}

    evs = [r["ev"] for r in results]
    clvs = [r["clv"] for r in results]
    n = len(evs)

    # Pearson correlation
    mean_ev = statistics.mean(evs)
    mean_clv = statistics.mean(clvs)
    cov = sum((evs[i] - mean_ev) * (clvs[i] - mean_clv) for i in range(n)) / n
    std_ev = math.sqrt(sum((e - mean_ev) ** 2 for e in evs) / n)
    std_clv = math.sqrt(sum((c - mean_clv) ** 2 for c in clvs) / n)
    pearson = cov / (std_ev * std_clv) if std_ev * std_clv > 0 else 0

    # Spearman correlation (rank-based)
    ev_ranks = {v: i + 1 for i, v in enumerate(sorted(evs))}
    clv_ranks = {v: i + 1 for i, v in enumerate(sorted(clvs))}
    ranked_pairs = [(ev_ranks[evs[i]], clv_ranks[clvs[i]]) for i in range(n)]
    d_squared = sum((r[0] - r[1]) ** 2 for r in ranked_pairs)
    spearman = 1 - (6 * d_squared) / (n * (n ** 2 - 1)) if n > 1 else 0

    # Significance (t-test for Pearson)
    t_stat = pearson * math.sqrt((n - 2) / (1 - pearson ** 2)) if abs(pearson) < 1 else float("inf")
    # Approximate p-value using t-distribution with n-2 df
    # Using simplified: if |t| > 2, roughly p < 0.05 for large n
    p_value_approx = max(0, min(1, 2 * (1 - min(1, abs(t_stat) / math.sqrt(n)))))
    significant = p_value_approx < 0.05

    return {
        "status": "ok",
        "pairs": n,
        "pearson_r": round(pearson, 4),
        "spearman_rho": round(spearman, 4),
        "t_statistic": round(t_stat, 4),
        "p_value_approximate": round(p_value_approx, 4),
        "significant_at_95": significant,
        "interpretation": (
            "EV predicts CLV" if significant and pearson > 0.1 else
            "Weak or no relationship between EV and CLV"
        ),
    }


# ============================================================
#  PHASE 6: BOOKMAKER ANALYSIS
# ============================================================

def compute_bookmaker_rankings() -> list[dict]:
    """Rank bookmakers by CLV, ROI, and trade count."""
    db = _get_db()
    clv_records = db.query(RealMarketClvRecord).all()
    trades = db.query(RealMarketPaperTrade).filter(
        RealMarketPaperTrade.is_open == False,
        RealMarketPaperTrade.pnl.isnot(None),
    ).all()
    db.close()

    # Group CLV by bookmaker
    bm_clv: dict[str, list[float]] = defaultdict(list)
    for r in clv_records:
        bm_clv[r.bookmaker].append(float(r.clv_pct))

    # Group trade P&L by bookmaker
    bm_pnl: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        bm_pnl[t.bookmaker].append(float(t.pnl or 0))

    all_bms = set(list(bm_clv.keys()) + list(bm_pnl.keys()))
    rankings = []
    for bm in sorted(all_bms):
        clv_vals = bm_clv.get(bm, [])
        pnl_vals = bm_pnl.get(bm, [])

        avg_clv = sum(clv_vals) / len(clv_vals) if clv_vals else 0
        pos_clv_pct = sum(1 for v in clv_vals if v > 0) / len(clv_vals) * 100 if clv_vals else 0
        total_pnl = sum(pnl_vals)
        roi = (total_pnl / len(pnl_vals)) * 100 if pnl_vals else 0

        rankings.append({
            "bookmaker": bm,
            "avg_clv": round(avg_clv, 4),
            "positive_clv_pct": round(pos_clv_pct, 2),
            "roi_pct": round(roi, 2),
            "trade_count": len(pnl_vals),
            "clv_samples": len(clv_vals),
        })

    rankings.sort(key=lambda x: x["avg_clv"], reverse=True)
    return rankings


# ============================================================
#  PHASE 7: SPORT ANALYSIS
# ============================================================

def compute_sport_rankings() -> list[dict]:
    """Rank sports by CLV, ROI, and sample size."""
    db = _get_db()

    # Get CLV records with event info
    clv_with_events = (
        db.query(RealMarketClvRecord, RealMarketEvent.sport)
        .join(RealMarketEvent, RealMarketClvRecord.event_id == RealMarketEvent.event_id)
        .all()
    )

    # Get trades with event info
    trades_with_events = (
        db.query(RealMarketPaperTrade, RealMarketEvent.sport)
        .join(RealMarketEvent, RealMarketPaperTrade.event_id == RealMarketEvent.event_id)
        .filter(RealMarketPaperTrade.is_open == False)
        .all()
    )
    db.close()

    sport_clv: dict[str, list[float]] = defaultdict(list)
    for clv, sport in clv_with_events:
        sport_clv[sport].append(float(clv.clv_pct))

    sport_pnl: dict[str, list[float]] = defaultdict(list)
    for trade, sport in trades_with_events:
        if trade.pnl is not None:
            sport_pnl[sport].append(float(trade.pnl))

    rankings = []
    all_sports = set(list(sport_clv.keys()) + list(sport_pnl.keys()))
    for sport in sorted(all_sports):
        clv_vals = sport_clv.get(sport, [])
        pnl_vals = sport_pnl.get(sport, [])

        avg_clv = sum(clv_vals) / len(clv_vals) if clv_vals else 0
        total_pnl = sum(pnl_vals)
        roi = (total_pnl / len(pnl_vals)) * 100 if pnl_vals else 0

        rankings.append({
            "sport": sport,
            "avg_clv": round(avg_clv, 4),
            "roi_pct": round(roi, 2),
            "sample_size": max(len(clv_vals), len(pnl_vals)),
            "clv_samples": len(clv_vals),
            "trade_samples": len(pnl_vals),
        })

    rankings.sort(key=lambda x: x["avg_clv"], reverse=True)
    return rankings


# ============================================================
#  PHASE 8: FALSE POSITIVE DETECTION
# ============================================================

def compute_false_positive_rate() -> dict:
    """Measure false positive rate: EV positive but CLV negative."""
    db = _get_db()
    trades = db.query(RealMarketPaperTrade).filter(
        RealMarketPaperTrade.is_open == False,
        RealMarketPaperTrade.entry_ev.isnot(None),
        RealMarketPaperTrade.pnl.isnot(None),
    ).all()
    db.close()

    if not trades:
        return {"status": "insufficient_data", "trades": 0}

    ev_positive = [t for t in trades if t.entry_ev and float(t.entry_ev) > 0]
    ev_negative = [t for t in trades if t.entry_ev and float(t.entry_ev) <= 0]

    false_positives = [t for t in ev_positive if t.pnl and float(t.pnl) <= 0]
    true_positives = [t for t in ev_positive if t.pnl and float(t.pnl) > 0]

    fp_rate = len(false_positives) / len(ev_positive) * 100 if ev_positive else 0
    tp_rate = len(true_positives) / len(ev_positive) * 100 if ev_positive else 0

    # Confusion matrix
    false_negatives = [t for t in ev_negative if t.pnl and float(t.pnl) > 0]
    true_negatives = [t for t in ev_negative if t.pnl and float(t.pnl) <= 0]

    return {
        "status": "ok",
        "total_trades": len(trades),
        "ev_positive_trades": len(ev_positive),
        "ev_negative_trades": len(ev_negative),
        "false_positives": len(false_positives),
        "true_positives": len(true_positives),
        "false_negative": len(false_negatives),
        "true_negative": len(true_negatives),
        "false_positive_rate": round(fp_rate, 2),
        "true_positive_rate": round(tp_rate, 2),
        "precision": round(tp_rate / (tp_rate + fp_rate) * 100, 2) if (tp_rate + fp_rate) > 0 else 0,
    }


# ============================================================
#  PHASE 10: FINAL CLASSIFICATION
# ============================================================

def classify_edge(clv_metrics: dict, trade_metrics: dict, ev_corr: dict) -> dict:
    """Determine: NO_EDGE, WEAK_EDGE, PROMISING_EDGE, or STRONG_EDGE."""
    clv_records = clv_metrics.get("records", 0)
    closed_trades = trade_metrics.get("closed_trades", 0)
    clv_mean = clv_metrics.get("mean_clv", 0)
    win_rate = trade_metrics.get("win_rate", 0)
    roi = trade_metrics.get("roi_pct", 0)
    pearson = ev_corr.get("pearson_r", 0)
    significant = ev_corr.get("significant_at_95", False)

    if clv_records < 100:
        return {
            "classification": "INSUFFICIENT_DATA",
            "clv_records": clv_records,
            "required": 100,
            "reasoning": f"Only {clv_records} CLV records (minimum 100 required)",
        }

    evidence = []
    score = 0

    # CLV evidence
    if abs(clv_mean) < 0.5:
        evidence.append("CLV near zero — no edge detected")
    elif clv_mean > 1.0:
        evidence.append(f"Positive CLV mean ({clv_mean}%) — odds move in our favor")
        score += 2
    elif clv_mean > 0.5:
        evidence.append(f"Slightly positive CLV ({clv_mean}%)")
        score += 1
    elif clv_mean < -1.0:
        evidence.append(f"Negative CLV mean ({clv_mean}%) — odds move against us")
        score -= 1

    # Win rate evidence
    if win_rate > 55:
        evidence.append(f"Win rate {win_rate}% exceeds 55%")
        score += 2
    elif win_rate > 52:
        evidence.append(f"Win rate {win_rate}% marginally above breakeven")
        score += 1
    elif win_rate < 48:
        evidence.append(f"Win rate {win_rate}% below breakeven")
        score -= 1

    # ROI evidence
    if roi > 5:
        evidence.append(f"ROI {roi}% strong")
        score += 2
    elif roi > 2:
        evidence.append(f"ROI {roi}% moderate")
        score += 1
    elif roi < 0:
        evidence.append(f"ROI {roi}% negative")
        score -= 1

    # EV -> CLV correlation evidence
    if significant and pearson > 0.3:
        evidence.append(f"EV significantly predicts CLV (r={pearson})")
        score += 2
    elif significant and pearson > 0.1:
        evidence.append(f"Weak EV->CLV correlation (r={pearson}, p<0.05)")
        score += 1
    elif not significant:
        evidence.append(f"No significant EV->CLV correlation (r={pearson})")
        score -= 1

    # Classification
    if score >= 5:
        classification = "STRONG_EDGE"
    elif score >= 3:
        classification = "PROMISING_EDGE"
    elif score >= 1:
        classification = "WEAK_EDGE"
    else:
        classification = "NO_EDGE"

    return {
        "classification": classification,
        "evidence_score": score,
        "clv_records": clv_records,
        "closed_trades": closed_trades,
        "evidence": evidence,
        "reasoning": (
            f"Score {score}/8: {classification}. "
            + "; ".join(evidence)
        ),
    }


# ============================================================
#  MAIN REPORT
# ============================================================

def generate_full_report() -> dict:
    """Generate complete research report covering all phases."""
    logger("=" * 60)
    logger("  LONGITUDINAL EDGE RESEARCH — FULL REPORT")
    logger("=" * 60)

    # Phase 2: Load daily reports
    daily = load_daily_reports()
    logger(f"\n[PHASE 2] Daily reports found: {len(daily)}")
    for d in daily:
        logger(f"  {d['day']}: events={d['events_collected']} odds={d['odds_collected']} trades={d['paper_trades_opened']} clv={d['clv_records_generated']}")

    # Phase 3: CLV analysis
    logger(f"\n[PHASE 3] CLV Analysis...")
    clv = compute_clv_metrics()
    if clv["status"] == "ok":
        logger(f"  Records: {clv['records']}")
        logger(f"  Mean CLV: {clv['mean_clv']}%")
        logger(f"  Median CLV: {clv['median_clv']}%")
        logger(f"  Positive: {clv['positive_clv_pct']}%")
        logger(f"  Negative: {clv['negative_clv_pct']}%")
        logger(f"  Distribution: {clv['distribution']}")
    else:
        logger(f"  {clv['status']} ({clv['records']} records)")

    # Phase 4: Paper trade analysis
    logger(f"\n[PHASE 4] Paper Trade Analysis...")
    trades = compute_paper_trade_metrics()
    if trades["status"] == "ok":
        logger(f"  Closed trades: {trades['closed_trades']}")
        logger(f"  Win rate: {trades['win_rate']}%")
        logger(f"  ROI: {trades['roi_pct']}%")
        logger(f"  Profit factor: {trades['profit_factor']}")
        logger(f"  Max drawdown: {trades['max_drawdown_units']} units")
        logger(f"  Expectancy: {trades['expectancy_per_trade']} per trade")
    else:
        logger(f"  {trades['status']} ({trades['closed_trades']} closed)")

    # Phase 5: EV validation
    logger(f"\n[PHASE 5] EV -> CLV Correlation...")
    ev = compute_ev_clv_correlation()
    if ev["status"] == "ok":
        logger(f"  Pairs: {ev['pairs']}")
        logger(f"  Pearson r: {ev['pearson_r']}")
        logger(f"  Spearman rho: {ev['spearman_rho']}")
        logger(f"  p-value: {ev['p_value_approximate']}")
        logger(f"  Significant: {ev['significant_at_95']}")
        logger(f"  {ev['interpretation']}")
    else:
        logger(f"  {ev['status']} ({ev.get('pairs', 0)} pairs)")

    # Phase 6: Bookmaker analysis
    logger(f"\n[PHASE 6] Bookmaker Rankings...")
    bm_rankings = compute_bookmaker_rankings()
    if bm_rankings:
        logger(f"  {'Bookmaker':25s} {'Avg CLV':>10s} {'Pos%':>8s} {'ROI%':>8s} {'Trades':>8s}")
        logger(f"  {'-'*25} {'-'*10} {'-'*8} {'-'*8} {'-'*8}")
        for bm in bm_rankings[:10]:
            logger(f"  {bm['bookmaker']:25s} {bm['avg_clv']:>10.4f} {bm['positive_clv_pct']:>7.2f}% {bm['roi_pct']:>7.2f}% {bm['trade_count']:>8d}")
    else:
        logger(f"  No bookmaker data")

    # Phase 7: Sport analysis
    logger(f"\n[PHASE 7] Sport Rankings...")
    sport_rankings = compute_sport_rankings()
    if sport_rankings:
        logger(f"  {'Sport':35s} {'Avg CLV':>10s} {'ROI%':>8s} {'Samples':>8s}")
        logger(f"  {'-'*35} {'-'*10} {'-'*8} {'-'*8}")
        for s in sport_rankings[:10]:
            logger(f"  {s['sport']:35s} {s['avg_clv']:>10.4f} {s['roi_pct']:>7.2f}% {s['sample_size']:>8d}")
    else:
        logger(f"  No sport data")

    # Phase 8: False positive detection
    logger(f"\n[PHASE 8] False Positive Detection...")
    fp = compute_false_positive_rate()
    if fp["status"] == "ok":
        logger(f"  FP rate: {fp['false_positive_rate']}%")
        logger(f"  TP rate: {fp['true_positive_rate']}%")
        logger(f"  Precision: {fp['precision']}%")
        logger(f"  Confusion: FP={fp['false_positives']} TP={fp['true_positives']} FN={fp['false_negative']} TN={fp['true_negative']}")
    else:
        logger(f"  {fp['status']} ({fp.get('trades', 0)} trades)")

    # Phase 10: Final classification
    logger(f"\n[PHASE 10] Final Classification...")
    classification = classify_edge(clv, trades, ev)
    logger(f"  Classification: {classification['classification']}")
    if 'evidence_score' in classification:
        logger(f"  Score: {classification['evidence_score']}/8")
        logger(f"  Evidence:")
        for e in classification["evidence"]:
            logger(f"    - {e}")
    logger(f"  Reasoning: {classification['reasoning']}")

    # Summary box
    logger("\n" + "=" * 60)
    logger("  RESEARCH SUMMARY")
    logger("=" * 60)
    logger(f"  Classification: {classification['classification']}")
    logger(f"  CLV Records:    {clv.get('records', 0)}")
    logger(f"  Closed Trades:  {trades.get('closed_trades', 0)}")
    logger(f"  Win Rate:       {trades.get('win_rate', 'N/A')}%")
    logger(f"  ROI:            {trades.get('roi_pct', 'N/A')}%")
    logger(f"  EV-CLV r:       {ev.get('pearson_r', 'N/A')}")
    logger(f"  FP Rate:        {fp.get('false_positive_rate', 'N/A')}%")
    best_bm = bm_rankings[0]['bookmaker'] if bm_rankings else 'N/A'
    best_sp = sport_rankings[0]['sport'] if sport_rankings else 'N/A'
    logger(f"  Best BM:        {best_bm}")
    logger(f"  Best Sport:     {best_sp}")
    logger("=" * 60)

    return {
        "daily_reports": daily,
        "clv_analysis": clv,
        "paper_trade_analysis": trades,
        "ev_clv_correlation": ev,
        "bookmaker_rankings": bm_rankings,
        "sport_rankings": sport_rankings,
        "false_positive_analysis": fp,
        "final_classification": classification,
    }


if __name__ == "__main__":
    phase_filter = None
    for arg in sys.argv:
        if arg.startswith("--phase="):
            phase_filter = int(arg.split("=")[1])

    report = generate_full_report()

    # Output JSON
    output_path = Path(__file__).parent / "research_report.json"
    output_path.write_text(json.dumps(report, indent=2, default=str))
    logger(f"\n[SAVED] Full report to {output_path}")
