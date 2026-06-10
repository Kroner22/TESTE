"use client"

import { useMarketData } from "@/hooks/useMarketData"
import { cn } from "@/lib/utils"
import { Gauge, Zap, Clock, BarChart3 } from "lucide-react"

export function LatencyAdvantageBadge() {
  const { latencyRanking, bestEarlySource } = useMarketData()

  if (latencyRanking.length === 0) {
    return (
      <div className="card-gradient card-shadow rounded-2xl border border-brand-border/60 p-5 text-center">
        <Clock className="w-8 h-8 text-brand-text/20 mx-auto mb-2" />
        <p className="text-sm text-brand-text/40">Dados de latência indisponíveis</p>
      </div>
    )
  }

  const maxMs = Math.max(...latencyRanking.map(r => r.avgMs), 1)

  return (
    <div className="card-gradient card-shadow rounded-2xl border border-brand-border/60 p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Gauge className="w-5 h-5 text-brand-accent" />
          <h3 className="text-sm font-bold text-brand-text-bright">Latência por Provider</h3>
        </div>
        {bestEarlySource && (
          <span className="text-[10px] text-brand-green bg-brand-green/10 px-2 py-0.5 rounded-full font-medium">
            <Zap className="w-3 h-3 inline mr-0.5" />
            {bestEarlySource}
          </span>
        )}
      </div>

      <div className="space-y-2">
        {latencyRanking.map((stat, i) => (
          <div key={stat.provider}>
            <div className="flex items-center justify-between text-xs mb-1">
              <div className="flex items-center gap-2">
                <span className={cn(
                  "w-5 h-5 rounded-md flex items-center justify-center text-[10px] font-bold",
                  i === 0 ? "bg-brand-green/10 text-brand-green" :
                  i === latencyRanking.length - 1 ? "bg-brand-red/10 text-brand-red" :
                  "bg-brand-border/30 text-brand-text/60"
                )}>
                  {i + 1}
                </span>
                <span className="font-medium text-brand-text-bright">{stat.provider}</span>
              </div>
              <span className="font-mono text-brand-text/60">{stat.avgMs}ms</span>
            </div>
            <div className="h-1.5 rounded-full bg-brand-border/20 overflow-hidden">
              <div
                className={cn(
                  "h-full rounded-full transition-all duration-300",
                  i === 0 ? "bg-brand-green" :
                  i <= Math.ceil(latencyRanking.length / 2) ? "bg-brand-amber" :
                  "bg-brand-red"
                )}
                style={{ width: `${(1 - stat.avgMs / maxMs) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-2 text-[10px] text-brand-text/40 pt-2 border-t border-brand-border/30">
        <div>
          <BarChart3 className="w-3 h-3 inline mr-1" />
          P95: {latencyRanking[0]?.p95Ms || 0}ms
        </div>
        <div>
          <Clock className="w-3 h-3 inline mr-1" />
          Mediana: {latencyRanking[0]?.medianMs || 0}ms
        </div>
        <div>
          <Zap className="w-3 h-3 inline mr-1" />
          Vantagem: +{(latencyRanking[latencyRanking.length - 1]?.avgMs || 0) - (latencyRanking[0]?.avgMs || 0)}ms
        </div>
      </div>
    </div>
  )
}
