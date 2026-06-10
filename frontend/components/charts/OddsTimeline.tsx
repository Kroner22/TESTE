"use client"

import { useMemo } from "react"
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip,
  ReferenceLine,
} from "recharts"
import { useMarketData } from "@/hooks/useMarketData"
import { Card, CardContent, CardHeader, CardTitle, Badge } from "@/components/ui/card"
import { cn, formatTime } from "@/lib/utils"
import type { OddsHistory } from "@/lib/types"
import { TrendingUp, TrendingDown } from "lucide-react"

export function OddsMiniChart({ history }: { history: OddsHistory }) {
  const data = history.movement.map((p) => ({
    t: formatTime(p.timestamp),
    odd: p.odd,
  }))

  const isUp = history.currentOdd > history.openingOdd
  const color = isUp ? "#22d68c" : "#f43f5e"

  return (
    <div className="flex items-center gap-4">
      <div className="flex items-center gap-2 flex-shrink-0">
        <div className={cn("flex items-center gap-1 text-sm font-medium", isUp ? "text-brand-green" : "text-brand-red")}>
          {isUp ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
          <span>{history.openingOdd.toFixed(2)} → {history.currentOdd.toFixed(2)}</span>
        </div>
        <span className={cn("text-xs px-2 py-0.5 rounded-full", isUp ? "bg-brand-green/10 text-brand-green" : "bg-brand-red/10 text-brand-red")}>
          Betano {isUp ? "subiu" : "caiu"} {(history.currentOdd - history.openingOdd) >= 0 ? "+" : ""}{(history.currentOdd - history.openingOdd).toFixed(2)}
        </span>
      </div>
      <div className="flex-1 h-14">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <Line
              type="monotone"
              dataKey="odd"
              stroke={color}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <ReferenceLine y={history.openingOdd} stroke="#8899b4" strokeDasharray="3 3" strokeOpacity={0.3} />
            <Tooltip
              contentStyle={{
                background: "#111b2e", border: "1px solid #1a2a45",
                borderRadius: 8, fontSize: 12,
              }}
              labelStyle={{ color: "#e2e8f0" }}
              formatter={(value: number) => [value.toFixed(2), "Odd Betano"]}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

export function OddsTimelineChart() {
  const { opportunities, primaryBookmaker } = useMarketData()

  const histories = useMemo(() => {
    return opportunities
      .filter(o => o.oddsHistory)
      .slice(0, 4)
      .map(o => ({
        label: `${o.homeTeam} vs ${o.awayTeam}`,
        sport: o.sport,
        grade: o.grade,
        isFromBetano: o.bookmaker === primaryBookmaker,
        ...o.oddsHistory!,
      }))
  }, [opportunities, primaryBookmaker])

  return (
    <Card>
      <CardHeader>
        <CardTitle>Movimento das Odds — {primaryBookmaker}</CardTitle>
        <Badge variant="info">{histories.length} eventos</Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        {histories.length === 0 ? (
          <div className="text-center py-8 text-brand-text">Nenhum movimento detectado</div>
        ) : (
          histories.map((h) => (
            <div key={h.eventId} className="space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-sm text-brand-text-bright font-medium">
                  {h.label}
                  {h.isFromBetano && <span className="text-xs text-brand-accent ml-2">(Betano)</span>}
                </span>
                <span className="text-xs text-brand-text/60 capitalize">{h.sport}</span>
              </div>
              <OddsMiniChart history={h} />
            </div>
          ))
        )}
      </CardContent>
    </Card>
  )
}
