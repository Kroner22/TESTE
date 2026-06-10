from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from .models import ClvGrade, ClvRecord, ClvReport, TimingEfficiency
from .analyzer import (
    compute_distribution, compute_by_bookmaker, compute_correlation,
    compute_timing_analysis, compute_t_test, compute_model_quality,
)
from .calculator import detect_leak


def generate_clv_report(
    records: list[ClvRecord],
    title: str = "CLV Analysis Report",
) -> ClvReport:
    if not records:
        return ClvReport(verdict="no_data", recommendations=["Collect CLV data before analysis"])

    distribution = compute_distribution(records)
    by_bookmaker = compute_by_bookmaker(records)
    correlation = compute_correlation(records)
    timing = compute_timing_analysis(records)
    t_test = compute_t_test(records)
    leaks = detect_leak(records)
    model_quality = compute_model_quality(records, distribution, correlation)

    unique_events = len(set(r.event_id for r in records))
    unique_bookmakers = len(set(r.bookmaker for r in records))

    verdict = _generate_verdict(distribution, correlation, t_test, timing, leaks)
    recommendations = _generate_recommendations(
        distribution, correlation, timing, by_bookmaker, leaks, model_quality,
    )

    return ClvReport(
        generated_at=datetime.now(timezone.utc),
        n_records=len(records),
        n_events=unique_events,
        n_bookmakers=unique_bookmakers,
        overall_clv=distribution.mean_clv,
        overall_clv_pct=distribution.mean_clv,
        distribution=distribution,
        by_bookmaker=by_bookmaker,
        correlation=correlation,
        timing=timing,
        model_quality=model_quality,
        verdict=verdict,
        recommendations=recommendations,
    )


def _generate_verdict(
    dist, corr, t_test, timing, leaks,
) -> str:
    parts: list[str] = []

    clv = dist.mean_clv
    if clv > 2.0:
        parts.append("ELITE: System generates strong positive CLV")
    elif clv > 1.0:
        parts.append("STRONG: System generates positive CLV consistently")
    elif clv > 0.3:
        parts.append("POSITIVE: System edges the market")
    elif clv > -0.3:
        parts.append("NEUTRAL: System matches market efficiency")
    elif clv > -1.0:
        parts.append("NEGATIVE: System trails the market")
    else:
        parts.append("CATASTROPHIC: System is significantly behind the market")

    if dist.positive_pct > 60:
        parts.append(f"({dist.positive_pct:.0f}% of bets beat the closing line)")
    elif dist.positive_pct < 40:
        parts.append(f"(only {dist.positive_pct:.0f}% of bets beat the closing line)")

    if t_test["significant"]:
        if t_test["t_statistic"] > 0:
            parts.append("Statistically significant positive CLV")
        else:
            parts.append("Statistically significant negative CLV")
    else:
        parts.append("CLV not statistically distinguishable from zero")

    if corr.interpretation.startswith("strong") or corr.interpretation.startswith("moderate"):
        parts.append(f"EV+ correlates with CLV (r={corr.pearson_r:.2f}) — model is predictive")
    elif corr.interpretation.startswith("no_significant"):
        parts.append("EV+ does NOT correlate with CLV — model may be overfitting")

    if timing.early_avg_clv > timing.late_avg_clv + 0.5:
        parts.append("Earlier entries significantly outperform late entries")
    elif timing.late_avg_clv < timing.early_avg_clv - 0.5:
        parts.append("Late entries underperform — timing matters")

    if len(leaks) > 0:
        leak_types = set(l["type"] for l in leaks)
        if "late_entry" in leak_types:
            parts.append(f"WARNING: {sum(1 for l in leaks if l['type']=='late_entry')} late entries detected")
        if "false_positive_ev" in leak_types:
            parts.append(f"WARNING: {sum(1 for l in leaks if l['type']=='false_positive_ev')} false positive EV cases")

    return " | ".join(parts)


def _generate_recommendations(
    dist, corr, timing, by_bookmaker, leaks, model_quality,
) -> list[str]:
    recs: list[str] = []

    if dist.mean_clv < -0.5:
        recs.append("URGENT: Review model — negative CLV indicates edge is illusory")
        recs.append("Systematic timing delay detected; optimize capture speed")

    if dist.positive_pct < 45:
        recs.append("Improve timing: capture odds earlier in the market cycle")

    if corr.interpretation.startswith("no_significant"):
        recs.append("Disconnect between EV+ and CLV — recalibrate probability estimates")

    if timing.late_pct + timing.dead_pct > 30:
        recs.append(f"High late entry rate ({timing.late_pct + timing.dead_pct:.0f}%); prioritize earlier capture")

    if by_bookmaker:
        worst = by_bookmaker[-1]
        if worst.avg_clv_pct < -1.0:
            recs.append(f"Avoid {worst.bookmaker}: consistently negative CLV ({worst.avg_clv_pct:.1f}%)")
        best = by_bookmaker[0]
        if best.avg_clv_pct > 1.0:
            recs.append(f"Prioritize {best.bookmaker}: best CLV ({best.avg_clv_pct:.1f}%)")

    if len(leaks) > 0:
        recs.append(f"Investigate {len(leaks)} system leaks (late entries, false EV positives)")

    if model_quality and "catastrophic" in model_quality:
        recs.append("Review risk management — high catastrophic bet rate")

    if not recs:
        recs.append("Continue monitoring — CLV is within acceptable range")
        recs.append("Scale up sample size for stronger statistical conclusions")

    return recs


def format_report_text(report: ClvReport) -> str:
    lines = [
        "=" * 60,
        "  CLV ANALYSIS REPORT",
        "=" * 60,
        f"  Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')} UTC",
        f"  Records:    {report.n_records}",
        f"  Events:     {report.n_events}",
        f"  Bookmakers: {report.n_bookmakers}",
        "",
        f"  OVERALL CLV: {report.overall_clv_pct:+.2f}%",
        f"  Verdict:     {report.verdict}",
        "",
    ]

    if report.distribution:
        d = report.distribution
        lines += [
            "  ── Distribution ──",
            f"  Mean CLV:     {d.mean_clv:+.2f}%",
            f"  Median CLV:   {d.median_clv:+.2f}%",
            f"  Std Dev:      {d.std_clv:.2f}%",
            f"  Range:        {d.min_clv:+.2f}% to {d.max_clv:+.2f}%",
            f"  Positive:     {d.positive_count} ({d.positive_pct:.1f}%)",
            f"  Negative:     {d.negative_count} ({d.negative_pct:.1f}%)",
            "",
            f"  Grade breakdown:",
        ]
        for grade in ClvGrade:
            count = d.grade_distribution.get(grade, 0)
            bar = "█" * (count * 20 // max(1, d.total_records))
            lines.append(f"    {grade.value:14s} {count:4d}  {bar}")

    if report.correlation:
        c = report.correlation
        lines += [
            "",
            f"  ── EV+ vs CLV Correlation ──",
            f"  Pearson r:    {c.pearson_r:+.4f}",
            f"  Spearman ρ:   {c.spearman_rho:+.4f}",
            f"  P-value:      {c.p_value:.4f}",
            f"  Status:       {c.interpretation}",
        ]

    if report.timing:
        t = report.timing
        lines += [
            "",
            f"  ── Timing Analysis ──",
            f"  Avg hours to close:  {t.avg_hours_to_close:.1f}h",
            f"  Early entry:         {t.early_pct:.0f}% (avg CLV: {t.early_avg_clv:+.2f}%)",
            f"  Optimal timing:      {t.optimal_pct:.0f}%",
            f"  Late entry:          {t.late_pct:.0f}% (avg CLV: {t.late_avg_clv:+.2f}%)",
            f"  Dead entry:          {t.dead_pct:.0f}%",
        ]

    if report.by_bookmaker:
        lines += ["", "  ── By Bookmaker ──"]
        lines.append(f"  {'Bookmaker':<14s} {'Bets':>5s} {'Avg CLV':>8s} {'Pos%':>6s} {'Elite%':>7s} {'Score':>6s}")
        lines.append(f"  {'─'*14} {'─'*5} {'─'*8} {'─'*6} {'─'*7} {'─'*6}")
        for bm in report.by_bookmaker:
            lines.append(
                f"  {bm.bookmaker:<14s} {bm.n_bets:5d} {bm.avg_clv_pct:>+7.2f}% "
                f"{bm.positive_rate:>5.1f}% {bm.elite_rate:>6.1f}% {bm.avg_timing_score:>5.2f}"
            )

    lines += [
        "",
        f"  ── Recommendations ──",
    ]
    for i, rec in enumerate(report.recommendations, 1):
        lines.append(f"  {i}. {rec}")

    lines += [
        "",
        "=" * 60,
    ]

    return "\n".join(lines)
