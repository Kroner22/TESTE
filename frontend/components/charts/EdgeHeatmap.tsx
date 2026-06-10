"use client"

import { useMemo } from "react"
import { Card, CardContent, CardHeader, CardTitle, Badge } from "@/components/ui/card"
import { useMarketData } from "@/hooks/useMarketData"
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
} from "recharts"

export function EdgeHeatmap() {
  const { opportunities, primaryBookmaker } = useMarketData()

  const data = useMemo(() => {
    const grouped: Record<string, { sport: string; count: number; diffs: number[] }> = {}
    for (const opp of opportunities) {
      const key = opp.sport
      if (!grouped[key]) grouped[key] = { sport: key, count: 0, diffs: [] }
      grouped[key].count++
      grouped[key].diffs.push(opp.betanoOdd - opp.marketAvgOdd)
    }
    return Object.entries(grouped).map(([sport, g]) => ({
      sport: sport === "soccer" ? "Futebol" : sport === "basketball" ? "Basquete" : sport === "tennis" ? "Tênis" : "NFL",
      oportunidades: g.count,
      difMedia: +((g.diffs.reduce((a, b) => a + b, 0) / g.diffs.length)).toFixed(2),
    }))
  }, [opportunities])

  return (
    <Card>
      <CardHeader>
        <CardTitle>{primaryBookmaker} vs Mercado</CardTitle>
        <Badge variant="info">{data.length} esportes</Badge>
      </CardHeader>
      <CardContent>
        <div className="h-44">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#1a2a45" />
              <XAxis type="number" tick={{ fill: "#8899b4", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis dataKey="sport" type="category" tick={{ fill: "#8899b4", fontSize: 10 }} axisLine={false} tickLine={false} width={75} />
              <Tooltip
                contentStyle={{ background: "#111b2e", border: "1px solid #1a2a45", borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: "#e2e8f0" }}
                formatter={(value: number) => [value > 0 ? `+${value.toFixed(2)}` : value.toFixed(2), "Diferença Betano"]}
              />
              <Bar dataKey="difMedia" fill="#22d68c" radius={[0, 6, 6, 0]} name="Diferença vs mercado" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}
