"""Agent 3: Portfolio Manager — optimizes bet selection and stake sizing."""
from crewai import Agent
from backend.crewa.config import LLM_MODEL, LLM_TEMPERATURE
from backend.crewa.tools.portfolio_tools import OptimizeStakesTool, RecommendTimingTool


def create_portfolio_manager() -> Agent:
    return Agent(
        role="Portfolio Manager",
        goal="Build an optimal betting portfolio by selecting the best opportunities, "
             "sizing stakes appropriately, and timing entries for maximum risk-adjusted returns.",
        backstory="Quantitative portfolio manager who managed $500M in assets. "
                  "You apply Modern Portfolio Theory and Kelly Criterion to sports betting. "
                  "You optimize for risk-adjusted returns, not just raw EV.",
        tools=[OptimizeStakesTool(), RecommendTimingTool()],
        llm=LLM_MODEL,
        temperature=LLM_TEMPERATURE,
        allow_delegation=False,
        verbose=False,
        max_iter=5,
    )
