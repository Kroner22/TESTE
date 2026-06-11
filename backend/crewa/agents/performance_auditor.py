"""Agent 4: Performance Auditor — monitors results and adapts strategy."""
from crewai import Agent
from backend.crewa.config import LLM_MODEL, LLM_TEMPERATURE
from backend.crewa.tools.audit_tools import GetPerformanceSummaryTool, GetGradePerformanceTool


def create_performance_auditor() -> Agent:
    return Agent(
        role="Performance Auditor",
        goal="Track betting performance across all grades and strategies. "
             "Identify which approaches are working, which are failing, and recommend "
             "adjustments to improve profitability.",
        backstory="Data-driven auditor who has audited trading desks at major investment banks. "
                  "You have zero tolerance for cognitive biases and demand statistical significance. "
                  "You separate signal from noise with rigor.",
        tools=[GetPerformanceSummaryTool(), GetGradePerformanceTool()],
        llm=LLM_MODEL,
        temperature=LLM_TEMPERATURE,
        allow_delegation=False,
        verbose=False,
        max_iter=5,
    )
