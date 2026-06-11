"""FastAPI router for CrewAI multi-agent system interaction."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/v1/crew", tags=["crew"])


class ScanRequest(BaseModel):
    sport: Optional[str] = None


class CrewStatus(BaseModel):
    agents: list[dict]
    is_ready: bool


@router.post("/scan", summary="Run multi-agent market scan")
async def run_scan(req: ScanRequest):
    """Execute all 5 agents to scan markets, assess risk, optimize portfolio, and recommend bets."""
    try:
        from backend.crewa.crew import OmegaCrew
        crew = OmegaCrew()
        result = crew.run_scan(sport=req.sport)
        return {
            "status": "complete",
            "agents": crew.get_agents_info(),
            "result": result,
        }
    except ImportError as e:
        raise HTTPException(503, f"CrewAI system not available: {e}")
    except Exception as e:
        raise HTTPException(500, f"Agent run failed: {e}")


@router.get("/agents", response_model=CrewStatus)
async def list_agents():
    """List all available agents and their roles."""
    try:
        from backend.crewa.crew import OmegaCrew
        crew = OmegaCrew()
        return CrewStatus(agents=crew.get_agents_info(), is_ready=True)
    except ImportError as e:
        return CrewStatus(agents=[], is_ready=False)


@router.post("/tools/{tool_name}", summary="Execute a specific agent tool directly")
async def run_tool(tool_name: str, params: dict = {}):
    """Run a specific CrewAI tool directly by name with parameters."""
    tools_map = {
        "scan_markets": ("backend.crewa.tools.market_tools", "ScanMarketsTool"),
        "get_market_detail": ("backend.crewa.tools.market_tools", "GetMarketDetailTool"),
        "get_trending_markets": ("backend.crewa.tools.market_tools", "GetTrendingMarketsTool"),
        "assess_opportunity_risk": ("backend.crewa.tools.risk_tools", "AssessOpportunityRiskTool"),
        "assess_portfolio_risk": ("backend.crewa.tools.risk_tools", "AssessPortfolioRiskTool"),
        "optimize_stakes": ("backend.crewa.tools.portfolio_tools", "OptimizeStakesTool"),
        "recommend_timing": ("backend.crewa.tools.portfolio_tools", "RecommendTimingTool"),
        "get_performance_summary": ("backend.crewa.tools.audit_tools", "GetPerformanceSummaryTool"),
        "get_grade_performance": ("backend.crewa.tools.audit_tools", "GetGradePerformanceTool"),
        "predict_match": ("backend.crewa.tools.strategy_tools", "PredictMatchOutcomeTool"),
        "explain_decision": ("backend.crewa.tools.strategy_tools", "ExplainDecisionTool"),
    }
    if tool_name not in tools_map:
        raise HTTPException(404, f"Unknown tool: {tool_name}")
    mod_path, cls_name = tools_map[tool_name]
    import importlib
    mod = importlib.import_module(mod_path)
    tool_cls = getattr(mod, cls_name)
    tool = tool_cls()
    result = tool._run(**params)
    return {"tool": tool_name, "result": result}
