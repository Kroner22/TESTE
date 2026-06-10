"use client"

import { useMemo } from "react"
import { Header } from "@/components/layout/Header"
import { OddsTimelineChart } from "@/components/charts/OddsTimeline"
import { ProbabilityChart } from "@/components/charts/ProbabilityChart"
import { EdgeHeatmap } from "@/components/charts/EdgeHeatmap"
import { PerformanceChart } from "@/components/charts/PerformanceChart"
import { MarketMover } from "@/components/dashboard/MarketAnalytics"
import { useMarketData } from "@/hooks/useMarketData"
import { Card, CardContent, CardHeader, CardTitle, Badge } from "@/components/ui/card"
import { cn } from "@/lib/utils"

export default function AnalyticsPage() {
  const { analytics, performance, opportunities, primaryBookmaker } = useMarketData()

  const latestPerf = performance.length > 0 ? performance[performance.length - 1] : null

  const betanoCount = opportunities.filter(o => o.bookmaker === primaryBookmaker).length
  const betanoAbove = opportunities.filter(o => o.betanoOdd > o.marketAvgOdd).length
  const betanoBelow = opportunities.filter(o => o.betanoOdd < o.marketAvgOdd).length

  return (
    <div className="min-h-screen">
      <Header />
      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8 animate-fade-in">
        <div>
          <h1 className="text-2xl font-bold text-brand-text-bright">Análise de Mercado</h1>
          <p className="text-sm text-brand-text mt-1">Movimentos, odds e comparativo com {primaryBookmaker}</p>
        </div>

        {/* Market movers */}
        <MarketMover />

        {/* Key stats — Betano focused */}
        <div className="grid grid-cols-4 gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Métricas do Modelo</CardTitle>
              <Badge variant="info">atual</Badge>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {[
                  { label: "Precisão (Brier)", value: latestPerf?.brier.toFixed(4) ?? "—", color: latestPerf && latestPerf.brier < 0.15 ? "text-brand-green" : "text-brand-amber" },
                  { label: "Acurácia", value: latestPerf ? `${(latestPerf.accuracy * 100).toFixed(1)}%` : "—", color: "text-brand-green" },
                  { label: "ROI (30d)", value: latestPerf ? `${latestPerf.roi.toFixed(1)}%` : "—", color: latestPerf && latestPerf.roi > 0 ? "text-brand-green" : "text-brand-red" },
                  { label: "Total de Sinais", value: latestPerf?.nBets.toString() ?? "—" },
                ].map(s => (
                  <div key={s.label} className="flex items-center justify-between">
                    <span className="text-xs text-brand-text">{s.label}</span>
                    <span className={cn("text-sm font-medium tabular-nums", s.color || "text-brand-text-bright")}>{s.value}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{primaryBookmaker}</CardTitle>
              <Badge variant="info">oportunidades</Badge>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {[
                  { label: "Sinais Detectados", value: betanoCount.toString(), color: "text-brand-accent" },
                  { label: "Acima do Mercado", value: betanoAbove.toString(), color: "text-brand-green" },
                  { label: "Abaixo do Mercado", value: betanoBelow.toString(), color: "text-brand-red" },
                  { label: "Total de Oportunidades", value: analytics.totalOpportunities.toString(), color: "text-brand-text-bright" },
                ].map(s => (
                  <div key={s.label} className="flex items-center justify-between">
                    <span className="text-xs text-brand-text">{s.label}</span>
                    <span className={cn("text-sm font-medium tabular-nums", s.color || "text-brand-text-bright")}>{s.value}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Distribuição</CardTitle>
              <Badge variant="warning">qualidade</Badge>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {[
                  { label: "Excelentes (ELITE)", value: analytics.eliteCount.toString(), color: "text-brand-green" },
                  { label: "Boas (STRONG)", value: analytics.strongCount.toString(), color: "text-brand-accent" },
                  { label: "Eventos Voláteis", value: analytics.volatileEvents.toString(), color: "text-brand-amber" },
                  { label: "Alertas Ativos", value: analytics.alertsActive.toString(), color: analytics.alertsActive > 5 ? "text-brand-red" : "text-brand-amber" },
                ].map(s => (
                  <div key={s.label} className="flex items-center justify-between">
                    <span className="text-xs text-brand-text">{s.label}</span>
                    <span className={cn("text-sm font-medium tabular-nums", s.color || "text-brand-text-bright")}>{s.value}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Por Esporte</CardTitle>
              <Badge variant="info">na {primaryBookmaker}</Badge>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {Object.entries(analytics.opportunitiesBySport).length === 0 ? (
                  <div className="text-xs text-brand-text">Sem dados</div>
                ) : (
                  Object.entries(analytics.opportunitiesBySport)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 4)
                    .map(([sport, count]) => {
                      const label = { soccer: "Futebol", basketball: "Basquete", tennis: "Tênis", american_football: "NFL" }[sport] || sport
                      return (
                        <div key={sport} className="flex items-center justify-between">
                          <span className="text-xs text-brand-text">{label}</span>
                          <span className="text-sm font-medium text-brand-accent tabular-nums">{count}</span>
                        </div>
                      )
                    })
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Charts row */}
        <div className="grid grid-cols-12 gap-4">
          <div className="col-span-8">
            <PerformanceChart />
          </div>
          <div className="col-span-4">
            <EdgeHeatmap />
          </div>
        </div>

        <div className="grid grid-cols-12 gap-4">
          <div className="col-span-7">
            <OddsTimelineChart />
          </div>
          <div className="col-span-5">
            <ProbabilityChart />
          </div>
        </div>
      </main>
    </div>
  )
}
