"use client"

import { useMemo } from "react"
import { Header } from "@/components/layout/Header"
import { OpportunityCardGrid } from "@/components/tables/OpportunityTable"
import { MarketMover } from "@/components/dashboard/MarketAnalytics"
import { AlertCards } from "@/components/dashboard/AlertCenter"
import { MarketTruthIndicator } from "@/components/truth/MarketTruthIndicator"
import { SharpMoveAlert } from "@/components/truth/SharpMoveAlert"
import { LatencyAdvantageBadge } from "@/components/truth/LatencyAdvantageBadge"
import { MarketConfidenceMeter } from "@/components/truth/MarketConfidenceMeter"
import { ClvValidationPanel } from "@/components/truth/ClvValidationPanel"
import { PaperTradingDashboard } from "@/components/truth/PaperTradingDashboard"
import { EfficiencyReportView } from "@/components/truth/EfficiencyReportView"
import { useMarketData } from "@/hooks/useMarketData"
import { TrendingUp, BarChart3, Bell, ArrowUpRight, Star, Zap, Shield, Target } from "lucide-react"
import Link from "next/link"
import { cn } from "@/lib/utils"

function StatCard({ icon: Icon, label, value, sub, color }: {
  icon: React.ElementType; label: string; value: string; sub?: string; color?: string
}) {
  return (
    <div className="card-gradient card-shadow rounded-2xl border border-brand-border/60 p-5 transition-all duration-200 hover:card-shadow-hover hover:border-brand-border">
      <div className="flex items-start justify-between mb-3">
        <span className="text-xs text-brand-text font-medium">{label}</span>
        <Icon className={cn("w-5 h-5", color || "text-brand-accent")} />
      </div>
      <div className={cn("text-2xl font-bold tracking-tight", color || "text-brand-text-bright")}>
        {value}
      </div>
      {sub && <div className="text-xs text-brand-text mt-1">{sub}</div>}
    </div>
  )
}

function SectionHeader({ icon: Icon, title, href }: { icon: React.ElementType; title: string; href?: string }) {
  return (
    <div className="flex items-center justify-between mb-4">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl bg-brand-accent/10 flex items-center justify-center">
          <Icon className="w-5 h-5 text-brand-accent" />
        </div>
        <h2 className="text-lg font-bold text-brand-text-bright">{title}</h2>
      </div>
      {href && (
        <Link
          href={href}
          className="flex items-center gap-1 text-sm text-brand-accent hover:text-brand-accent/80 transition-colors"
        >
          Ver tudo <ArrowUpRight className="w-4 h-4" />
        </Link>
      )}
    </div>
  )
}

function ValidationPaperTrading() {
  const { validationReport } = useMarketData()
  if (!validationReport || validationReport.closed_entries === 0) {
    return <p className="text-sm text-brand-text/40 text-center py-8">Sem dados de paper trading</p>
  }
  const roi = validationReport.profit_simulation_roi
  const sharpe = validationReport.sharpe_ratio
  const hitRate = validationReport.positive_rate
  const entries = validationReport.closed_entries
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-brand-card rounded-xl p-3">
          <div className="text-[10px] text-brand-text/50">Retorno Total</div>
          <div className={roi > 0 ? "text-brand-green text-xl font-bold" : "text-brand-red text-xl font-bold"}>
            {roi > 0 ? "+" : ""}{roi.toFixed(1)}%
          </div>
        </div>
        <div className="bg-brand-card rounded-xl p-3">
          <div className="text-[10px] text-brand-text/50">Sharpe (anual)</div>
          <div className={sharpe > 1 ? "text-brand-green text-xl font-bold" : sharpe > 0 ? "text-brand-amber text-xl font-bold" : "text-brand-red text-xl font-bold"}>
            {sharpe.toFixed(2)}
          </div>
        </div>
        <div className="bg-brand-card rounded-xl p-3">
          <div className="text-[10px] text-brand-text/50">Hit Rate</div>
          <div className="text-brand-text-bright text-xl font-bold">{hitRate.toFixed(1)}%</div>
        </div>
        <div className="bg-brand-card rounded-xl p-3">
          <div className="text-[10px] text-brand-text/50">Entradas</div>
          <div className="text-brand-text-bright text-xl font-bold">{entries}</div>
        </div>
      </div>
      <div className="text-[11px] text-brand-text/40 flex items-center gap-2">
        <span>Kelly: {(validationReport.total_kelly_stake * 100).toFixed(0)}%</span>
        <span className="w-1 h-1 rounded-full bg-brand-border/30" />
        <span>Delay: {validationReport.avg_detection_delay_ms.toFixed(0)}ms</span>
        <span className="w-1 h-1 rounded-full bg-brand-border/30" />
        <span>CLV: {validationReport.avg_clv_pct > 0 ? "+" : ""}{validationReport.avg_clv_pct.toFixed(2)}%</span>
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const { analytics, opportunities, primaryBookmaker } = useMarketData()

  const topOpportunities = useMemo(() => {
    return [...opportunities].sort((a, b) => b.expectedValue - a.expectedValue).slice(0, 6)
  }, [opportunities])

  const betanoCount = opportunities.filter(o => o.bookmaker === primaryBookmaker).length
  const betanoAboveMarket = opportunities.filter(o =>
    o.bookmaker === primaryBookmaker && o.betanoOdd > o.marketAvgOdd
  ).length

  return (
    <div className="min-h-screen">
      <Header />
      <main className="max-w-7xl mx-auto px-6 py-8 space-y-10 animate-fade-in">
        {/* Stats row */}
        <div className="grid grid-cols-4 gap-4">
          <StatCard
            icon={Zap}
            label={`Oportunidades (${primaryBookmaker})`}
            value={betanoCount.toString()}
            sub={`${analytics.eliteCount} excelentes · ${analytics.strongCount} boas`}
            color="text-brand-green"
          />
          <StatCard
            icon={TrendingUp}
            label="Betano acima do mercado"
            value={betanoAboveMarket.toString()}
            sub={`De ${analytics.totalOpportunities} oportunidades`}
            color="text-brand-accent"
          />
          <StatCard
            icon={BarChart3}
            label="Confiança Média"
            value={`${(analytics.avgConfidence * 100).toFixed(0)}%`}
            sub={`${analytics.highConfCount} com alta confiança`}
            color="text-brand-green"
          />
          <StatCard
            icon={Bell}
            label="Alertas Ativos"
            value={analytics.alertsActive.toString()}
            sub="Monitoramento contínuo"
            color={analytics.alertsActive > 5 ? "text-brand-amber" : "text-brand-text"}
          />
        </div>

        {/* Section 1: Oportunidades de Hoje */}
        <section>
          <SectionHeader icon={Star} title={`🔥 Oportunidades — ${primaryBookmaker}`} href="/opportunities" />
          <OpportunityCardGrid opportunities={topOpportunities} />
        </section>

        {/* Section 2: Movimento do Mercado */}
        <section>
          <SectionHeader icon={BarChart3} title="📊 Movimento do Mercado" href="/analytics" />
          <MarketMover />
        </section>

        {/* Section 3: Market Truth Layer */}
        <section>
          <SectionHeader icon={Shield} title="🛡️ Truth Layer — Consenso de Mercado" />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <MarketTruthIndicator />
            <MarketConfidenceMeter />
            <div className="lg:col-span-1">
              <SharpMoveAlert />
            </div>
            <div className="lg:col-span-1">
              <LatencyAdvantageBadge />
            </div>
          </div>
        </section>

        {/* Section 4: CLV Validation */}
        <section>
          <SectionHeader icon={Target} title="✅ Validação CLV — Mercado Real" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <ClvValidationPanel />
            <div className="card-gradient card-shadow rounded-2xl border border-brand-border/60 p-5">
              <h4 className="text-xs text-brand-text/50 uppercase tracking-wide font-medium mb-3">Simulação de Profit</h4>
              <ValidationPaperTrading />
            </div>
          </div>
        </section>

        {/* Section 5: Paper Trading */}
        <section>
          <SectionHeader icon={TrendingUp} title="📋 Paper Trading — Posições" />
          <div className="card-gradient card-shadow rounded-2xl border border-brand-border/60 p-5">
            <PaperTradingDashboard />
          </div>
        </section>

        {/* Section 6: Market Efficiency */}
        <section>
          <SectionHeader icon={BarChart3} title="🔬 Análise de Eficiência — Mercado" />
          <div className="card-gradient card-shadow rounded-2xl border border-brand-border/60 p-5">
            <EfficiencyReportView />
          </div>
        </section>

        {/* Section 7: Alertas Importantes */}
        <section>
          <SectionHeader icon={Bell} title="⚠️ Alertas Importantes" href="/alerts" />
          <AlertCards />
        </section>
      </main>
    </div>
  )
}
