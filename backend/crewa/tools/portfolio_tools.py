"""Portfolio management tools for CrewAI agents."""
from datetime import datetime, timezone
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional


class OptimizeStakesInput(BaseModel):
    opportunities: list[dict] = Field(..., description="List of opportunities: [{'ev_pct':..., 'confidence':..., 'odd':..., 'risk_level':...}]")
    bankroll: float = Field(1000, description="Current bankroll")
    max_stake_pct: float = Field(0.05, description="Max stake as fraction of bankroll")


class OptimizeStakesTool(BaseTool):
    name: str = "optimize_stakes"
    description: str = "Optimize stake sizes across multiple opportunities using Kelly Criterion and portfolio constraints."
    args_schema: type = OptimizeStakesInput

    def _run(self, opportunities: list[dict], bankroll: float = 1000,
             max_stake_pct: float = 0.05) -> list[dict]:
        from backend.domains.value.kelly import compute_kelly
        sorted_ops = sorted(opportunities, key=lambda x: x.get("ev_pct", 0) * x.get("confidence", 0), reverse=True)
        results = []
        total_allocated = 0.0
        for op in sorted_ops:
            ev_pct = op.get("ev_pct", 0) / 100.0
            confidence = op.get("confidence", 0.5)
            odd = op.get("odd", 2.0)
            if ev_pct <= 0 or odd <= 1:
                continue
            fair_prob = (1 + ev_pct) / odd
            risk_factor = {"LOW": 1.0, "MEDIUM": 0.75, "HIGH": 0.5, "EXTREME": 0.25}.get(op.get("risk_level", "MEDIUM"), 0.75)
            kelly_frac = 0.25 * risk_factor * confidence
            kelly_result = compute_kelly(
                probability=min(fair_prob, 0.99),
                decimal_odd=odd,
                kelly_fraction=kelly_frac,
            )
            stake_frac = kelly_result.recommended_stake
            stake = min(bankroll * stake_frac, bankroll * max_stake_pct)
            remaining = bankroll * (1 - total_allocated)
            stake = min(stake, remaining * 0.5)
            results.append({
                "ev_pct": round(ev_pct * 100, 2),
                "odd": odd,
                "confidence": round(confidence, 2),
                "suggested_stake": round(stake, 2),
                "stake_pct_of_bankroll": round(stake / bankroll * 100, 2),
                "kelly_fraction_used": round(kelly_frac, 2),
                "risk_level": op.get("risk_level", "MEDIUM"),
                "is_viable": kelly_result.is_viable,
            })
            total_allocated += stake / bankroll
        return results


class RecommendTimingInput(BaseModel):
    event_start: str = Field(..., description="ISO datetime of event start")
    current_odd: float = Field(..., description="Current decimal odd")
    odd_history: Optional[list[float]] = Field(None, description="Recent odds history")
    volatility: Optional[str] = Field(None, description="Market volatility level")


class RecommendTimingTool(BaseTool):
    name: str = "recommend_timing"
    description: str = "Recommend optimal timing to place a bet based on event start and odds movement."
    args_schema: type = RecommendTimingInput

    def _run(self, event_start: str, current_odd: float,
             odd_history: Optional[list[float]] = None,
             volatility: Optional[str] = None) -> dict:
        start = datetime.fromisoformat(event_start)
        now = datetime.now(timezone.utc)
        hours_to_start = (start - now).total_seconds() / 3600 if start > now else 0

        if hours_to_start > 48:
            recommendation = "AGUARDAR — muito tempo para o inicio, odds podem melhorar"
            confidence = "baixa"
        elif hours_to_start > 12:
            recommendation = "AGUARDAR — janela de 12h antes do inicio e ideal"
            confidence = "media"
        elif hours_to_start > 2:
            recommendation = "AGORA — janela otima de colocacao"
            confidence = "alta"
        elif hours_to_start > 0:
            recommendation = "URGENTE — evento prestes a comecar"
            confidence = "alta"
        else:
            recommendation = "EXPIRADO — evento ja iniciou"
            confidence = "N/A"

        return {
            "hours_to_start": round(hours_to_start, 1),
            "recommendation": recommendation,
            "confidence": confidence,
            "current_odd": current_odd,
        }
