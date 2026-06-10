"""
detector.py — Main value bet detection orchestrator.

Pipeline:
  1. Receive market odds from one or more bookmakers
  2. Aggregate best odds across bookmakers
  3. Remove overround (user-chosen method: basic/power/shin)
  4. Compute fair probabilities
  5. Calculate EV for each outcome
  6. Compute Kelly stakes
  7. Score confidence
  8. Classify risk
  9. Grade opportunity
  10. Return list of ValueOpportunity objects
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

from .models import (
    MarketOdds,
    ValueOpportunity,
    OverroundMethod,
    ValueGrade,
    RiskLevel,
)
from .probability import (
    compute_fair_probabilities,
    market_overround,
    best_odds_across_bookmakers,
)
from .ev import (
    compute_expected_value,
    classify_value_grade,
    is_statistically_significant,
)
from .kelly import compute_kelly, full_kelly
from .confidence import compute_confidence
from .risk import compute_risk_score


class ValueDetector:
    """
    Detects value betting opportunities from market odds.
    
    Usage:
        detector = ValueDetector()
        opportunities = detector.scan(market_odds_list, model_probs={...})
    """

    def __init__(
        self,
        overround_method: OverroundMethod = OverroundMethod.BASIC,
        min_ev: float = 0.01,
        min_confidence: float = 0.15,
        kelly_fraction: float = 0.5,
        bankroll_pct_limit: float = 0.25,
        min_stake_pct: float = 0.005,
    ):
        self.overround_method = overround_method
        self.min_ev = min_ev
        self.min_confidence = min_confidence
        self.kelly_fraction = kelly_fraction
        self.bankroll_pct_limit = bankroll_pct_limit
        self.min_stake_pct = min_stake_pct

    def scan(
        self,
        market_odds_list: list[MarketOdds],
        model_probabilities: Optional[dict[str, dict[str, float]]] = None,
        edge_history: Optional[dict[str, list[float]]] = None,
        hours_to_event: Optional[float] = None,
        regime: Optional[str] = None,
        n_bookmakers: int = 1,
    ) -> list[ValueOpportunity]:
        """
        Scan market odds for value opportunities.
        
        Args:
            market_odds_list: One or more MarketOdds objects
            model_probabilities: {"event_id:outcome": prob} from ML model
            edge_history: {"event_id:outcome": [ev_estimates]} for stability
            hours_to_event: Time until event starts
            regime: Market regime ("STABLE", "SEMI_STABLE", "CHAOTIC")
            n_bookmakers: Number of bookmakers offering this market
        
        Returns:
            List of ValueOpportunity, sorted by EV descending.
        """
        opportunities: list[ValueOpportunity] = []

        for market in market_odds_list:
            odds_float = {k: float(v) for k, v in market.outcomes.items()}
            if not odds_float:
                continue

            # Step 1-3: Remove overround, get fair (de-margined) probabilities
            fair = compute_fair_probabilities(odds_float, self.overround_method)

            # Step 4-5: For each outcome, calculate EV
            key = f"{market.event_id}:"
            for outcome, fair_prob in fair.outcomes.items():
                if fair_prob <= 0 or fair_prob >= 1:
                    continue

                odd = odds_float[outcome]
                impl_prob = 1.0 / odd

                # Use model probability if available (it's an independent estimate).
                # Otherwise fall back to the de-margined implied probability.
                model_prob = None
                if model_probabilities:
                    model_prob = model_probabilities.get(f"{key}{outcome}")
                prob_estimate = model_prob if model_prob is not None else fair_prob

                ev = compute_expected_value(prob_estimate, odd)

                if ev <= self.min_ev:
                    continue

                # Step 6: Kelly stake
                kelly_result = compute_kelly(
                    probability=prob_estimate,
                    decimal_odd=odd,
                    bankroll_pct_limit=self.bankroll_pct_limit,
                    min_stake_pct=self.min_stake_pct,
                    kelly_fraction=self.kelly_fraction,
                )

                # Step 7: Confidence
                edge_hist = edge_history.get(f"{key}{outcome}") if edge_history else None

                confidence = compute_confidence(
                    sample_size=len(edge_hist) if edge_hist else 0,
                    model_prob=model_prob if model_prob is not None else 0.5,
                    brier_score=None,
                    historical_accuracy=None,
                    total_bets=len(edge_hist) if edge_hist else 0,
                    edge_estimates=edge_hist,
                )

                if confidence < self.min_confidence:
                    continue

                # Step 8: Risk
                risk_score, risk_level = compute_risk_score(
                    edge_estimates=edge_hist,
                    hours_to_event=hours_to_event,
                    regime=regime,
                    n_bookmakers=n_bookmakers,
                )

                # Step 9: Grade
                significant = is_statistically_significant(
                    ev, prob_estimate, odd,
                    sample_size=len(edge_hist) if edge_hist else 100,
                )
                grade = classify_value_grade(ev, confidence, significant)

                # Expiry: 6 hours from now or until event start
                if hours_to_event is not None and hours_to_event > 0:
                    expires = datetime.now(timezone.utc) + timedelta(hours=min(6, hours_to_event))
                else:
                    expires = datetime.now(timezone.utc) + timedelta(hours=6)

                opportunities.append(ValueOpportunity(
                    event_id=market.event_id,
                    sport=market.sport,
                    market=market.market,
                    outcome=outcome,
                    bookmaker_odd=Decimal(str(odd)),
                    fair_probability=round(fair_prob, 4),
                    implied_probability=round(impl_prob, 4),
                    expected_value=round(ev, 4),
                    edge_pct=round(ev * 100, 2),
                    kelly_stake=kelly_result.recommended_stake,
                    confidence=round(confidence, 3),
                    risk_score=risk_score,
                    risk_level=risk_level,
                    grade=grade,
                    model_probability=model_prob,
                    sample_size=len(edge_hist) if edge_hist else 0,
                    expires_at=expires,
                ))

        # Sort by EV descending
        opportunities.sort(key=lambda o: o.expected_value, reverse=True)
        return opportunities
