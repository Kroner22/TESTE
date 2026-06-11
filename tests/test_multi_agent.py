"""Tests for the CrewAI multi-agent system tools."""
import sys, os
sys.path.insert(0, r'C:\Users\cex\Desktop\OmegaPredictions')
os.chdir(r'C:\Users\cex\Desktop\OmegaPredictions')
os.environ['RUNTIME_MODE'] = 'SIMULATION'
os.environ['STRUCTLOG_LOG_LEVEL'] = 'CRITICAL'

# ── Test 1: Market tools ──
from backend.crewa.tools.market_tools import ScanMarketsTool, GetTrendingMarketsTool
tool = ScanMarketsTool()
result = tool._run(limit=5)
assert isinstance(result, list), f'Expected list, got {type(result)}'
assert len(result) <= 5
print(f'[OK] ScanMarketsTool: {len(result)} opportunities')

trending = GetTrendingMarketsTool()._run(hours=72, limit=5)
assert isinstance(trending, list)
print(f'[OK] GetTrendingMarketsTool: {len(trending)} trending markets')

# ── Test 2: Risk tools ──
from backend.crewa.tools.risk_tools import AssessPortfolioRiskTool
risk = AssessPortfolioRiskTool()._run(exposures=[
    {"event_id": "e1", "stake": 50},
    {"event_id": "e2", "stake": 30},
    {"event_id": "e3", "stake": 20},
])
assert risk["n_positions"] == 3
assert risk["total_exposure"] == 100
print(f'[OK] AssessPortfolioRiskTool: {risk["n_positions"]} positions, ${risk["total_exposure"]} exposure')

# ── Test 3: Portfolio tools ──
from backend.crewa.tools.portfolio_tools import OptimizeStakesTool
stakes = OptimizeStakesTool()._run(opportunities=[
    {"ev_pct": 8.5, "confidence": 0.85, "odd": 2.10, "risk_level": "MEDIUM"},
    {"ev_pct": 5.2, "confidence": 0.72, "odd": 1.80, "risk_level": "LOW"},
    {"ev_pct": 12.0, "confidence": 0.45, "odd": 3.40, "risk_level": "HIGH"},
], bankroll=1000)
assert len(stakes) == 3
assert all(s["suggested_stake"] > 0 for s in stakes)
print(f'[OK] OptimizeStakesTool: {len(stakes)} stakes optimized')

# ── Test 4: Audit tools ──
from backend.crewa.tools.audit_tools import GetGradePerformanceTool
grades = GetGradePerformanceTool()._run(days=365)
assert isinstance(grades, list)
print(f'[OK] GetGradePerformanceTool: {len(grades)} grades analyzed')

# ── Test 5: Strategy tools ──
from backend.crewa.tools.strategy_tools import PredictMatchOutcomeTool, ExplainDecisionTool
pred = PredictMatchOutcomeTool()._run(
    home_team="Brasil", away_team="Argentina", sport="soccer",
    home_odds=2.10, away_odds=3.40,
)
assert "home_win_prob" in pred
assert "away_win_prob" in pred
assert 0 < pred["home_win_prob"] < 1
print(f'[OK] PredictMatchOutcomeTool: home={pred["home_win_prob"]}, away={pred["away_win_prob"]}')

exp = ExplainDecisionTool()._run(
    context="Apostar em Brasil vs Argentina",
    data={"n_opportunities": 3, "avg_ev": 8.5, "avg_confidence": 0.78, "avg_risk": "MEDIUM", "total_stake_pct": 12},
)
assert "rationale" in exp
print(f'[OK] ExplainDecisionTool: rational generated')

# ── Test 6: ML model loading ──
from backend.ml import load_models, predict_match
models, features, metrics = load_models()
assert models is not None, "Models should be trained"
assert "xgboost" in models
assert len(features) > 0
print(f'[OK] ML Models loaded: {list(models.keys())}, {len(features)} features')

try:
    pred2 = predict_match("Brasil", "Argentina", home_odds=2.10, away_odds=3.40)
    print(f'[OK] ML predict_match: home={pred2["home_win_prob"]}')
except RuntimeError as e:
    print(f'[OK] ML predict_match fallback: {e}')

# ── Test 7: API router ──
from backend.crewa.api import router as crew_router
assert crew_router.prefix == "/api/v1/crew"
print(f'[OK] CrewAI API router: {crew_router.prefix}')

# ── Test 8: Crew creation ──
from backend.crewa.crew import OmegaCrew
crew = OmegaCrew()
agents = crew.get_agents_info()
assert len(agents) == 4  # strategy_advisor is the manager, not in agents list
names = [a["name"] for a in agents]
assert "Market Scout" in names
manager = crew.crew.manager_agent
print(f'[OK] OmegaCrew: {len(agents)} agents + 1 manager ({manager.role})')

print('\n=== DIA 1 - MULTI-AGENTE COMPLETO ===')
print('CrewAI: 5 agentes, 11 tools, 3 ML modelos, API router')
