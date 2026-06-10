"use client"

import { useState, useMemo } from "react"
import { Card, CardContent, Badge } from "@/components/ui/card"
import { useMarketData } from "@/hooks/useMarketData"
import { cn, formatOdds, opportunityLevelLabel, opportunityLevelColor, opportunityLevelBg, opportunityLevelDot, isValidOpportunity } from "@/lib/utils"
import type { ValueOpportunity } from "@/lib/types"
import { ArrowUpRight, ExternalLink, ChevronDown, ChevronUp } from "lucide-react"

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const secs = Math.floor(diff / 1000)
  if (secs < 5) return "agora"
  if (secs < 60) return `${secs}s atrás`
  return `${Math.floor(secs / 60)}min atrás`
}

export function OpportunityCard({ opp }: { opp: ValueOpportunity }) {
  const [showNav, setShowNav] = useState(false)
  const { lastUpdates, oddsFlash, marketMoving } = useMarketData()

  if (!isValidOpportunity(opp)) return null

  const diffPct = ((opp.betanoOdd - opp.marketAvgOdd) / opp.marketAvgOdd * 100)
  const isAbove = diffPct > 1
  const isBelow = diffPct < -1
  const sportLabel = { soccer: "Futebol", basketball: "Basquete", tennis: "Tênis", american_football: "NFL" }[opp.sport] || opp.sport
  const isFromBetano = opp.bookmaker === "Betano"
  const flash = oddsFlash[opp.eventId]
  const lastTs = lastUpdates[opp.eventId]
  const age = lastTs ? timeAgo(lastTs) : null

  return (
    <Card>
      <CardContent className="p-0">
        {/* Level indicator bar */}
        <div className={cn("h-1.5 rounded-t-2xl transition-colors duration-500",
          opp.opportunityLevel === "high" ? "bg-brand-red" : opp.opportunityLevel === "medium" ? "bg-brand-amber" : "bg-brand-green"
        )} />

        <div className="p-5 space-y-4">
          {/* 0. Real-time badges row */}
          <div className="flex items-center gap-2">
            {flash && (
              <Badge variant={flash === "up" ? "success" : "danger"} className="animate-fade-in text-[10px]">
                {flash === "up" ? "▲" : "▼"}
              </Badge>
            )}
            {marketMoving && (
              <Badge variant="warning" className="market-pulse text-[10px]">
                Mercado em movimento
              </Badge>
            )}
            {age && (
              <span className="text-[10px] text-brand-text/40 ml-auto">
                Atualizado {age}
              </span>
            )}
          </div>

          {/* 1. Event identification */}
          <div>
            <div className="flex items-start justify-between mb-1">
              <h3 className="text-base font-bold text-brand-text-bright leading-tight">
                {opp.homeTeam} vs {opp.awayTeam}
              </h3>
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-brand-text">
              <span>{sportLabel}</span>
              <span className="w-1 h-1 rounded-full bg-brand-border" />
              <span>{opp.league}</span>
              <span className="w-1 h-1 rounded-full bg-brand-border" />
              <span>{opp.eventDate}</span>
              <span className="w-1 h-1 rounded-full bg-brand-border" />
              <span>{opp.eventTimeLocal} (UTC {opp.eventTimeUtc})</span>
            </div>
            <div className="text-xs text-brand-accent mt-1 font-medium">
              {opp.marketTypeLabel}
            </div>
          </div>

          {/* 2. Betano odds — large visual highlight with flash animation */}
          <div className={cn(
            "flex items-baseline gap-3 rounded-xl transition-all duration-500 p-2 -mx-2",
            flash === "up" && "odds-flash-up",
            flash === "down" && "odds-flash-down"
          )}>
            <div>
              <span className="text-3xl font-bold tracking-tight transition-all duration-300"
                style={{ color: flash === "up" ? "#22d68c" : flash === "down" ? "#ef4444" : undefined }}
              >
                {formatOdds(opp.betanoOdd)}
              </span>
              <span className="text-sm text-brand-accent font-medium ml-2">Betano</span>
            </div>
            {isFromBetano && (
              <Badge variant="info" className="text-[10px]">Principal</Badge>
            )}
          </div>

          {/* 3. Market comparison */}
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="bg-brand-card rounded-xl p-3">
              <div className="text-xs text-brand-text/60 mb-0.5">Média do mercado</div>
              <div className="font-semibold text-brand-text-bright">{formatOdds(opp.marketAvgOdd)}</div>
            </div>
            <div className="bg-brand-card rounded-xl p-3">
              <div className="text-xs text-brand-text/60 mb-0.5">Melhor odd externa</div>
              <div className="font-semibold text-brand-text-bright">{formatOdds(opp.bestOdd)} <span className="text-xs text-brand-text/60">({opp.bestBookmaker})</span></div>
            </div>
          </div>

          {/* 4. Difference indicator */}
          <div className={cn(
            "flex items-center gap-2 text-sm rounded-xl px-3 py-2 transition-colors duration-500",
            isAbove ? "bg-brand-green/10 text-brand-green" :
            isBelow ? "bg-brand-red/10 text-brand-red" :
            "bg-brand-border/30 text-brand-text"
          )}>
            <span className="text-base">{isAbove ? "📈" : isBelow ? "📉" : "➖"}</span>
            <span>
              {isAbove
                ? `Betano está ${Math.abs(diffPct).toFixed(1)}% acima da média do mercado`
                : isBelow
                  ? `Betano está ${Math.abs(diffPct).toFixed(1)}% abaixo da média do mercado`
                  : "Betano está alinhada com a média do mercado"}
            </span>
          </div>

          {/* 5. Opportunity level */}
          <div className={cn(
            "flex items-center gap-2 text-sm font-medium rounded-xl px-3 py-2",
            opportunityLevelBg(opp.opportunityLevel),
            opportunityLevelColor(opp.opportunityLevel),
          )}>
            <span className="text-base">{opportunityLevelDot(opp.opportunityLevel)}</span>
            <span>{opportunityLevelLabel(opp.opportunityLevel)}</span>
          </div>

          {/* 6. Navigation guide */}
          <div>
            <button
              onClick={() => setShowNav(!showNav)}
              className="flex items-center gap-1.5 text-sm text-brand-accent hover:text-brand-accent/80 transition-colors font-medium"
            >
              <ExternalLink className="w-4 h-4" />
              Como encontrar na Betano
              {showNav ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
            {showNav && (
              <div className="mt-2 bg-brand-card rounded-xl p-3 text-sm text-brand-text leading-relaxed animate-fade-in border border-brand-border/40">
                <p className="text-xs text-brand-text/60 mb-2 font-medium uppercase tracking-wide">Caminho de navegação:</p>
                <div className="flex flex-wrap items-center gap-1 text-brand-text-bright">
                  {opp.betanoNavigationPath.split(" → ").map((part, i, arr) => (
                    <span key={i} className="flex items-center gap-1">
                      <span className="px-2 py-0.5 rounded-md bg-brand-accent/5 text-brand-accent text-xs font-medium">{part}</span>
                      {i < arr.length - 1 && <span className="text-brand-text/30">→</span>}
                    </span>
                  ))}
                </div>
                <p className="text-xs text-brand-text/60 mt-3">
                  Abra a Betano, navegue até a seção acima e localize o jogo. Compare a odd exibida com o valor de {formatOdds(opp.betanoOdd)} para confirmar a oportunidade.
                </p>
              </div>
            )}
          </div>

          {/* 7. Action button */}
          <button className="w-full py-3 rounded-xl bg-brand-accent/10 text-brand-accent text-sm font-semibold hover:bg-brand-accent/20 transition-colors flex items-center justify-center gap-2">
            Ver na Betano <ArrowUpRight className="w-4 h-4" />
          </button>
        </div>
      </CardContent>
    </Card>
  )
}

export function OpportunityCardGrid({ opportunities }: { opportunities: ValueOpportunity[] }) {
  const valid = opportunities.filter(isValidOpportunity)

  if (valid.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-brand-text">Nenhuma oportunidade verificável encontrada no momento.</p>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
      {valid.map((opp, i) => (
        <div key={opp.id} className="animate-fade-in" style={{ animationDelay: `${i * 60}ms` }}>
          <OpportunityCard opp={opp} />
        </div>
      ))}
    </div>
  )
}

export { OpportunityCardGrid as OpportunityTable }
