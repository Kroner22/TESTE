from __future__ import annotations

import random
import statistics
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from backend.domains.clv.models import ClvRecord, ClvGrade
from .models import (
    BetOutcome, ClvValidationBet, EdgeSignal, ClvValidationMetrics,
    ClvValidationReport, SegmentAnalysis, SystemEdgeClass, Recommendation,
)


def _odds_range(odd: Decimal) -> str:
    f = float(odd)
    if f < 2.0:
        return "1.0-2.0"
    if f < 3.0:
        return "2.0-3.0"
    if f < 5.0:
        return "3.0-5.0"
    return "5.0+"


def _classify_edge_signal(ev: float, clv: float) -> EdgeSignal:
    if ev > 0 and clv > 0:
        return EdgeSignal.TRUE_EDGE
    if ev > 0 and clv <= 0:
        return EdgeSignal.FALSE_POSITIVE
    if ev <= 0 and clv <= 0:
        return EdgeSignal.CORRECTLY_AVOIDED
    return EdgeSignal.MODEL_BLIND_SPOT


def _simulate_bet_outcome(closing_odd: Decimal) -> BetOutcome:
    win_prob = 1.0 / float(closing_odd) if float(closing_odd) > 1 else 0.5
    return BetOutcome.WIN if random.random() < win_prob else BetOutcome.LOSS


DEFAULT_STAKE_PCT = 0.01


def run_clv_backtest(
    records: list[ClvRecord],
    stake_pct: float = DEFAULT_STAKE_PCT,
    initial_bankroll: float = 10_000.0,
    seed: Optional[int] = None,
) -> ClvValidationReport:
    if seed is not None:
        random.seed(seed)

    if not records:
        return ClvValidationReport(verdict="No records to backtest")

    sorted_records = sorted(records, key=lambda r: r.captured_at)

    bets: list[ClvValidationBet] = []
    bankroll = initial_bankroll
    equity: list[tuple[datetime, float]] = []
    peak = initial_bankroll

    for rec in sorted_records:
        stake = bankroll * stake_pct
        if stake <= 0:
            continue

        outcome = _simulate_bet_outcome(rec.closing_odd)
        profit = stake * (float(rec.closing_odd) - 1.0) if outcome == BetOutcome.WIN else -stake

        bankroll += profit
        if bankroll > peak:
            peak = bankroll

        bets.append(ClvValidationBet(
            event_id=rec.event_id,
            market=rec.market,
            outcome=rec.outcome,
            bookmaker=rec.bookmaker,
            entry_odd=rec.captured_odd,
            closing_odd=rec.closing_odd,
            captured_at=rec.captured_at,
            closed_at=rec.closed_at,
            simulated_ev=rec.simulated_ev,
            clv_pct=rec.clv_pct,
            bet_result=outcome,
            profit=round(profit, 2),
            stake=round(stake, 2),
            edge_signal=_classify_edge_signal(rec.simulated_ev, rec.clv_pct),
            grade=rec.grade.value,
            odds_range=_odds_range(rec.captured_odd),
            sport=getattr(rec, "sport", "unknown"),
            timing=rec.timing_efficiency.value,
        ))
        equity.append((rec.captured_at, round(bankroll, 2)))

    metrics = _compute_metrics(bets, bankroll > initial_bankroll)
    by_sport = _segment_by(bets, "sport")
    by_bookmaker = _segment_by(bets, "bookmaker")
    by_odds_range = _segment_by(bets, "odds_range")
    by_grade = _segment_by(bets, "grade")
    by_month = _segment_by_month(bets)
    by_edge_signal = _segment_by(bets, "edge_signal")

    charts_ev_vs_clv = [{"ev": b.simulated_ev, "clv": b.clv_pct, "signal": b.edge_signal.value} for b in bets]
    charts_equity = [{"date": d.isoformat(), "bankroll": v} for d, v in equity]
    charts_edge_decay = _compute_edge_decay_chart(bets)
    charts_distribution = _compute_distribution_charts(bets)

    summary = _build_summary(metrics)

    return ClvValidationReport(
        metrics=metrics,
        bets=bets,
        equity_curve=[(d.isoformat(), v) for d, v in equity],
        by_sport=by_sport,
        by_bookmaker=by_bookmaker,
        by_odds_range=by_odds_range,
        by_grade=by_grade,
        by_month=by_month,
        by_edge_signal=by_edge_signal,
        charts_ev_vs_clv=charts_ev_vs_clv,
        charts_equity=charts_equity,
        charts_edge_decay=charts_edge_decay,
        charts_distribution=charts_distribution,
        verdict=metrics.recommendation.value,
        summary_text=summary,
    )


def _compute_metrics(bets: list[ClvValidationBet], profitable: bool) -> ClvValidationMetrics:
    if not bets:
        return ClvValidationMetrics()

    n = len(bets)
    wins = sum(1 for b in bets if b.is_winner)
    losses = n - wins

    total_staked = sum(b.stake for b in bets)
    total_profit = sum(b.profit for b in bets)
    roi = (total_profit / total_staked * 100.0) if total_staked > 0 else 0.0

    clvs = [b.clv_pct for b in bets]
    evs = [b.simulated_ev for b in bets]
    avg_clv = statistics.mean(clvs)
    avg_ev = statistics.mean(evs)

    clv_adjusted_roi = roi - avg_clv

    n_true = sum(1 for b in bets if b.edge_signal == EdgeSignal.TRUE_EDGE)
    n_false = sum(1 for b in bets if b.edge_signal == EdgeSignal.FALSE_POSITIVE)
    n_blind = sum(1 for b in bets if b.edge_signal == EdgeSignal.MODEL_BLIND_SPOT)
    n_avoided = sum(1 for b in bets if b.edge_signal == EdgeSignal.CORRECTLY_AVOIDED)

    aligned = sum(1 for b in bets if b.ev_aligned_with_clv)
    efficiency = (aligned / n * 100.0) if n > 0 else 0.0

    ev_positive_bets = [b for b in bets if b.simulated_ev > 0]
    ev_pos_with_clv_pos = sum(1 for b in ev_positive_bets if b.clv_pct > 0)
    edge_quality = (ev_pos_with_clv_pos / len(ev_positive_bets) * 100.0) if ev_positive_bets else 0.0

    max_dd, dd_duration = _compute_drawdown(bets)

    profits = [b.profit for b in bets]
    avg_profit = statistics.mean(profits) if profits else 0.0
    std_profit = statistics.stdev(profits) if len(profits) > 1 else 0.0
    sharpe = (avg_profit / std_profit * (365 ** 0.5)) if std_profit > 0 else 0.0

    t_stat, p_val = _one_sample_t_test(clvs)

    edge_decay_slope, edge_decay_interp = _compute_edge_decay_slope(bets)

    signal = _classify_system(roi, avg_clv, p_val, efficiency, edge_quality)

    return ClvValidationMetrics(
        n_bets=n,
        n_wins=wins,
        n_losses=losses,
        hit_rate=(wins / n * 100.0) if n > 0 else 0.0,
        total_staked=round(total_staked, 2),
        total_profit=round(total_profit, 2),
        roi_pct=round(roi, 4),
        clv_adjusted_roi=round(clv_adjusted_roi, 4),
        avg_clv_pct=round(avg_clv, 4),
        median_clv_pct=round(statistics.median(clvs), 4),
        avg_ev=round(avg_ev, 4),
        ev_clv_pearson=round(_pearson(evs, clvs), 4),
        ev_clv_spearman=round(_spearman(evs, clvs), 4),
        ev_clv_p_value=0.0,
        efficiency_score=round(efficiency, 2),
        edge_quality_score=round(edge_quality, 2),
        max_drawdown_pct=round(max_dd, 4),
        max_drawdown_duration_days=dd_duration,
        edge_decay_slope=round(edge_decay_slope, 6),
        edge_decay_interpretation=edge_decay_interp,
        true_edge_pct=(n_true / n * 100.0) if n > 0 else 0.0,
        false_positive_pct=(n_false / n * 100.0) if n > 0 else 0.0,
        blind_spot_pct=(n_blind / n * 100.0) if n > 0 else 0.0,
        correctly_avoided_pct=(n_avoided / n * 100.0) if n > 0 else 0.0,
        sharpe_ratio=round(sharpe, 4),
        t_statistic=round(t_stat, 4),
        p_value=round(p_val, 4),
        is_significant=p_val < 0.05,
        system_edge_class=signal,
        recommendation=_recommend(signal),
    )


def _classify_system(
    roi: float, avg_clv: float, p_value: float,
    efficiency: float, edge_quality: float,
) -> SystemEdgeClass:
    if p_value < 0.05 and avg_clv > 0.5 and roi > 0:
        return SystemEdgeClass.STRONG_EDGE
    if avg_clv < -0.5 and efficiency < 40:
        return SystemEdgeClass.NO_EDGE
    if edge_quality > 50 and efficiency > 50:
        return SystemEdgeClass.STRONG_EDGE
    if edge_quality > 30 and roi > 0:
        return SystemEdgeClass.WEAK_EDGE
    return SystemEdgeClass.INCONCLUSIVE


def _recommend(signal: SystemEdgeClass) -> Recommendation:
    if signal == SystemEdgeClass.STRONG_EDGE:
        return Recommendation.SCALE
    if signal == SystemEdgeClass.NO_EDGE:
        return Recommendation.KILL
    if signal == SystemEdgeClass.WEAK_EDGE:
        return Recommendation.FIX
    return Recommendation.FIX


def _compute_drawdown(bets: list[ClvValidationBet]) -> tuple[float, int]:
    if not bets:
        return 0.0, 0
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    dd_start = 0
    max_dd_duration = 0
    for i, b in enumerate(bets):
        cum += b.profit
        if cum > peak:
            peak = cum
            dd_start = i
        dd = (peak - cum) / (peak + 1e-9) if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
            max_dd_duration = i - dd_start
    return max_dd * 100.0, max_dd_duration


def _one_sample_t_test(values: list[float]) -> tuple[float, float]:
    if len(values) < 2:
        return 0.0, 1.0
    import math
    n = len(values)
    mean = statistics.mean(values)
    std = statistics.stdev(values)
    if std == 0:
        return 0.0, 1.0
    se = std / math.sqrt(n)
    t = mean / se
    from scipy import stats as scipy_stats
    try:
        p = scipy_stats.t.sf(abs(t), df=n - 1) * 2
    except Exception:
        p = 1.0
    return t, p


def _pearson(x: list[float], y: list[float]) -> float:
    if len(x) < 3:
        return 0.0
    try:
        from scipy import stats as scipy_stats
        r, _ = scipy_stats.pearsonr(x, y)
        return r
    except Exception:
        return 0.0


def _spearman(x: list[float], y: list[float]) -> float:
    if len(x) < 3:
        return 0.0
    try:
        from scipy import stats as scipy_stats
        r, _ = scipy_stats.spearmanr(x, y)
        return r
    except Exception:
        return 0.0


def _compute_edge_decay_slope(bets: list[ClvValidationBet]) -> tuple[float, str]:
    if len(bets) < 20:
        return 0.0, "insufficient_data"

    window = max(10, len(bets) // 20)
    clv_avgs = []
    for i in range(0, len(bets), window):
        chunk = bets[i:i + window]
        if chunk:
            clv_avgs.append(statistics.mean(b.clv_pct for b in chunk))

    if len(clv_avgs) < 3:
        return 0.0, "insufficient_data"

    x = list(range(len(clv_avgs)))
    n = len(x)
    x_mean = statistics.mean(x)
    y_mean = statistics.mean(clv_avgs)
    num = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, clv_avgs))
    den = sum((xi - x_mean) ** 2 for xi in x)
    slope = num / den if den != 0 else 0.0

    if slope < -0.05:
        interp = "degrading_edge"
    elif slope > 0.05:
        interp = "improving_edge"
    else:
        interp = "stable_edge"

    return slope, interp


def _compute_edge_decay_chart(bets: list[ClvValidationBet]) -> list[dict]:
    if len(bets) < 20:
        return []
    window = max(10, len(bets) // 20)
    result = []
    for i in range(0, len(bets), window):
        chunk = bets[i:i + window]
        if chunk:
            avg_clv = statistics.mean(b.clv_pct for b in chunk)
            result.append({"bucket": i // window, "avg_clv": round(avg_clv, 4), "n_bets": len(chunk)})
    return result


def _segment_by(bets: list[ClvValidationBet], attr: str) -> list[SegmentAnalysis]:
    groups: dict[str, list[ClvValidationBet]] = {}
    for b in bets:
        val = getattr(b, attr, "unknown")
        groups.setdefault(val, []).append(b)

    results = []
    for value, group in groups.items():
        if len(group) < 2:
            continue
        n = len(group)
        wins = sum(1 for b in group if b.is_winner)
        total_staked = sum(b.stake for b in group)
        total_profit = sum(b.profit for b in group)
        roi = (total_profit / total_staked * 100.0) if total_staked > 0 else 0.0
        clv = statistics.mean(b.clv_pct for b in group)
        hit_rate = (wins / n * 100.0) if n > 0 else 0.0
        aligned = sum(1 for b in group if b.ev_aligned_with_clv)
        efficiency = (aligned / n * 100.0) if n > 0 else 0.0
        ev_pos = [b for b in group if b.simulated_ev > 0]
        ev_pos_with_clv = sum(1 for b in ev_pos if b.clv_pct > 0)
        edge_quality = (ev_pos_with_clv / len(ev_pos) * 100.0) if ev_pos else 0.0

        results.append(SegmentAnalysis(
            segment=attr,
            value=str(value),
            n_bets=n,
            roi_pct=round(roi, 2),
            clv_pct=round(clv, 2),
            hit_rate=round(hit_rate, 2),
            efficiency=round(efficiency, 2),
            edge_quality=round(edge_quality, 2),
        ))

    return sorted(results, key=lambda s: s.roi_pct, reverse=True)


def _segment_by_month(bets: list[ClvValidationBet]) -> list[SegmentAnalysis]:
    groups: dict[str, list[ClvValidationBet]] = {}
    for b in bets:
        key = b.captured_at.strftime("%Y-%m")
        groups.setdefault(key, []).append(b)

    results = []
    for month, group in sorted(groups.items()):
        if len(group) < 2:
            continue
        n = len(group)
        wins = sum(1 for b in group if b.is_winner)
        total_staked = sum(b.stake for b in group)
        total_profit = sum(b.profit for b in group)
        roi = (total_profit / total_staked * 100.0) if total_staked > 0 else 0.0
        clv = statistics.mean(b.clv_pct for b in group)
        hit_rate = (wins / n * 100.0) if n > 0 else 0.0
        aligned = sum(1 for b in group if b.ev_aligned_with_clv)
        efficiency = (aligned / n * 100.0) if n > 0 else 0.0
        ev_pos = [b for b in group if b.simulated_ev > 0]
        ev_pos_with_clv = sum(1 for b in ev_pos if b.clv_pct > 0)
        edge_quality = (ev_pos_with_clv / len(ev_pos) * 100.0) if ev_pos else 0.0

        results.append(SegmentAnalysis(
            segment="month",
            value=month,
            n_bets=n,
            roi_pct=round(roi, 2),
            clv_pct=round(clv, 2),
            hit_rate=round(hit_rate, 2),
            efficiency=round(efficiency, 2),
            edge_quality=round(edge_quality, 2),
        ))

    return results


def _compute_distribution_charts(bets: list[ClvValidationBet]) -> list[dict]:
    bins = {
        "< -5%": 0, "-5 a -3%": 0, "-3 a -1%": 0, "-1 a 0%": 0,
        "0 a 1%": 0, "1 a 3%": 0, "3 a 5%": 0, "> 5%": 0,
    }
    for b in bets:
        c = b.clv_pct
        if c < -5:
            bins["< -5%"] += 1
        elif c < -3:
            bins["-5 a -3%"] += 1
        elif c < -1:
            bins["-3 a -1%"] += 1
        elif c < 0:
            bins["-1 a 0%"] += 1
        elif c < 1:
            bins["0 a 1%"] += 1
        elif c < 3:
            bins["1 a 3%"] += 1
        elif c < 5:
            bins["3 a 5%"] += 1
        else:
            bins["> 5%"] += 1

    return [{"bucket": k, "count": v} for k, v in bins.items()]


def _build_summary(m: ClvValidationMetrics) -> str:
    lines = [
        f"System Classification: {m.system_edge_class.value}",
        f"Recommendation: {m.recommendation.value}",
        "",
        f"Bets: {m.n_bets} total ({m.n_wins}W / {m.n_losses}L)",
        f"Hit Rate: {m.hit_rate:.1f}%",
        f"ROI: {m.roi_pct:+.2f}%",
        f"CLV-Adjusted ROI: {m.clv_adjusted_roi:+.2f}%",
        f"Avg CLV: {m.avg_clv_pct:+.2f}%",
        f"Avg EV: {m.avg_ev:+.4f}",
        "",
        f"EV-CLV Pearson: {m.ev_clv_pearson:+.3f}",
        f"EV-CLV Spearman: {m.ev_clv_spearman:+.3f}",
        f"Efficiency Score: {m.efficiency_score:.1f}%",
        f"Edge Quality Score: {m.edge_quality_score:.1f}%",
        "",
        f"True Edge: {m.true_edge_pct:.1f}%",
        f"False Positive: {m.false_positive_pct:.1f}%",
        f"Blind Spot: {m.blind_spot_pct:.1f}%",
        f"Correctly Avoided: {m.correctly_avoided_pct:.1f}%",
        "",
        f"Max Drawdown: {m.max_drawdown_pct:.1f}%",
        f"Sharpe Ratio: {m.sharpe_ratio:.2f}",
        f"Edge Decay: {m.edge_decay_interpretation} (slope={m.edge_decay_slope:+.6f})",
        "",
        f"T-Test: t={m.t_statistic:+.3f}, p={m.p_value:.4f}",
        f"Statistically Significant: {'YES' if m.is_significant else 'NO'}",
    ]
    return "\n".join(lines)


def format_clv_backtest_report(report: ClvValidationReport) -> str:
    lines = [
        "=" * 64,
        "  CLV VALIDATION BACKTEST REPORT",
        "=" * 64,
        f"  Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')} UTC",
        f"  Bets: {report.metrics.n_bets}",
        "",
        f"  System: {report.metrics.system_edge_class.value}",
        f"  Action: {report.metrics.recommendation.value}",
        "",
    ]

    m = report.metrics
    lines += [
        "  ── Performance ──",
        f"  ROI:                {m.roi_pct:>+8.2f}%",
        f"  CLV-Adjusted ROI:   {m.clv_adjusted_roi:>+8.2f}%",
        f"  Hit Rate:           {m.hit_rate:>7.1f}%  ({m.n_wins}W / {m.n_losses}L)",
        f"  Total Staked:       ${m.total_staked:>8.2f}",
        f"  Total Profit:       ${m.total_profit:>+8.2f}",
        f"  Max Drawdown:       {m.max_drawdown_pct:>7.1f}%  ({m.max_drawdown_duration_days}d)",
        f"  Sharpe Ratio:       {m.sharpe_ratio:>7.2f}",
        "",
        "  ── EV x CLV ──",
        f"  Avg EV:             {m.avg_ev:>+8.4f}",
        f"  Avg CLV:            {m.avg_clv_pct:>+8.2f}%",
        f"  CLV Median:         {m.median_clv_pct:>+8.2f}%",
        f"  EV-CLV Pearson:     {m.ev_clv_pearson:>+8.3f}",
        f"  EV-CLV Spearman:    {m.ev_clv_spearman:>+8.3f}",
        "",
        "  ── Edge Quality ──",
        f"  Efficiency Score:   {m.efficiency_score:>7.1f}%",
        f"  Edge Quality Score: {m.edge_quality_score:>7.1f}%",
        f"  True Edge:          {m.true_edge_pct:>7.1f}%",
        f"  False Positive:     {m.false_positive_pct:>7.1f}%",
        f"  Blind Spot:         {m.blind_spot_pct:>7.1f}%",
        f"  Correctly Avoided:  {m.correctly_avoided_pct:>7.1f}%",
        "",
        "  ── Edge Decay ──",
        f"  Status: {m.edge_decay_interpretation}",
        f"  Slope: {m.edge_decay_slope:+.6f}",
        "",
        "  ── Statistical ──",
        f"  T-Test:   t={m.t_statistic:+.3f}, p={m.p_value:.4f}",
        f"  Significant: {'YES' if m.is_significant else 'NO'}",
        "",
    ]

    if report.by_sport:
        lines += ["  ── By Sport ──"]
        lines.append(f"  {'Sport':<18s} {'Bets':>5s} {'ROI':>8s} {'CLV':>7s} {'Hit%':>6s} {'Eff%':>6s}")
        lines.append(f"  {'─'*18} {'─'*5} {'─'*8} {'─'*7} {'─'*6} {'─'*6}")
        for s in report.by_sport:
            lines.append(f"  {s.value:<18s} {s.n_bets:5d} {s.roi_pct:>+7.2f}% {s.clv_pct:>+6.2f}% {s.hit_rate:>5.1f}% {s.efficiency:>5.1f}%")

    if report.by_bookmaker:
        lines += ["", "  ── By Bookmaker ──"]
        lines.append(f"  {'Bookmaker':<18s} {'Bets':>5s} {'ROI':>8s} {'CLV':>7s} {'Hit%':>6s} {'Eff%':>6s}")
        lines.append(f"  {'─'*18} {'─'*5} {'─'*8} {'─'*7} {'─'*6} {'─'*6}")
        for bm in report.by_bookmaker:
            lines.append(f"  {bm.value:<18s} {bm.n_bets:5d} {bm.roi_pct:>+7.2f}% {bm.clv_pct:>+6.2f}% {bm.hit_rate:>5.1f}% {bm.efficiency:>5.1f}%")

    lines += ["", "═" * 64]

    return "\n".join(lines)
