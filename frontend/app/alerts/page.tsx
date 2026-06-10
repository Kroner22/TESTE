"use client"

import { Header } from "@/components/layout/Header"
import { AlertCards } from "@/components/dashboard/AlertCenter"
import { useMarketData } from "@/hooks/useMarketData"
import { Card, CardContent } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { ShieldAlert, TrendingUp, Activity, Info, Zap } from "lucide-react"

const TYPE_CONFIG: Record<string, { icon: any; label: string; color: string }> = {
  opportunity: { icon: Zap, label: "Oportunidade", color: "text-brand-green" },
  risk: { icon: ShieldAlert, label: "Risco", color: "text-brand-red" },
  movement: { icon: TrendingUp, label: "Movimento", color: "text-brand-amber" },
  drift: { icon: Activity, label: "Divergência", color: "text-brand-purple" },
  system: { icon: Info, label: "Sistema", color: "text-brand-accent" },
}

export default function AlertsPage() {
  const { alerts } = useMarketData()

  const byType = alerts.reduce<Record<string, typeof alerts>>((acc, a) => {
    if (!acc[a.type]) acc[a.type] = []
    acc[a.type].push(a)
    return acc
  }, {})

  return (
    <div className="min-h-screen">
      <Header />
      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8 animate-fade-in">
        <div>
          <h1 className="text-2xl font-bold text-brand-text-bright">Central de Alertas</h1>
          <p className="text-sm text-brand-text mt-1">{alerts.length} alerta{alerts.length !== 1 ? "s" : ""} registrado{alerts.length !== 1 ? "s" : ""}</p>
        </div>

        {/* Summary by type */}
        <div className="grid grid-cols-5 gap-4">
          {Object.entries(TYPE_CONFIG).map(([type, cfg]) => {
            const Icon = cfg.icon
            const count = byType[type]?.length || 0
            return (
              <Card key={type}>
                <CardContent className="p-5">
                  <div className="flex items-center gap-2 mb-2">
                    <Icon className={cn("w-5 h-5", cfg.color)} />
                    <span className={cn("text-sm font-semibold", cfg.color)}>{cfg.label}</span>
                  </div>
                  <div className={cn("text-2xl font-bold", count > 0 ? cfg.color : "text-brand-text/30")}>
                    {count}
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>

        {/* Full list */}
        <AlertCards />
      </main>
    </div>
  )
}
