"use client"

import { useMemo } from "react"
import { useMarketData } from "@/hooks/useMarketData"
import { cn } from "@/lib/utils"
import { Shield, Activity, Users, GitCompareArrows } from "lucide-react"

export function MarketConfidenceMeter() {
  const { marketConsensus, truthConfidence, bestEarlySource } = useMarketData()

  const stats = useMemo(() => {
    const total = marketConsensus.length
    if (total === 0) return { avgConfidence: 0, avgDeviation: 0, totalProviders: 0, totalOutliers: 0, highConfCount: 0, lowConfCount: 0 }

    let sumConf = 0
    let sumDev = 0
    let maxProviders = 0
    let totalOutliers = 0
    let highConf = 0
    let lowConf = 0

    for (const c of marketConsensus) {
      sumConf += c.confidence
      sumDev += c.deviationPct
      maxProviders = Math.max(maxProviders, c.providerCount)
      totalOutliers += c.outlierCount
      if (c.confidence > 0.8) highConf++
      if (c.confidence < 0.5) lowConf++
    }

    return {
      avgConfidence: sumConf / total,
      avgDeviation: sumDev / total,
      totalProviders: maxProviders,
      totalOutliers,
      highConfCount: highConf,
      lowConfCount: lowConf,
      total,
    }
  }, [marketConsensus])

  const level = truthConfidence > 0.8 ? "high" : truthConfidence > 0.6 ? "medium" : "low"

  const gaugeColor = level === "high" ? "text-brand-green" : level === "medium" ? "text-brand-amber" : "text-brand-red"

  return (
    <div className="card-gradient card-shadow rounded-2xl border border-brand-border/60 p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Shield className="w-5 h-5 text-brand-accent" />
          <h3 className="text-sm font-bold text-brand-text-bright">Confiança do Mercado</h3>
        </div>
        <span className={cn("text-lg font-bold font-mono", gaugeColor)}>
          {(truthConfidence * 100).toFixed(0)}%
        </span>
      </div>

      <div className="relative h-3 rounded-full bg-brand-border/20 overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-700 ease-out",
            level === "high" ? "bg-gradient-to-r from-brand-green to-brand-green/60" :
            level === "medium" ? "bg-gradient-to-r from-brand-amber to-brand-amber/60" :
            "bg-gradient-to-r from-brand-red to-brand-red/60",
          )}
          style={{ width: `${truthConfidence * 100}%` }}
        />
        <div
          className="absolute top-0 h-full w-0.5 bg-white/30"
          style={{ left: `${truthConfidence * 100}%` }}
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="bg-brand-card rounded-xl p-3">
          <div className="flex items-center gap-1.5 text-[10px] text-brand-text/50 mb-1">
            <Activity className="w-3 h-3" />
            Consenso Médio
          </div>
          <div className="text-sm font-semibold text-brand-text-bright">
            {(stats.avgConfidence * 100).toFixed(1)}%
          </div>
        </div>
        <div className="bg-brand-card rounded-xl p-3">
          <div className="flex items-center gap-1.5 text-[10px] text-brand-text/50 mb-1">
            <GitCompareArrows className="w-3 h-3" />
            Desvio Médio
          </div>
          <div className="text-sm font-semibold text-brand-text-bright">
            {stats.avgDeviation.toFixed(2)}%
          </div>
        </div>
        <div className="bg-brand-card rounded-xl p-3">
          <div className="flex items-center gap-1.5 text-[10px] text-brand-text/50 mb-1">
            <Users className="w-3 h-3" />
            Providers
          </div>
          <div className="text-sm font-semibold text-brand-text-bright">
            {stats.totalProviders}
          </div>
        </div>
        <div className="bg-brand-card rounded-xl p-3">
          <div className="flex items-center gap-1.5 text-[10px] text-brand-text/50 mb-1">
            <Shield className="w-3 h-3" />
            Alta/Baixa Conf.
          </div>
          <div className="text-sm font-semibold text-brand-text-bright">
            {stats.highConfCount}/{stats.lowConfCount}
          </div>
        </div>
      </div>

      {bestEarlySource && (
        <div className="flex items-center gap-2 text-[11px] text-brand-green bg-brand-green/5 rounded-lg px-3 py-2">
          <Activity className="w-3.5 h-3.5" />
          <span>Melhor sinal antecipado: <strong>{bestEarlySource}</strong></span>
        </div>
      )}
    </div>
  )
}
