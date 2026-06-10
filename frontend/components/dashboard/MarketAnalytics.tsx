"use client"

import { useMemo } from "react"
import { useMarketData } from "@/hooks/useMarketData"
import { Card, CardContent, Badge } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { TrendingUp, TrendingDown, Activity, BarChart3 } from "lucide-react"
import type { MarketAnalytics } from "@/lib/types"

interface MoverCardProps {
  title: string
  description: string
  icon: React.ElementType
  color: string
  badge?: { label: string; variant: "success" | "warning" | "danger" | "info" | "neutral" }
}

function MoverCard({ title, description, icon: Icon, color, badge }: MoverCardProps) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-start gap-4">
          <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0", color)}>
            <Icon className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="text-sm font-semibold text-brand-text-bright">{title}</h3>
              {badge && <Badge variant={badge.variant}>{badge.label}</Badge>}
            </div>
            <p className="text-sm text-brand-text leading-relaxed">{description}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export function MarketMover() {
  const { analytics, opportunities, status, primaryBookmaker } = useMarketData()

  const cards = useMemo(() => {
    const result: MoverCardProps[] = []

    // Best Betano opportunity
    const betanoOpps = opportunities.filter(o => o.bookmaker === primaryBookmaker)
    const bestBetano = betanoOpps.length > 0
      ? [...betanoOpps].sort((a, b) => b.expectedValue - a.expectedValue)[0]
      : opportunities.length > 0
        ? [...opportunities].sort((a, b) => b.expectedValue - a.expectedValue)[0]
        : null

    if (bestBetano) {
      const isBetano = bestBetano.bookmaker === primaryBookmaker
      result.push({
        title: "Melhor na Betano",
        description: isBetano
          ? `${bestBetano.homeTeam} vs ${bestBetano.awayTeam} — odd ${bestBetano.betanoOdd.toFixed(2)} na Betano. Chance real estimada em ${(bestBetano.fairProbability * 100).toFixed(0)}%.`
          : `${bestBetano.homeTeam} vs ${bestBetano.awayTeam} — odd de referência ${bestBetano.betanoOdd.toFixed(2)}. Melhor odd disponível: ${bestBetano.bestOdd.toFixed(2)} (${bestBetano.bestBookmaker}).`,
        icon: TrendingUp,
        color: "bg-brand-green/10 text-brand-green",
        badge: { label: gradeLabel(bestBetano.grade), variant: "success" },
      })
    }

    // Market movement overview — Betano-focused
    const volatileCount = opportunities.filter(o => (o.volatility ?? 0) > 0.3).length
    if (volatileCount > 0) {
      result.push({
        title: "Movimentação na Betano",
        description: `${volatileCount} evento${volatileCount > 1 ? "s" : ""} com alta movimentação nas odds da Betano. Fique atento às melhores janelas de entrada antes que as odds se ajustem.`,
        icon: Activity,
        color: "bg-brand-amber/10 text-brand-amber",
        badge: { label: `${volatileCount} ativo${volatileCount > 1 ? "s" : ""}`, variant: "warning" },
      })
    }

    // Betano vs market comparison
    const aboveMarket = opportunities.filter(o => o.betanoOdd > o.marketAvgOdd).length
    if (aboveMarket > 0) {
      result.push({
        title: "Betano vs Mercado",
        description: `Em ${aboveMarket} oportunidade${aboveMarket > 1 ? "s" : ""}, a Betano está oferecendo odds acima da média do mercado. Isso pode indicar valor comparativo.`,
        icon: BarChart3,
        color: "bg-brand-accent/10 text-brand-accent",
        badge: { label: `${aboveMarket} acima`, variant: "info" },
      })
    }

    // Sport with most Betano opportunities
    const bySport = Object.entries(analytics.opportunitiesBySport)
      .sort((a, b) => b[1] - a[1])
    if (bySport.length > 0) {
      const [topSport, topCount] = bySport[0]
      const sportLabel = { soccer: "Futebol", basketball: "Basquete", tennis: "Tênis", american_football: "NFL" }[topSport] || topSport
      result.push({
        title: `${sportLabel} em Destaque na Betano`,
        description: `${topCount} oportunidade${topCount > 1 ? "s" : ""} disponível${topCount > 1 ? "s" : ""} na Betano para este esporte. É o mercado com mais sinais positivos no momento.`,
        icon: TrendingDown,
        color: "bg-brand-green/10 text-brand-green",
        badge: { label: `${topCount} sinais`, variant: "success" },
      })
    }

    // Regime info
    const regimeLabel: Record<string, string> = {
      calm: "Mercado calmo, poucas oscilações — momento tranquilo para analisar as odds da Betano",
      normal: "Mercado operando normalmente — oportunidades na Betano dentro do esperado",
      volatile: "Mercado volátil — odds da Betano mudando rápido, oportunidades e riscos elevados",
      chaotic: "Mercado caótico — risco extremo, odds da Betano podem estar defasadas, recomenda-se cautela",
    }
    result.push({
      title: "Clima do Mercado",
      description: regimeLabel[status.regime] || "Mercado operando normalmente.",
      icon: TrendingDown,
      color: status.regime === "chaotic" ? "bg-brand-red/10 text-brand-red" :
             status.regime === "volatile" ? "bg-brand-amber/10 text-brand-amber" :
             "bg-brand-green/10 text-brand-green",
      badge: { label: status.regime.toUpperCase(), variant: status.regime === "chaotic" ? "danger" : status.regime === "volatile" ? "warning" : "success" },
    })

    return result
  }, [analytics, opportunities, status, primaryBookmaker])

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {cards.length === 0 ? (
        <div className="col-span-full text-center py-12">
          <p className="text-brand-text">Nenhum movimento de mercado detectado.</p>
        </div>
      ) : (
        cards.map((card, i) => (
          <div key={card.title} className="animate-fade-in" style={{ animationDelay: `${i * 80}ms` }}>
            <MoverCard {...card} />
          </div>
        ))
      )}
    </div>
  )
}

function gradeLabel(grade: string): string {
  switch (grade) {
    case "ELITE": return "Excelente"
    case "STRONG": return "Boa"
    case "SOLID": return "Sólida"
    case "SPECULATIVE": return "Especulativa"
    default: return grade
  }
}
