"use client"

import { useMemo } from "react"
import { useMarketData } from "@/hooks/useMarketData"
import { cn } from "@/lib/utils"
import { TrendingUp, TrendingDown, BarChart3, Clock, Activity, Target } from "lucide-react"

export function ClvValidationPanel() {
  const { validationReport, dataMode } = useMarketData()

  if (!validationReport || validationReport.closed_entries === 0) {
    return (
      <div className="card-gradient card-shadow rounded-2xl border border-brand-border/60 p-5 text-center">
        <BarChart3 className="w-8 h-8 text-brand-text/20 mx-auto mb-2" />
        <p className="text-sm text-brand-text/40">Aguardando dados de validação CLV</p>
        <p className="text-xs text-brand-text/30 mt-1">O sistema precisa capturar entradas reais para gerar o relatório</p>
      </div>
    )
  }

  const hasEdge = validationReport.avg_clv_pct > 0
  const roiPositive = validationReport.profit_simulation_roi > 0
  const highCorrelation = validationReport.ev_clv_correlation > 0.3
  const goodTiming = validationReport.optimal_timing_rate > 60

  return (
    <div className="card-gradient card-shadow rounded-2xl border border-brand-border/60 p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Target className="w-5 h-5 text-brand-accent" />
          <h3 className="text-sm font-bold text-brand-text-bright">Validação CLV</h3>
        </div>
        <span className={cn(
          "text-[10px] px-2 py-0.5 rounded-full font-medium",
          hasEdge ? "bg-brand-green/10 text-brand-green" : "bg-brand-red/10 text-brand-red",
        )}>
          {hasEdge ? "Edge Confirmado" : "Edge Não Confirmado"}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="bg-brand-card rounded-xl p-3">
          <div className="flex items-center gap-1 text-brand-text/50 mb-1">
            {hasEdge ? <TrendingUp className="w-3 h-3 text-brand-green" /> : <TrendingDown className="w-3 h-3 text-brand-red" />}
            CLV Médio
          </div>
          <span className={cn(
            "text-lg font-bold",
            hasEdge ? "text-brand-green" : "text-brand-red",
          )}>
            {validationReport.avg_clv_pct > 0 ? "+" : ""}{validationReport.avg_clv_pct.toFixed(2)}%
          </span>
        </div>
        <div className="bg-brand-card rounded-xl p-3">
          <div className="flex items-center gap-1 text-brand-text/50 mb-1">
            <Activity className="w-3 h-3" />
            Taxa Acerto
          </div>
          <span className="text-lg font-bold text-brand-text-bright">
            {validationReport.positive_rate.toFixed(1)}%
          </span>
        </div>
        <div className="bg-brand-card rounded-xl p-3">
          <div className="flex items-center gap-1 text-brand-text/50 mb-1">
            <BarChart3 className="w-3 h-3" />
            ROI Paper Trade
          </div>
          <span className={cn(
            "text-lg font-bold",
            roiPositive ? "text-brand-green" : "text-brand-red",
          )}>
            {validationReport.profit_simulation_roi > 0 ? "+" : ""}{validationReport.profit_simulation_roi.toFixed(1)}%
          </span>
        </div>
        <div className="bg-brand-card rounded-xl p-3">
          <div className="flex items-center gap-1 text-brand-text/50 mb-1">
            <Target className="w-3 h-3" />
            Sharpe Ratio
          </div>
          <span className={cn(
            "text-lg font-bold",
            validationReport.sharpe_ratio > 1 ? "text-brand-green" : validationReport.sharpe_ratio > 0 ? "text-brand-amber" : "text-brand-red",
          )}>
            {validationReport.sharpe_ratio.toFixed(2)}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 text-[10px] text-brand-text/40 pt-2 border-t border-brand-border/30">
        <div className="flex items-center gap-1">
          <Clock className="w-3 h-3" />
          Timing Ótimo: {validationReport.optimal_timing_rate.toFixed(0)}%
        </div>
        <div className="flex items-center gap-1">
          <BarChart3 className="w-3 h-3" />
          EV vs CLV: r={validationReport.ev_clv_correlation.toFixed(2)}
        </div>
        <div className="flex items-center gap-1">
          <Activity className="w-3 h-3" />
          Entradas: {validationReport.total_entries}
        </div>
      </div>

      {hasEdge && highCorrelation && goodTiming && (
        <div className="bg-brand-green/5 border border-brand-green/20 rounded-lg px-3 py-2 text-[11px] text-brand-green">
          Modelo VALIDADO — CLV positivo, correlação EV→CLV forte, timing ótimo na maioria das entradas.
          Edge real detectado contra o mercado vivo.
        </div>
      )}
      {!hasEdge && (
        <div className="bg-brand-red/5 border border-brand-red/20 rounded-lg px-3 py-2 text-[11px] text-brand-red">
          CLV negativo ou neutro — edge simulado não se confirmou no mercado real.
          Revisar fair probability, timing de captura e parâmetros de overround.
        </div>
      )}
      {hasEdge && !highCorrelation && (
        <div className="bg-brand-amber/5 border border-brand-amber/20 rounded-lg px-3 py-2 text-[11px] text-brand-amber">
          CLV positivo mas correlação fraca com EV — o edge existe mas o modelo não o está prevendo consistentemente.
        </div>
      )}
    </div>
  )
}
