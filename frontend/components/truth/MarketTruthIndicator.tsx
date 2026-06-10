"use client"

import { useMarketData } from "@/hooks/useMarketData"
import { cn } from "@/lib/utils"
import { Shield, ShieldCheck, ShieldAlert } from "lucide-react"

export function MarketTruthIndicator() {
  const { truthConfidence, bestEarlySource, latencyRanking } = useMarketData()

  const level = truthConfidence > 0.8 ? "high" : truthConfidence > 0.6 ? "medium" : "low"

  const colorMap = {
    high: "text-brand-green border-brand-green/30 bg-brand-green/5",
    medium: "text-brand-amber border-brand-amber/30 bg-brand-amber/5",
    low: "text-brand-red border-brand-red/30 bg-brand-red/5",
  }

  const IconMap = {
    high: ShieldCheck,
    medium: Shield,
    low: ShieldAlert,
  }

  const labelMap = {
    high: "Alta Confiança",
    medium: "Confiança Moderada",
    low: "Baixa Confiança",
  }

  const Icon = IconMap[level]

  const topProvider = latencyRanking[0]

  return (
    <div className={cn("rounded-xl border p-4 space-y-3", colorMap[level])}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className="w-5 h-5" />
          <span className="text-sm font-semibold">Truth Layer</span>
        </div>
        <span className="text-xs font-mono">{(truthConfidence * 100).toFixed(0)}%</span>
      </div>

      <div className="h-1.5 rounded-full bg-brand-border/30 overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            level === "high" ? "bg-brand-green" : level === "medium" ? "bg-brand-amber" : "bg-brand-red",
          )}
          style={{ width: `${truthConfidence * 100}%` }}
        />
      </div>

      <div className="flex items-center justify-between text-[11px]">
        <span className="text-brand-text/60">{labelMap[level]}</span>
        {bestEarlySource && (
          <span className="text-brand-accent font-medium">
            Sinal mais rápido: {bestEarlySource}
          </span>
        )}
      </div>

      {topProvider && (
        <div className="text-[10px] text-brand-text/40 flex gap-3 pt-1 border-t border-current/10">
          <span>Mais rápido: {topProvider.provider} ({topProvider.avgMs}ms)</span>
          {latencyRanking.length > 1 && (
            <span>Diferença: +{(latencyRanking[latencyRanking.length - 1].avgMs - topProvider.avgMs).toFixed(0)}ms</span>
          )}
        </div>
      )}
    </div>
  )
}
