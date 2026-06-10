"use client"

import { useMemo, useState } from "react"
import { Header } from "@/components/layout/Header"
import { OpportunityCardGrid } from "@/components/tables/OpportunityTable"
import { useMarketData } from "@/hooks/useMarketData"
import { cn } from "@/lib/utils"
import { ArrowUpDown } from "lucide-react"

const SPORTS = [
  { key: "all", label: "Todos" },
  { key: "soccer", label: "Futebol" },
  { key: "basketball", label: "Basquete" },
  { key: "tennis", label: "Tênis" },
  { key: "american_football", label: "NFL" },
]

const SORT_OPTIONS = [
  { key: "ev", label: "Melhor Retorno" },
  { key: "confidence", label: "Mais Confiável" },
  { key: "edge", label: "Maior Vantagem" },
  { key: "timestamp", label: "Mais Recente" },
] as const

export default function OpportunitiesPage() {
  const { opportunities, primaryBookmaker } = useMarketData()
  const [sportFilter, setSportFilter] = useState("all")
  const [sortKey, setSortKey] = useState<string>("ev")

  const filtered = useMemo(() => {
    let result = sportFilter === "all" ? opportunities : opportunities.filter(o => o.sport === sportFilter)
    result = [...result].sort((a, b) => {
      switch (sortKey) {
        case "confidence": return b.confidence - a.confidence
        case "edge": return b.edgePct - a.edgePct
        case "timestamp": return new Date(b.detectedAt).getTime() - new Date(a.detectedAt).getTime()
        default: return b.expectedValue - a.expectedValue
      }
    })
    return result
  }, [opportunities, sportFilter, sortKey])

  const betanoCount = filtered.filter(o => o.bookmaker === primaryBookmaker).length
  const aboveMarketCount = filtered.filter(o => o.betanoOdd > o.marketAvgOdd).length

  return (
    <div className="min-h-screen">
      <Header />
      <main className="max-w-7xl mx-auto px-6 py-8 space-y-6 animate-fade-in">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-brand-text-bright">Oportunidades</h1>
            <p className="text-sm text-brand-text mt-1">
              {filtered.length} oportunidade{filtered.length !== 1 ? "s" : ""} · {betanoCount} na {primaryBookmaker} · {aboveMarketCount} acima da média
            </p>
          </div>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5 bg-brand-card rounded-xl p-1 border border-brand-border/60">
            {SPORTS.map(s => (
              <button
                key={s.key}
                onClick={() => setSportFilter(s.key)}
                className={cn(
                  "px-3.5 py-1.5 text-sm rounded-lg transition-all duration-200",
                  sportFilter === s.key
                    ? "bg-brand-accent/10 text-brand-accent font-medium"
                    : "text-brand-text hover:text-brand-text-bright"
                )}
              >
                {s.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1.5 bg-brand-card rounded-xl p-1 border border-brand-border/60">
            <ArrowUpDown className="w-4 h-4 text-brand-text ml-2" />
            {SORT_OPTIONS.map(s => (
              <button
                key={s.key}
                onClick={() => setSortKey(s.key)}
                className={cn(
                  "px-3 py-1.5 text-sm rounded-lg transition-all duration-200",
                  sortKey === s.key
                    ? "bg-brand-accent/10 text-brand-accent font-medium"
                    : "text-brand-text hover:text-brand-text-bright"
                )}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>

        <OpportunityCardGrid opportunities={filtered} />
      </main>
    </div>
  )
}
