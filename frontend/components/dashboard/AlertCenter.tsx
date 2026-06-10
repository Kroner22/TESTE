"use client"

import { useMemo } from "react"
import { Card, CardContent, Badge } from "@/components/ui/card"
import { useMarketData } from "@/hooks/useMarketData"
import { cn, timeAgo } from "@/lib/utils"
import { Zap, ShieldAlert, TrendingUp, Activity, Info, AlertTriangle } from "lucide-react"

const TYPE_CONFIG = {
  opportunity: { icon: Zap, color: "text-brand-green", bg: "bg-brand-green/10", label: "Oportunidade" },
  risk: { icon: ShieldAlert, color: "text-brand-red", bg: "bg-brand-red/10", label: "Risco" },
  movement: { icon: TrendingUp, color: "text-brand-amber", bg: "bg-brand-amber/10", label: "Movimento" },
  drift: { icon: Activity, color: "text-brand-purple", bg: "bg-brand-purple/10", label: "Divergência" },
  system: { icon: Info, color: "text-brand-accent", bg: "bg-brand-accent/10", label: "Sistema" },
}

export function AlertCards() {
  const { alerts } = useMarketData()

  const displayed = useMemo(() => {
    return alerts.slice(0, 5)
  }, [alerts])

  if (displayed.length === 0) {
    return (
      <Card>
        <CardContent className="p-8 text-center">
          <div className="w-12 h-12 rounded-xl bg-brand-green/10 flex items-center justify-center mx-auto mb-3">
            <AlertTriangle className="w-6 h-6 text-brand-green" />
          </div>
          <p className="text-sm text-brand-text-bright font-medium">Nenhum alerta no momento</p>
          <p className="text-xs text-brand-text mt-1">Tudo tranquilo por aqui</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-3">
      {displayed.map((alert, i) => {
        const cfg = TYPE_CONFIG[alert.type]
        const Icon = cfg.icon
        const severityColor = alert.severity === "critical" ? "border-l-brand-red" :
          alert.severity === "warning" ? "border-l-brand-amber" : "border-l-brand-accent"

        return (
          <div
            key={alert.id}
            className={cn(
              "card-gradient card-shadow rounded-2xl border border-brand-border/60 p-4",
              "border-l-4 transition-all duration-200 hover:card-shadow-hover",
              severityColor,
              "animate-slide-in-right"
            )}
            style={{ animationDelay: `${i * 80}ms` }}
          >
            <div className="flex items-start gap-3">
              <div className={cn("w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0", cfg.bg)}>
                <Icon className={cn("w-4.5 h-4.5", cfg.color)} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className={cn("text-xs font-semibold", cfg.color)}>
                    {cfg.label}
                  </span>
                  <Badge variant={alert.severity === "critical" ? "danger" : alert.severity === "warning" ? "warning" : "info"}>
                    {alert.severity === "critical" ? "Urgente" : alert.severity === "warning" ? "Atenção" : "Info"}
                  </Badge>
                </div>
                <p className="text-sm text-brand-text-bright mt-1 leading-relaxed">{alert.message}</p>
                <p className="text-xs text-brand-text/60 mt-1.5">{timeAgo(alert.timestamp)} atrás</p>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
