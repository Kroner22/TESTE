"""Agent 2: Risk Analyst — assesses risk for each opportunity."""
from crewai import Agent
from backend.crewa.config import LLM_MODEL, LLM_TEMPERATURE
from backend.crewa.tools.risk_tools import AssessOpportunityRiskTool, AssessPortfolioRiskTool


def create_risk_analyst() -> Agent:
    return Agent(
        role="Risk Analyst",
        goal="Protect bankroll by rigorously assessing risk for every potential bet. "
             "Apply Kelly Criterion, portfolio constraints, and risk scoring to ensure "
             "no single bet threatens the portfolio.",
        backstory="Former hedge fund risk manager who specialized in tail-risk hedging. "
                  "You bring institutional-grade risk management to sports betting. "
                  "You never let greed override discipline.",
        tools=[AssessOpportunityRiskTool(), AssessPortfolioRiskTool()],
        llm=LLM_MODEL,
        temperature=LLM_TEMPERATURE,
        allow_delegation=False,
        verbose=False,
        max_iter=5,
    )
