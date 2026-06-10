"use client"

import { useMemo } from "react"
import { Card, CardContent, CardHeader, CardTitle, Badge } from "@/components/ui/card"
import { useMarketData } from "@/hooks/useMarketData"
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
} from "recharts"

export function ProbabilityChart() {
  const { opportunities, primaryBookmaker } = useMarketData()

  const data = useMemo(() => {
    const grouped: Record<string, { sport: string; count: number; betanoOdds: number[] }> = {}
    for (const opp of opportunities) {
      const key = opp.sport
      if (!grouped[key]) grouped[key] = { sport: key, count: 0, betanoOdds: [] }
      grouped[key].count++
      grouped[key].betanoOdds.push(opp.betanoOdd)
    }
    return Object.entries(grouped).map(([sport, g]) => ({
      sport: sport === "soccer" ? "Futebol" : sport === "basketball" ? "Basquete" : sport === "tennis" ? "Tênis" : "NFL",
      oddMediaBetano: +((g.betanoOdds.reduce((a, b) => a + b, 0) / g.betanoOdds.length)).toFixed(2),
      count: g.count,
    }))
  }, [opportunities])

  return (
    <Card>
      <CardHeader>
        <CardTitle>Odds Médias — {primaryBookmaker}</CardTitle>
        <Badge variant="info">{data.length} esportes</Badge>
      </CardHeader>
      <CardContent>
        <div className="h-52">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#1a2a45" />
              <XAxis type="number" tick={{ fill: "#8899b4", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis dataKey="sport" type="category" tick={{ fill: "#8899b4", fontSize: 11 }} axisLine={false} tickLine={false} width={70} />
              <Tooltip
                contentStyle={{ background: "#111b2e", border: "1px solid #1a2a45", borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: "#e2e8f0" }}
                formatter={(value: number) => [value.toFixed(2), "Odd Betano"]}
              />
              <Bar dataKey="oddMediaBetano" fill="#3b82f6" radius={[0, 6, 6, 0]} name="Odd Betano" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}
