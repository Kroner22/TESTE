"""Risk assessment tools for CrewAI agents."""
from datetime import datetime, timezone
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional


class AssessOpportunityRiskInput(BaseModel):
    event_id: str = Field(..., description="Event ID")
    outcome: str = Field(..., description="Outcome (home, away, draw)")
    current_bankroll: float = Field(1000, description="Current bankroll in dollars")


class AssessOpportunityRiskTool(BaseTool):
    name: str = "assess_opportunity_risk"
    description: str = "Assess risk level for a specific opportunity using the risk engine."
    args_schema: type = AssessOpportunityRiskInput

    def _run(self, event_id: str, outcome: str, current_bankroll: float = 1000) -> dict:
        from backend.app.database import SessionLocal, OpportunityRecord, Event
        from backend.domains.value.risk import compute_risk_score, classify_risk
        db = SessionLocal()
        opp = db.query(OpportunityRecord).filter(
            OpportunityRecord.event_id == event_id,
            OpportunityRecord.outcome == outcome,
        ).first()
        evt = db.query(Event).filter(Event.event_id == event_id).first()
        db.close()

        if not opp:
            return {"error": "Opportunity not found"}
        if not evt:
            return {"error": "Event not found"}

        hours_to_start = (evt.start_time - datetime.now(timezone.utc)).total_seconds() / 3600 if evt.start_time else 72

        risk_score = compute_risk_score(
            edge_volatility=float(opp.edge_score or 0) / 10 if opp.edge_score else 0.2,
            time_pressure=max(0, 72 - hours_to_start) / 72,
            regime_stability=0.7,
            market_depth=0.5,
        )
        risk_level = classify_risk(risk_score)

        from backend.domains.value.kelly import compute_kelly
        kelly = compute_kelly(
            probability=float(opp.fair_prob or 0.5),
            decimal_odd=float(opp.odd or 2.0),
            kelly_fraction=0.25,
        )

        return {
            "event_id": event_id,
            "outcome": outcome,
            "risk_score": round(risk_score, 3),
            "risk_level": risk_level.value,
            "kelly_stake_pct": round(kelly.recommended_stake * 100, 2),
            "kelly_stake_dollars": round(kelly.recommended_stake * current_bankroll, 2),
            "is_viable": kelly.is_viable,
            "expected_growth": round(kelly.expected_growth, 6),
            "hours_to_start": round(hours_to_start, 1),
        }


class AssessPortfolioRiskInput(BaseModel):
    exposures: list[dict] = Field(..., description="List of current positions: [{'event_id':..., 'stake':..., 'odd':...}]")
    max_risk_per_event: float = Field(0.05, description="Max fraction of bankroll per event")
    max_correlation_risk: float = Field(0.15, description="Max fraction in correlated outcomes")


class AssessPortfolioRiskTool(BaseTool):
    name: str = "assess_portfolio_risk"
    description: str = "Analyze portfolio-level risk across all active positions."
    args_schema: type = AssessPortfolioRiskInput

    def _run(self, exposures: list[dict], max_risk_per_event: float = 0.05,
             max_correlation_risk: float = 0.15) -> dict:
        total_exposure = sum(e.get("stake", 0) for e in exposures)
        event_groups = {}
        for e in exposures:
            event_groups.setdefault(e.get("event_id", "unknown"), []).append(e.get("stake", 0))
        max_event_exposure = max((sum(stakes) for stakes in event_groups.values()), default=0)
        n_events = len(event_groups)
        return {
            "total_exposure": round(total_exposure, 2),
            "n_positions": len(exposures),
            "n_events": n_events,
            "max_per_event": round(max_event_exposure, 2),
            "is_diversified": n_events >= 3 and max_event_exposure <= max_risk_per_event * 1000,
            "suggestion": "Reduzir concentracao" if max_event_exposure > max_risk_per_event * 1000 else "Carteira equilibrada",
        }
