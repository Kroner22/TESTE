"use client"

import { useMarketData } from "@/hooks/useMarketData"
import { cn } from "@/lib/utils"
import { TrendingUp, TrendingDown, Activity, Zap } from "lucide-react"

const moveColors: Record<string, string> = {
  steam: "border-brand-red/30 bg-brand-red/5",
  reverse_line: "border-brand-amber/30 bg-brand-amber/5",
}

const moveIcons: Record<string, React.ElementType> = {
  steam: Zap,
  reverse_line: Activity,
}

const moveLabels: Record<string, string> = {
  steam: "Steam Move",
  reverse_line: "Reverse Line",
}

const sportLabel: Record<string, string> = {
  soccer: "Futebol",
  basketball: "Basquete",
  tennis: "Tênis",
  american_football: "NFL",
}

export function SharpMoveAlert() {
  const { sharpMoves } = useMarketData()

  if (sharpMoves.length === 0) {
    return (
      <div className="card-gradient card-shadow rounded-2xl border border-brand-border/60 p-5 text-center">
        <Activity className="w-8 h-8 text-brand-text/20 mx-auto mb-2" />
        <p className="text-sm text-brand-text/40">Nenhum movimento brusco detectado</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {sharpMoves.slice(0, 5).map((move, i) => {
        const Icon = moveIcons[move.moveType] || Zap
        const label = moveLabels[move.moveType] || move.moveType
        const colors = moveColors[move.moveType] || "border-brand-border/30 bg-brand-card"

        return (
          <div
            key={`${move.eventId}-${i}`}
            className={cn("rounded-xl border p-3.5 animate-fade-in transition-all duration-300", colors)}
            style={{ animationDelay: `${i * 50}ms` }}
          >
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center gap-2">
                <div className={cn(
                  "w-7 h-7 rounded-lg flex items-center justify-center",
                  move.direction === "up" ? "bg-brand-green/10" : "bg-brand-red/10",
                )}>
                  {move.direction === "up"
                    ? <TrendingUp className="w-4 h-4 text-brand-green" />
                    : <TrendingDown className="w-4 h-4 text-brand-red" />
                  }
                </div>
                <div>
                  <span className="text-sm font-semibold text-brand-text-bright">{label}</span>
                  <div className="text-[10px] text-brand-text/50">
                    {move.eventId.length > 20 ? move.eventId.slice(0, 20) + "..." : move.eventId}
                  </div>
                </div>
              </div>
              <Icon className="w-4 h-4 text-brand-text/30" />
            </div>

            <div className="grid grid-cols-3 gap-2 text-xs">
              <div>
                <div className="text-brand-text/40">Magnitude</div>
                <div className={cn(
                  "font-semibold",
                  move.direction === "up" ? "text-brand-green" : "text-brand-red",
                )}>
                  {move.direction === "up" ? "+" : "-"}{move.magnitudePct.toFixed(1)}%
                </div>
              </div>
              <div>
                <div className="text-brand-text/40">Velocidade</div>
                <div className="font-semibold text-brand-text-bright">{move.velocityPctPerMin.toFixed(1)}%/min</div>
              </div>
              <div>
                <div className="text-brand-text/40">Confiança</div>
                <div className="font-semibold text-brand-text-bright">{(move.confidence * 100).toFixed(0)}%</div>
              </div>
            </div>

            <div className="mt-2 text-[10px] text-brand-text/40">
              {move.durationSeconds > 60
                ? `Duração: ${(move.durationSeconds / 60).toFixed(1)}min`
                : `Duração: ${move.durationSeconds.toFixed(0)}s`
              }
            </div>
          </div>
        )
      })}
    </div>
  )
}
