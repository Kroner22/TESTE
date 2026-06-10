"use client"

import { useMarketData } from "@/hooks/useMarketData"

export function EfficiencyReportView() {
  const { efficiencyReport } = useMarketData()

  if (!efficiencyReport) {
    return <p className="text-sm text-brand-text/40 text-center py-8">Aguardando dados de eficiência</p>
  }

  const scoreColor = efficiencyReport.edge_confidence > 0.7
    ? "text-brand-green"
    : efficiencyReport.edge_confidence > 0.4
    ? "text-brand-amber"
    : "text-brand-red"

  const verdictColor = efficiencyReport.verdict.startsWith("EDGE REAL")
    ? "text-brand-green"
    : efficiencyReport.verdict.startsWith("EDGE PARCIAL")
    ? "text-brand-amber"
    : "text-brand-red"

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-xs text-brand-text/50 uppercase tracking-wide font-medium">Eficiência do Modelo</h4>
        <span className={`text-sm font-bold ${scoreColor}`}>
          {(efficiencyReport.edge_confidence * 100).toFixed(0)}%
        </span>
      </div>

      <div className="w-full h-2 bg-brand-card rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${efficiencyReport.edge_confidence * 100}%`,
            background: efficiencyReport.edge_confidence > 0.7
              ? "linear-gradient(90deg, #22c55e, #16a34a)"
              : efficiencyReport.edge_confidence > 0.4
              ? "linear-gradient(90deg, #eab308, #ca8a04)"
              : "linear-gradient(90deg, #ef4444, #dc2626)",
          }}
        />
      </div>

      <p className={`text-sm font-medium ${verdictColor}`}>{efficiencyReport.verdict}</p>

      <div className="grid grid-cols-2 gap-2">
        <div className="bg-brand-card/50 rounded-lg p-2">
          <div className="text-[10px] text-brand-text/50">Sobreajuste</div>
          <div className="flex items-center gap-2 text-sm">
            <span className={
              efficiencyReport.overfitting?.severity === "BAIXA" ? "text-brand-green font-medium" :
              efficiencyReport.overfitting?.severity === "MODERADA" ? "text-brand-amber font-medium" :
              "text-brand-red font-medium"
            }>
              {efficiencyReport.overfitting?.severity || "—"}
            </span>
            {efficiencyReport.overfitting && (
              <span className="text-brand-text/30 text-xs">score {efficiencyReport.overfitting.score.toFixed(2)}</span>
            )}
          </div>
        </div>
        <div className="bg-brand-card/50 rounded-lg p-2">
          <div className="text-[10px] text-brand-text/50">Edge Persistente</div>
          <div className={`text-sm font-medium ${efficiencyReport.persistent_edge ? "text-brand-green" : "text-brand-red"}`}>
            {efficiencyReport.persistent_edge ? "Sim" : "Não"}
          </div>
        </div>
        <div className="bg-brand-card/50 rounded-lg p-2">
          <div className="text-[10px] text-brand-text/50">Falso Positivo</div>
          <div className="text-sm text-brand-text-bright font-medium">
            {efficiencyReport.false_positive_rate.toFixed(0)}%
          </div>
        </div>
        <div className="bg-brand-card/50 rounded-lg p-2">
          <div className="text-[10px] text-brand-text/50">Velocidade Mercado</div>
          <div className="text-sm text-brand-text-bright font-medium">
            {efficiencyReport.market_speed_ms.toFixed(0)}ms
          </div>
        </div>
      </div>

      <div className="bg-brand-card/50 rounded-lg p-2">
        <div className="text-[10px] text-brand-text/50 mb-1">Timing de Entrada</div>
        <div className="flex items-center gap-3 text-xs">
          <span className="text-brand-green">Ótimo {efficiencyReport.timing_lag.optimal_entry_pct.toFixed(0)}%</span>
          <span className="text-brand-text/30">|</span>
          <span className="text-brand-red">Tardio {efficiencyReport.timing_lag.late_entry_pct.toFixed(0)}%</span>
          <span className="text-brand-text/30">|</span>
          <span className="text-brand-text/50">Delay {efficiencyReport.timing_lag.avg_delay_seconds.toFixed(0)}s</span>
        </div>
        {efficiencyReport.timing_lag.best_entry_window && (
          <div className="text-[10px] text-brand-text/40 mt-1">
            Melhor janela: {efficiencyReport.timing_lag.best_entry_window === "EARLY_OPTIMAL" ? "Início (Early) ou Ótimo" : "Tardio (Late)"}
          </div>
        )}
      </div>

      {efficiencyReport.overfitting?.description && (
        <div className="text-[10px] text-brand-text/40 leading-relaxed">
          {efficiencyReport.overfitting.description}
        </div>
      )}
    </div>
  )
}
