"""Performance audit tools for CrewAI agents."""
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional


class GetPerformanceSummaryInput(BaseModel):
    days: int = Field(30, description="Lookback period in days")


class GetPerformanceSummaryTool(BaseTool):
    name: str = "get_performance_summary"
    description: str = "Get aggregate performance metrics: win rate, P&L, ROI, Sharpe ratio."
    args_schema: type = GetPerformanceSummaryInput

    def _run(self, days: int = 30) -> dict:
        from datetime import datetime, timedelta, timezone
        from backend.app.database import SessionLocal, PaperTradeRecord
        from sqlalchemy import func
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        db = SessionLocal()
        total = db.query(PaperTradeRecord).filter(
            PaperTradeRecord.exit_timestamp >= cutoff,
            PaperTradeRecord.pnl.isnot(None),
        ).count()
        winners = db.query(PaperTradeRecord).filter(
            PaperTradeRecord.exit_timestamp >= cutoff,
            PaperTradeRecord.pnl > 0,
        ).count()
        total_pnl = db.query(func.sum(PaperTradeRecord.pnl)).filter(
            PaperTradeRecord.exit_timestamp >= cutoff,
            PaperTradeRecord.pnl.isnot(None),
        ).scalar() or 0
        total_stake = db.query(func.sum(PaperTradeRecord.stake)).filter(
            PaperTradeRecord.exit_timestamp >= cutoff,
        ).scalar() or 1
        db.close()

        win_rate = (winners / total * 100) if total > 0 else 0
        roi = (float(total_pnl) / float(total_stake) * 100) if total_stake > 0 else 0
        return {
            "period_days": days,
            "total_trades": total,
            "winners": winners,
            "losers": total - winners,
            "win_rate_pct": round(win_rate, 1),
            "total_pnl": round(float(total_pnl), 2),
            "roi_pct": round(roi, 2),
            "is_profitable": float(total_pnl) > 0,
        }


class GetGradePerformanceInput(BaseModel):
    days: int = Field(60, description="Lookback period in days")


class GetGradePerformanceTool(BaseTool):
    name: str = "get_grade_performance"
    description: str = "Get performance broken down by value grade to see which grades are most profitable."
    args_schema: type = GetGradePerformanceInput

    def _run(self, days: int = 60) -> list[dict]:
        from datetime import datetime, timedelta, timezone
        from backend.app.database import SessionLocal, PaperTradeRecord, OpportunityRecord
        from sqlalchemy import func
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        db = SessionLocal()
        rows = db.query(
            OpportunityRecord.value_grade,
            func.count(PaperTradeRecord.id),
            func.sum(PaperTradeRecord.pnl),
            func.avg(PaperTradeRecord.pnl),
        ).join(
            PaperTradeRecord,
            PaperTradeRecord.event_id == OpportunityRecord.event_id,
        ).filter(
            PaperTradeRecord.exit_timestamp >= cutoff,
            PaperTradeRecord.pnl.isnot(None),
        ).group_by(OpportunityRecord.value_grade).all()
        db.close()
        return [
            {
                "grade": r[0],
                "trades": r[1],
                "total_pnl": round(float(r[2] or 0), 2),
                "avg_pnl": round(float(r[3] or 0), 2),
            }
            for r in rows
        ]
