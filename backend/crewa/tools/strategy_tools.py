"""Strategy tools for CrewAI agents — ML predictions and decision support."""
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional


class PredictMatchOutcomeInput(BaseModel):
    home_team: str = Field(..., description="Home team name")
    away_team: str = Field(..., description="Away team name")
    sport: str = Field("soccer", description="Sport name")
    home_odds: Optional[float] = Field(None, description="Current home decimal odds")
    away_odds: Optional[float] = Field(None, description="Current away decimal odds")


class PredictMatchOutcomeTool(BaseTool):
    name: str = "predict_match_outcome"
    description: str = "Use trained ML models to predict match outcome probabilities."
    args_schema: type = PredictMatchOutcomeInput

    def _run(self, home_team: str, away_team: str, sport: str = "soccer",
             home_odds: Optional[float] = None, away_odds: Optional[float] = None) -> dict:
        try:
            from backend.ml.predict import predict_match
            result = predict_match(home_team, away_team, sport, home_odds, away_odds)
            return result
        except ImportError:
            pass
        except Exception as e:
            pass
        # Fallback: use existing value detection engine
        from decimal import Decimal
        if home_odds and away_odds:
            implied_home = 1.0 / home_odds
            implied_away = 1.0 / away_odds
            overround = implied_home + implied_away
            fair_home = implied_home / overround if overround > 0 else 0.5
            fair_away = implied_away / overround if overround > 0 else 0.5
            return {
                "home_win_prob": round(fair_home, 4),
                "away_win_prob": round(fair_away, 4),
                "model_used": "implied_probability (overround removal)",
                "home_edge_vs_market": round(fair_home - implied_home, 4) if home_odds else 0,
                "away_edge_vs_market": round(fair_away - implied_away, 4) if away_odds else 0,
            }
        from backend.domains.value.probability import implied_probability
        return {
            "home_win_prob": 0.5, "away_win_prob": 0.5,
            "model_used": "default_prior",
            "note": "Sem odds ou modelo ML disponivel — usando prior uniforme",
        }


class ExplainDecisionInput(BaseModel):
    context: str = Field(..., description="What decision needs explanation")
    data: dict = Field(default_factory=dict, description="Relevant data for the explanation")


class ExplainDecisionTool(BaseTool):
    name: str = "explain_decision"
    description: str = "Generate a human-readable explanation for a betting decision."
    args_schema: type = ExplainDecisionInput

    def _run(self, context: str, data: dict = {}) -> dict:
        return {
            "decision": context,
            "rationale": (
                f"Analise baseada em {data.get('n_opportunities', 0)} oportunidades. "
                f"EV medio: {data.get('avg_ev', 0)}%. "
                f"Confianca media: {data.get('avg_confidence', 0)}. "
                f"Risco: {data.get('avg_risk', 'MEDIUM')}. "
                f"Alocacao: {data.get('total_stake_pct', 0)}% do bankroll."
            ),
            "risk_warning": "Nunca aposte mais que 5% do bankroll em um unico evento.",
        }
