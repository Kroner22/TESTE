from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from .models import (
    OddsTimeSeries, OddsTick, BookmakerProfile, BookmakerStyle,
    BookmakerBehaviorReport,
)


def analyze_bookmaker(
    series_list: list[OddsTimeSeries],
    min_ticks: int = 3,
) -> BookmakerBehaviorReport:
    bk_data = defaultdict(lambda: {
        "reaction_times": [],
        "adjustments": [],
        "overrounds": [],
    })

    for s in series_list:
        bk = s.bookmaker
        ticks = s.ticks
        if len(ticks) < min_ticks:
            continue

        # Reaction times
        for i in range(2, len(ticks)):
            dt = (ticks[i].timestamp - ticks[i - 1].timestamp).total_seconds()
            bk_data[bk]["reaction_times"].append(dt)

        # Adjustment magnitudes
        for i in range(1, len(ticks)):
            prev = float(ticks[i - 1].odd)
            curr = float(ticks[i].odd)
            if prev > 0:
                bk_data[bk]["adjustments"].append(abs(curr - prev) / prev * 100)

        # Overround (simple: all outcomes in this event)
        if len(ticks) >= 2:
            implied = float(Decimal("1") / ticks[-1].odd) if ticks[-1].odd > 1 else 0
            bk_data[bk]["overrounds"].append(implied)

    profiles = {}
    total_reactions = []
    market_share = defaultdict(float)
    max_agg = 0.0
    max_cons = float("inf")
    most_agg = None
    most_cons = None

    for bk_name, data in bk_data.items():
        rt = data["reaction_times"]
        adj = data["adjustments"]
        ovr = data["overrounds"]

        avg_rt = sum(rt) / len(rt) if rt else 60.0
        avg_adj = sum(adj) / len(adj) if adj else 0.0
        avg_ovr = sum(ovr) / len(ovr) if ovr else 0.05
        n = max(len(rt), len(adj), len(ovr))

        agg_score = _aggressiveness(avg_adj, avg_rt)
        pro_score = _proactiveness(avg_rt)
        cons_score = _consistency(adj)

        style = _classify_style(agg_score, pro_score, cons_score)

        profile = BookmakerProfile(
            bookmaker=bk_name,
            style=style,
            reaction_time_avg_seconds=round(avg_rt, 2),
            adjustment_magnitude_avg=round(avg_adj, 4),
            overround_avg=round(avg_ovr, 4),
            aggressiveness_score=round(agg_score, 4),
            proactiveness_score=round(pro_score, 4),
            consistency_score=round(cons_score, 4),
            samples_analyzed=n,
        )
        profiles[bk_name] = profile
        total_reactions.extend(rt)

        share = 1.0 - min(avg_rt / 120.0, 1.0)
        market_share[bk_name] = round(share, 4)

        if agg_score > max_agg:
            max_agg = agg_score
            most_agg = bk_name
        if cons_score < max_cons and n >= 3:
            max_cons = cons_score
            most_cons = bk_name

    avg_rt_all = sum(total_reactions) / len(total_reactions) if total_reactions else 0.0
    total_share = sum(market_share.values())
    if total_share > 0:
        market_share = {k: v / total_share * 100 for k, v in market_share.items()}

    return BookmakerBehaviorReport(
        profiles=profiles,
        market_share_by_reaction=market_share,
        avg_reaction_time=round(avg_rt_all, 2),
        most_aggressive=most_agg,
        most_conservative=most_cons,
    )


def _classify_style(agg: float, pro: float, cons: float) -> BookmakerStyle:
    if agg > 0.7 and pro > 0.5:
        return BookmakerStyle.AGGRESSIVE
    if cons < 0.3 and agg < 0.3:
        return BookmakerStyle.CONSERVATIVE
    if pro > 0.6:
        return BookmakerStyle.PROACTIVE
    if pro < 0.3:
        return BookmakerStyle.REACTIVE
    return BookmakerStyle.MIXED


def _aggressiveness(avg_adjustment: float, avg_reaction_time: float) -> float:
    adj_score = min(avg_adjustment / 3.0, 1.0)
    rt_score = 1.0 - min(avg_reaction_time / 120.0, 1.0)
    return adj_score * 0.6 + rt_score * 0.4


def _proactiveness(avg_reaction_time: float) -> float:
    return 1.0 - min(avg_reaction_time / 180.0, 1.0)


def _consistency(adjustments: list[float]) -> float:
    if len(adjustments) < 3:
        return 0.5
    mean_a = sum(adjustments) / len(adjustments)
    variance = sum((a - mean_a) ** 2 for a in adjustments) / len(adjustments)
    std = math.sqrt(variance)
    return 1.0 - min(std / 2.0, 1.0)


def compare_bookmaker_pairs(
    profiles: dict[str, BookmakerProfile],
) -> list[dict]:
    comparisons = []
    names = list(profiles.keys())
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = profiles[names[i]], profiles[names[j]]
            rt_diff = a.reaction_time_avg_seconds - b.reaction_time_avg_seconds
            comparisons.append({
                "pair": f"{a.bookmaker}_{b.bookmaker}",
                "reaction_time_diff_sec": round(rt_diff, 2),
                "faster": a.bookmaker if rt_diff < 0 else b.bookmaker,
                "agg_diff": round(a.aggressiveness_score - b.aggressiveness_score, 4),
                "more_aggressive": a.bookmaker if a.aggressiveness_score > b.aggressiveness_score else b.bookmaker,
            })
    return sorted(comparisons, key=lambda x: abs(x["reaction_time_diff_sec"]), reverse=True)
