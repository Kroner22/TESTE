"use client"

import { useMarketData } from "@/hooks/useMarketData"
import { cn } from "@/lib/utils"
import { Radio, Wifi, WifiOff } from "lucide-react"

export function LiveMarketBadge() {
  const { dataMode, status } = useMarketData()

  const isLive = dataMode.mode === "LIVE"
  const isConnected = status.connected

  return (
    <div className="flex items-center gap-3">
      {/* Mode badge */}
      <div className={cn(
        "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-semibold transition-all duration-300",
        isLive
          ? "bg-brand-green/15 text-brand-green border border-brand-green/30"
          : "bg-brand-amber/15 text-brand-amber border border-brand-amber/30",
      )}>
        <div className={cn(
          "w-2 h-2 rounded-full",
          isLive ? "bg-brand-green animate-pulse" : "bg-brand-amber",
        )} />
        {isLive ? (
          <>
            <Radio className="w-3 h-3" />
            <span>AO VIVO</span>
          </>
        ) : (
          <>
            <WifiOff className="w-3 h-3" />
            <span>SIMULAÇÃO</span>
          </>
        )}
      </div>

      {/* Connection badge */}
      <div className={cn(
        "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-medium transition-all duration-300",
        isConnected
          ? "bg-brand-accent/10 text-brand-accent border border-brand-accent/20"
          : "bg-brand-red/10 text-brand-red border border-brand-red/20",
      )}>
        {isConnected ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
        <span>{isConnected ? "Conectado" : "Desconectado"}</span>
      </div>
    </div>
  )
}
