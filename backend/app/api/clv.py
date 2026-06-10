from __future__ import annotations

import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.plan_limiter import require_plan
from backend.domains.clv.calculator import build_clv_record, detect_leak
from backend.domains.clv.analyzer import (
    compute_distribution, compute_by_bookmaker, compute_correlation,
    compute_timing_analysis, compute_t_test, compute_model_quality,
)
from backend.domains.clv.report import generate_clv_report, format_report_text
from backend.domains.clv.models import ClvRecord

router = APIRouter(prefix="/api/v1/clv", tags=["clv"])

_lock = threading.Lock()
_records: list[ClvRecord] = []


MAX_RECORDS = 10_000


@router.post("/records")
def submit_records(payload: list[dict]):
    if not payload:
        raise HTTPException(400, "Empty payload")
    parsed: list[ClvRecord] = []
    for item in payload:
        try:
            record = _parse_record(item)
            parsed.append(record)
        except Exception as e:
            raise HTTPException(400, f"Invalid record: {e}")
    with _lock:
        _records.extend(parsed)
        if len(_records) > MAX_RECORDS:
            _records[:] = _records[-MAX_RECORDS:]
    return {"submitted": len(parsed), "total": len(_records)}


@router.get("/records")
def list_records(limit: int = Query(200, ge=1, le=5000), _=Depends(require_plan("paid"))):
    with _lock:
        subset = _records[-limit:]
    return [_serialize_record(r) for r in subset]


@router.get("/report")
def get_report(_=Depends(require_plan("paid"))):
    with _lock:
        if not _records:
            raise HTTPException(404, "No CLV records available. Submit records first via POST /api/v1/clv/records")
        report = generate_clv_report(list(_records))
    return _serialize_report(report)


@router.get("/report/text")
def get_report_text(_=Depends(require_plan("paid"))):
    with _lock:
        if not _records:
            raise HTTPException(404, "No CLV records available")
        report = generate_clv_report(list(_records))
    return {"text": format_report_text(report)}


@router.get("/distribution")
def get_distribution(_=Depends(require_plan("paid"))):
    with _lock:
        if not _records:
            raise HTTPException(404, "No CLV records")
        dist = compute_distribution(_records)
    return _serialize_distribution(dist)


@router.get("/by-bookmaker")
def get_by_bookmaker(_=Depends(require_plan("paid"))):
    with _lock:
        if not _records:
            raise HTTPException(404, "No CLV records")
        stats = compute_by_bookmaker(_records)
    return [_serialize_bookmaker_stats(s) for s in stats]


@router.get("/timing")
def get_timing(_=Depends(require_plan("paid"))):
    with _lock:
        if not _records:
            raise HTTPException(404, "No CLV records")
        timing = compute_timing_analysis(_records)
    return _serialize_timing(timing)


@router.get("/leaks")
def get_leaks(_=Depends(require_plan("paid"))):
    with _lock:
        if not _records:
            raise HTTPException(404, "No CLV records")
        leaks = detect_leak(_records)
    return {"leaks": leaks, "count": len(leaks)}


@router.get("/correlation")
def get_correlation(_=Depends(require_plan("paid"))):
    with _lock:
        if not _records:
            raise HTTPException(404, "No CLV records")
        corr = compute_correlation(_records)
    return _serialize_correlation(corr)


@router.get("/t-test")
def get_t_test(_=Depends(require_plan("paid"))):
    with _lock:
        if not _records:
            raise HTTPException(404, "No CLV records")
        t_test = compute_t_test(_records)
    return {
        "t_statistic": float(t_test["t_statistic"]),
        "p_value": float(t_test["p_value"]),
        "significant": bool(t_test["significant"]),
        "mean": float(t_test["mean"]),
        "interpretation": str(t_test["interpretation"]),
    }


@router.delete("/records")
def clear_records():
    with _lock:
        n = len(_records)
        _records.clear()
    return {"cleared": n}


def _parse_record(item: dict) -> ClvRecord:
    return build_clv_record(
        event_id=item["event_id"],
        market=item.get("market", "h2h"),
        outcome=item["outcome"],
        bookmaker=item["bookmaker"],
        captured_odd=Decimal(str(item["captured_odd"])),
        captured_at=datetime.fromisoformat(item["captured_at"]),
        closing_odd=Decimal(str(item["closing_odd"])),
        closed_at=datetime.fromisoformat(item["closed_at"]),
        opening_odd=Decimal(str(item.get("opening_odd", item["captured_odd"]))),
        opening_at=datetime.fromisoformat(item.get("opening_at", item["captured_at"])),
        simulated_ev=item.get("simulated_ev", 0.0),
        simulated_kelly=item.get("simulated_kelly"),
        model_edge=item.get("model_edge"),
    )


def _serialize_record(r: ClvRecord) -> dict:
    return {
        "event_id": r.event_id,
        "market": r.market,
        "outcome": r.outcome,
        "bookmaker": r.bookmaker,
        "captured_odd": float(r.captured_odd),
        "captured_prob": r.captured_prob,
        "captured_at": r.captured_at.isoformat(),
        "closing_odd": float(r.closing_odd),
        "closing_prob": r.closing_prob,
        "closed_at": r.closed_at.isoformat(),
        "opening_odd": float(r.opening_odd),
        "opening_at": r.opening_at.isoformat(),
        "clv_pct": r.clv_pct,
        "timing_efficiency": r.timing_efficiency.value,
        "hours_to_close": r.hours_to_close,
        "grade": r.grade.value,
        "odds_movement": r.odds_movement,
        "simulated_ev": r.simulated_ev,
    }


def _serialize_report(report) -> dict:
    result = {
        "generated_at": report.generated_at.isoformat(),
        "n_records": report.n_records,
        "n_events": report.n_events,
        "n_bookmakers": report.n_bookmakers,
        "overall_clv_pct": report.overall_clv_pct,
        "verdict": report.verdict,
        "recommendations": report.recommendations,
        "model_quality": report.model_quality,
    }
    if report.distribution:
        result["distribution"] = _serialize_distribution(report.distribution)
    if report.correlation:
        result["correlation"] = _serialize_correlation(report.correlation)
    if report.timing:
        result["timing"] = _serialize_timing(report.timing)
    if report.by_bookmaker:
        result["by_bookmaker"] = [_serialize_bookmaker_stats(s) for s in report.by_bookmaker]
    return result


def _serialize_distribution(d) -> dict:
    return {
        "total_records": d.total_records,
        "mean_clv": d.mean_clv,
        "median_clv": d.median_clv,
        "std_clv": d.std_clv,
        "min_clv": d.min_clv,
        "max_clv": d.max_clv,
        "positive_count": d.positive_count,
        "positive_pct": d.positive_pct,
        "negative_count": d.negative_count,
        "negative_pct": d.negative_pct,
        "neutral_count": d.neutral_count,
        "grade_distribution": {k.value: v for k, v in d.grade_distribution.items()},
    }


def _serialize_bookmaker_stats(s) -> dict:
    return {
        "bookmaker": s.bookmaker,
        "n_bets": s.n_bets,
        "avg_clv_pct": s.avg_clv_pct,
        "median_clv_pct": s.median_clv_pct,
        "std_clv_pct": s.std_clv_pct,
        "positive_rate": s.positive_rate,
        "elite_rate": s.elite_rate,
        "catastrophic_rate": s.catastrophic_rate,
        "avg_timing_score": s.avg_timing_score,
        "best_outcome": s.best_outcome,
        "worst_outcome": s.worst_outcome,
    }


def _serialize_correlation(c) -> dict:
    return {
        "pearson_r": c.pearson_r,
        "spearman_rho": c.spearman_rho,
        "p_value": c.p_value,
        "interpretation": c.interpretation,
    }


def _serialize_timing(t) -> dict:
    return {
        "avg_hours_to_close": t.avg_hours_to_close,
        "early_pct": t.early_pct,
        "optimal_pct": t.optimal_pct,
        "late_pct": t.late_pct,
        "dead_pct": t.dead_pct,
        "best_timing_clv": t.best_timing_clv,
        "worst_timing_clv": t.worst_timing_clv,
        "early_avg_clv": t.early_avg_clv,
        "late_avg_clv": t.late_avg_clv,
    }
