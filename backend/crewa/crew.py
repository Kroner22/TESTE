"""Crew definition — orchestrates the 5 agents."""
from crewai import Crew, Process
from backend.crewa.agents.market_scout import create_market_scout
from backend.crewa.agents.risk_analyst import create_risk_analyst
from backend.crewa.agents.portfolio_manager import create_portfolio_manager
from backend.crewa.agents.performance_auditor import create_performance_auditor
from backend.crewa.agents.strategy_advisor import create_strategy_advisor


class OmegaCrew:
    """Omega Predictions Multi-Agent Crew — 5 agents collaborating on value betting."""

    def __init__(self):
        self.market_scout = create_market_scout()
        self.risk_analyst = create_risk_analyst()
        self.portfolio_manager = create_portfolio_manager()
        self.performance_auditor = create_performance_auditor()
        self.strategy_advisor = create_strategy_advisor()

        self.crew = Crew(
            agents=[
                self.market_scout,
                self.risk_analyst,
                self.portfolio_manager,
                self.performance_auditor,
            ],
            process=Process.hierarchical,
            manager_agent=self.strategy_advisor,
            verbose=False,
            max_rpm=10,
            share_crew=False,
        )

    def run_scan(self, sport: str | None = None) -> str:
        """Run a full market scan and return recommendations."""
        task_description = (
            f"Execute uma analise completa do mercado{' de ' + sport if sport else ''}.\n"
            "1. Market Scout: Escaneie mercados em busca de oportunidades value bet.\n"
            "2. Risk Analyst: Avalie o risco de cada oportunidade encontrada.\n"
            "3. Portfolio Manager: Otimize stakes e timing para as melhores oportunidades.\n"
            "4. Performance Auditor: Verifique o historico recente de performance.\n"
            "5. Strategy Advisor: Sintetize tudo e de recomendações finais.\n\n"
            "Formato da resposta:\n"
            "- Top 5 oportunidades (EV, odd, confianca, risco)\n"
            "- Stake sugerido para cada uma\n"
            "- Risco total da carteira\n"
            "- Explicacao das decisoes"
        )
        return self.crew.kickoff(inputs={"task": task_description})

    def get_agents_info(self) -> list[dict]:
        return [
            {"name": "Market Scout", "role": a.role, "goal": a.goal}
            for a in self.crew.agents
        ]
