"""Agent 5: Strategy Advisor — coordinates, decides, explains."""
from crewai import Agent
from backend.crewa.config import LLM_MODEL, LLM_TEMPERATURE
from backend.crewa.tools.strategy_tools import PredictMatchOutcomeTool, ExplainDecisionTool


def create_strategy_advisor() -> Agent:
    return Agent(
        role="Strategy Advisor",
        goal="Synthesize inputs from all agents to make final betting decisions. "
             "Use ML model predictions to validate opportunities. "
             "Provide clear explanations for every recommendation.",
        backstory="Chief Investment Officer with 20 years experience in quantitative trading. "
                  "You lead the team by coordinating market intelligence, risk analysis, "
                  "portfolio optimization, and performance feedback into actionable decisions. "
                  "You communicate complex strategies in plain language.",
        tools=[PredictMatchOutcomeTool(), ExplainDecisionTool()],
        llm=LLM_MODEL,
        temperature=LLM_TEMPERATURE,
        allow_delegation=True,
        verbose=False,
        max_iter=8,
    )
