import pytest
from decimal import Decimal

from backend.agents.models import (
    AgentId, AgentState, EventPriority, MovementDirection,
    MovementSpeed, PatternType, AlertSeverity,
    OddsTick, OddsMovementEvent, DetectedPattern,
    VolatilitySnapshot, RiskAssessment, AgentAlert,
    AgentMessage, AgentHealth,
)


class TestModels:
    def test_odds_tick_change_pct(self):
        tick = OddsTick(event_id="e1", bookmaker="B", outcome="home",
                         old_odd=Decimal("2.0"), new_odd=Decimal("2.2"))
        assert tick.change_pct == 10.0
        assert tick.direction == MovementDirection.UP

    def test_odds_tick_drop(self):
        tick = OddsTick(event_id="e1", bookmaker="B", outcome="home",
                         old_odd=Decimal("2.0"), new_odd=Decimal("1.8"))
        assert abs(tick.change_pct + 10.0) < 0.01
        assert tick.direction == MovementDirection.DOWN

    def test_odds_tick_flat(self):
        tick = OddsTick(event_id="e1", bookmaker="B", outcome="home",
                         old_odd=Decimal("2.0"), new_odd=Decimal("2.003"))
        assert tick.direction == MovementDirection.FLAT

    def test_odds_tick_zero_old(self):
        tick = OddsTick(event_id="e1", bookmaker="B", outcome="home",
                         old_odd=Decimal("0"), new_odd=Decimal("2.0"))
        assert tick.change_pct == 0.0

    def test_volatility_snapshot_is_volatile(self):
        snap = VolatilitySnapshot(event_id="e1", sport="soccer",
                                   overall_volatility=0.6, odds_volatility=0.6,
                                   volume_volatility=0.5, spread_volatility=0.5,
                                   regime="volatile", trend_strength=0.5,
                                   mean_reversion_probability=0.3)
        assert snap.is_volatile is True
        assert snap.is_chaotic is False

    def test_volatility_chaotic(self):
        snap = VolatilitySnapshot(event_id="e1", sport="soccer",
                                   overall_volatility=0.8, odds_volatility=0.8,
                                   volume_volatility=0.7, spread_volatility=0.7,
                                   regime="chaotic", trend_strength=0.8,
                                   mean_reversion_probability=0.1)
        assert snap.is_volatile is True
        assert snap.is_chaotic is True

    def test_risk_assessment_high(self):
        risk = RiskAssessment(event_id="e1", sport="soccer", overall_risk=0.6,
                               market_risk=0.7, timing_risk=0.5, liquidity_risk=0.4,
                               volatility_risk=0.6, information_risk=0.8,
                               risk_level="HIGH", factors=["volatility:0.60"])
        assert risk.risk_level == "HIGH"

    def test_agent_message_key_unique(self):
        m1 = AgentMessage(source=AgentId.ODDS_MOVEMENT, target=AgentId.PATTERN_DETECTOR, msg_type="tick")
        m2 = AgentMessage(source=AgentId.ODDS_MOVEMENT, target=AgentId.PATTERN_DETECTOR, msg_type="tick")
        assert m1.key != m2.key

    def test_agent_health_unhealthy(self):
        health = AgentHealth(agent_id=AgentId.ODDS_MOVEMENT, state=AgentState.ERROR,
                              uptime_seconds=100, messages_processed=50, errors_last_hour=15,
                              is_healthy=False)
        assert health.is_healthy is False

    def test_agent_priority_order(self):
        assert EventPriority.CRITICAL > EventPriority.HIGH > EventPriority.MEDIUM > EventPriority.LOW

    def test_detected_pattern_actionable(self):
        p = DetectedPattern(pattern_type=PatternType.STEAM_MOVE, event_id="e1",
                             sport="tennis", confidence=0.9,
                             description="Steam move detected", is_actionable=True)
        assert p.is_actionable is True
        assert p.pattern_type == PatternType.STEAM_MOVE

    def test_agent_alert_severity(self):
        alert = AgentAlert(alert_id="a1", source=AgentId.ALERT_MANAGER,
                            severity=AlertSeverity.CRITICAL,
                            title="test", description="critical alert")
        assert alert.severity == AlertSeverity.CRITICAL

    def test_message_priority_default(self):
        m = AgentMessage(source=AgentId.ORCHESTRATOR, target=AgentId.LEARNING, msg_type="test")
        assert m.priority == EventPriority.MEDIUM
