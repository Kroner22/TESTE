from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Optional

from scipy import stats as scipy_stats

from .models import (
    BookmakerClvStats, ClvCorrelation, ClvDistribution,
    ClvGrade, ClvRecord, TimingAnalysis, TimingEfficiency,
)


def compute_distribution(records: list[ClvRecord]) -> ClvDistribution:
    if not records:
        return ClvDistribution(
            total_records=0, mean_clv=0.0, median_clv=0.0, std_clv=0.0,
            min_clv=0.0, max_clv=0.0, positive_count=0, positive_pct=0.0,
            negative_count=0, negative_pct=0.0, neutral_count=0,
            grade_distribution={g: 0 for g in ClvGrade}, positive_sum_clv=0.0,
            negative_sum_clv=0.0,
        )

    clvs = [r.clv_pct for r in records]
    pos = [c for c in clvs if c > 0]
    neg = [c for c in clvs if c < 0]
    neu = [c for c in clvs if -0.5 <= c <= 0.5]

    grade_dist: dict[ClvGrade, int] = defaultdict(int)
    for r in records:
        grade_dist[r.grade] += 1

    return ClvDistribution(
        total_records=len(records),
        mean_clv=statistics.mean(clvs),
        median_clv=statistics.median(clvs),
        std_clv=statistics.stdev(clvs) if len(clvs) > 1 else 0.0,
        min_clv=min(clvs),
        max_clv=max(clvs),
        positive_count=len(pos),
        positive_pct=len(pos) / len(clvs) * 100,
        negative_count=len(neg),
        negative_pct=len(neg) / len(clvs) * 100,
        neutral_count=len(neu),
        grade_distribution=dict(grade_dist),
        positive_sum_clv=sum(pos),
        negative_sum_clv=sum(neg),
    )


def compute_by_bookmaker(records: list[ClvRecord]) -> list[BookmakerClvStats]:
    grouped: dict[str, list[ClvRecord]] = defaultdict(list)
    for r in records:
        grouped[r.bookmaker].append(r)

    stats_list: list[BookmakerClvStats] = []
    for bookmaker, recs in grouped.items():
        clvs = [r.clv_pct for r in recs]
        positive = [c for c in clvs if c > 0]
        elite = [c for c in clvs if c > 3.0]
        catastrophic = [c for c in clvs if c < -3.0]

        timings = {
            TimingEfficiency.EARLY: 1.0,
            TimingEfficiency.OPTIMAL: 0.8,
            TimingEfficiency.LATE: 0.3,
            TimingEfficiency.DEAD: 0.0,
        }
        timing_scores = [timings.get(r.timing_efficiency, 0.5) for r in recs]

        outcomes_by_clv: dict[str, list[float]] = defaultdict(list)
        for r in recs:
            outcomes_by_clv[r.outcome].append(r.clv_pct)

        best_outcome = max(outcomes_by_clv, key=lambda o: statistics.mean(outcomes_by_clv[o]))
        worst_outcome = min(outcomes_by_clv, key=lambda o: statistics.mean(outcomes_by_clv[o]))

        stats_list.append(BookmakerClvStats(
            bookmaker=bookmaker,
            n_bets=len(recs),
            avg_clv_pct=statistics.mean(clvs),
            median_clv_pct=statistics.median(clvs),
            std_clv_pct=statistics.stdev(clvs) if len(clvs) > 1 else 0.0,
            positive_rate=len(positive) / len(clvs) * 100,
            elite_rate=len(elite) / len(clvs) * 100,
            catastrophic_rate=len(catastrophic) / len(clvs) * 100,
            avg_timing_score=statistics.mean(timing_scores),
            best_outcome=best_outcome,
            worst_outcome=worst_outcome,
        ))

    return sorted(stats_list, key=lambda s: s.avg_clv_pct, reverse=True)


def compute_correlation(records: list[ClvRecord]) -> ClvCorrelation:
    if len(records) < 5:
        return ClvCorrelation(
            pearson_r=0.0, spearman_rho=0.0, p_value=1.0,
            interpretation="insufficient_data",
        )

    evs = [r.simulated_ev for r in records]
    clvs = [r.clv_pct for r in records]

    try:
        pearson_r, p_value = scipy_stats.pearsonr(evs, clvs)
    except Exception:
        pearson_r, p_value = 0.0, 1.0

    try:
        spearman_rho, _ = scipy_stats.spearmanr(evs, clvs)
    except Exception:
        spearman_rho = 0.0

    abs_r = abs(pearson_r)
    if abs_r > 0.7 and p_value < 0.01:
        interpretation = "strong_correlation_model_validated"
    elif abs_r > 0.4 and p_value < 0.05:
        interpretation = "moderate_correlation_partial_validity"
    elif abs_r > 0.2 and p_value < 0.1:
        interpretation = "weak_correlation_more_data_needed"
    elif p_value >= 0.1:
        interpretation = "no_significant_correlation_model_uncorrelated_with_market"
    else:
        interpretation = "minimal_correlation"

    return ClvCorrelation(
        pearson_r=round(pearson_r, 4),
        spearman_rho=round(spearman_rho, 4),
        p_value=round(p_value, 4),
        interpretation=interpretation,
    )


def compute_timing_analysis(records: list[ClvRecord]) -> TimingAnalysis:
    if not records:
        return TimingAnalysis(
            avg_hours_to_close=0.0, early_pct=0.0, optimal_pct=0.0,
            late_pct=0.0, dead_pct=0.0, best_timing_clv=0.0,
            worst_timing_clv=0.0, early_avg_clv=0.0, late_avg_clv=0.0,
        )

    hours = [r.hours_to_close for r in records]
    all_clvs = [r.clv_pct for r in records]
    timing_map = defaultdict(list)
    for r in records:
        timing_map[r.timing_efficiency].append(r.clv_pct)

    n = len(records)
    early_clvs = timing_map.get(TimingEfficiency.EARLY, [])
    late_clvs = timing_map.get(TimingEfficiency.LATE, []) + timing_map.get(TimingEfficiency.DEAD, [])

    return TimingAnalysis(
        avg_hours_to_close=statistics.mean(hours),
        early_pct=len(early_clvs) / n * 100,
        optimal_pct=len(timing_map.get(TimingEfficiency.OPTIMAL, [])) / n * 100,
        late_pct=len(timing_map.get(TimingEfficiency.LATE, [])) / n * 100,
        dead_pct=len(timing_map.get(TimingEfficiency.DEAD, [])) / n * 100,
        best_timing_clv=max(all_clvs) if all_clvs else 0.0,
        worst_timing_clv=min(all_clvs) if all_clvs else 0.0,
        early_avg_clv=statistics.mean(early_clvs) if early_clvs else 0.0,
        late_avg_clv=statistics.mean(late_clvs) if late_clvs else 0.0,
    )


def compute_t_test(records: list[ClvRecord]) -> dict:
    clvs = [r.clv_pct for r in records]
    if len(clvs) < 2:
        return {"t_statistic": 0.0, "p_value": 1.0, "significant": False, "interpretation": "insufficient_data"}

    try:
        t_stat, p_value = scipy_stats.ttest_1samp(clvs, 0.0)
    except Exception:
        t_stat, p_value = 0.0, 1.0

    return {
        "t_statistic": round(t_stat, 4),
        "p_value": round(p_value, 4),
        "significant": p_value < 0.05,
        "mean": round(statistics.mean(clvs), 4),
        "interpretation": (
            "clv_significantly_positive" if t_stat > 0 and p_value < 0.05
            else "clv_significantly_negative" if t_stat < 0 and p_value < 0.05
            else "clv_not_significantly_different_from_zero"
        ),
    }


def compute_model_quality(records: list[ClvRecord], distribution: ClvDistribution, correlation: ClvCorrelation) -> str:
    if len(records) < 10:
        return "insufficient_data"

    signals = []

    if distribution.positive_pct > 60:
        signals.append("strong_positive_bias")
    elif distribution.positive_pct > 50:
        signals.append("slight_positive_bias")
    else:
        signals.append("no_positive_bias")

    if correlation.interpretation.startswith("strong"):
        signals.append("model_predicts_market")
    elif correlation.interpretation.startswith("no_significant"):
        signals.append("model_disconnected_from_market")

    early_records = [r for r in records if r.timing_efficiency == TimingEfficiency.EARLY]
    if len(early_records) >= 5:
        early_avg = statistics.mean([r.clv_pct for r in early_records])
        if early_avg > 1.0:
            signals.append("early_entry_profitable")
        elif early_avg < -1.0:
            signals.append("early_entry_harmful")

    if sum(1 for r in records if r.clv_pct < -3.0) > len(records) * 0.1:
        signals.append("high_catastrophic_rate")

    return " | ".join(signals)
