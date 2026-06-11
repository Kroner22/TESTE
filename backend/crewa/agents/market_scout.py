"""Agent 1: Market Scout — scans markets for value opportunities."""
from crewai import Agent
from backend.crewa.config import LLM_MODEL, LLM_TEMPERATURE, FALLBACK_MODE
from backend.crewa.tools.market_tools import (
    ScanMarketsTool, GetMarketDetailTool, GetTrendingMarketsTool,
)


def create_market_scout() -> Agent:
    return Agent(
        role="Market Scout",
        goal="Identify the best value betting opportunities by scanning all available markets, "
             "analyzing odds movements, and detecting mispriced outcomes before they correct.",
        backstory="Expert odds analyst with 15 years experience in sports betting markets. "
                  "You specialize in finding value where bookmakers have mispriced outcomes. "
                  "You scan hundreds of markets daily across 15 sports.",
        tools=[ScanMarketsTool(), GetMarketDetailTool(), GetTrendingMarketsTool()],
        llm=LLM_MODEL,
        temperature=LLM_TEMPERATURE,
        allow_delegation=False,
        verbose=False,
        max_iter=5,
        respect_context_window=True,
    )
