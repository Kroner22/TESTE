"use client"

import { useMemo } from "react"
import { Card, CardContent, CardHeader, CardTitle, Badge } from "@/components/ui/card"
import { useMarketData } from "@/hooks/useMarketData"
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid,
} from "recharts"

export function PerformanceChart() {
  const { performance, primaryBookmaker } = useMarketData()

  const data = useMemo(() => {
    return performance.slice(-20).map((p) => ({
      date: new Date(p.timestamp).toLocaleDateString("pt-BR", { month: "short", day: "numeric" }),
      roi: p.roi,
    }))
  }, [performance])

  return (
    <Card>
      <CardHeader>
        <CardTitle>Retorno — Análise {primaryBookmaker}</CardTitle>
        <Badge variant="info">20 dias</Badge>
      </CardHeader>
      <CardContent>
        <div className="h-44">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data}>
              <defs>
                <linearGradient id="roiGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#22d68c" stopOpacity={0.15} />
                  <stop offset="100%" stopColor="#22d68c" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1a2a45" />
              <XAxis dataKey="date" tick={{ fill: "#8899b4", fontSize: 10 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
              <YAxis tick={{ fill: "#8899b4", fontSize: 10 }} axisLine={false} tickLine={false} width={40} />
              <Tooltip
                contentStyle={{ background: "#111b2e", border: "1px solid #1a2a45", borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: "#e2e8f0" }}
                formatter={(value: number) => [`${value.toFixed(1)}%`, "ROI"]}
              />
              <Area type="monotone" dataKey="roi" stroke="#22d68c" fill="url(#roiGrad)" strokeWidth={2} dot={false} name="ROI %" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}
