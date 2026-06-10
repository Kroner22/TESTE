"use client"

import { useMarketData } from "@/hooks/useMarketData"

export function PaperTradingDashboard() {
  const { paperPositions, closedPositions, bankroll } = useMarketData()

  const openPositions = paperPositions.filter(p => p.is_open)
  const closed = closedPositions
  const totalPnl = closed.reduce((sum, p) => sum + (p.pnl || 0), 0)
  const wins = closed.filter(p => (p.pnl || 0) > 0).length
  const losses = closed.filter(p => (p.pnl || 0) <= 0).length
  const hitRate = closed.length > 0 ? (wins / closed.length) * 100 : 0

  return (
    <div className="space-y-4">
      {openPositions.length === 0 && closed.length === 0 ? (
        <p className="text-sm text-brand-text/40 text-center py-8">Nenhuma posição de paper trading</p>
      ) : (
        <>
          <div className="grid grid-cols-4 gap-3">
            <div className="bg-brand-card rounded-xl p-3">
              <div className="text-[10px] text-brand-text/50">Bankroll</div>
              <div className="text-brand-text-bright text-lg font-bold">${bankroll.toFixed(2)}</div>
            </div>
            <div className="bg-brand-card rounded-xl p-3">
              <div className="text-[10px] text-brand-text/50">P&L Total</div>
              <div className={totalPnl >= 0 ? "text-brand-green text-lg font-bold" : "text-brand-red text-lg font-bold"}>
                {totalPnl >= 0 ? "+" : ""}${totalPnl.toFixed(2)}
              </div>
            </div>
            <div className="bg-brand-card rounded-xl p-3">
              <div className="text-[10px] text-brand-text/50">Hit Rate</div>
              <div className="text-brand-text-bright text-lg font-bold">{hitRate.toFixed(1)}%</div>
            </div>
            <div className="bg-brand-card rounded-xl p-3">
              <div className="text-[10px] text-brand-text/50">Abertas</div>
              <div className="text-brand-amber text-lg font-bold">{openPositions.length}</div>
            </div>
          </div>

          {wins + losses > 0 && (
            <div className="flex gap-2 text-[11px] text-brand-text/40">
              <span className="text-brand-green">{wins} vitórias</span>
              <span className="text-brand-text/30">/</span>
              <span className="text-brand-red">{losses} derrotas</span>
              <span className="text-brand-text/30">·</span>
              <span>{closed.length} fechadas</span>
            </div>
          )}

          {openPositions.length > 0 && (
            <div>
              <h5 className="text-xs text-brand-text/50 uppercase tracking-wide font-medium mb-2">Abertas</h5>
              <div className="space-y-1.5">
                {openPositions.slice(0, 5).map(p => (
                  <div key={p.position_id} className="flex items-center justify-between bg-brand-card/50 rounded-lg px-3 py-2 text-sm">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-brand-text-bright font-medium truncate">{p.event_id.slice(0, 10)}</span>
                      <span className="text-brand-text/40 text-xs">{p.outcome}</span>
                    </div>
                    <div className="flex items-center gap-3 text-xs shrink-0">
                      <span className="text-brand-text">@{p.entry_odd.toFixed(2)}</span>
                      <span className="text-brand-accent">${p.stake.toFixed(2)}</span>
                      <span className="text-brand-text/40">EV {(p.entry_ev * 100).toFixed(1)}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {closed.length > 0 && (
            <div>
              <h5 className="text-xs text-brand-text/50 uppercase tracking-wide font-medium mb-2">Fechadas</h5>
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                {closed.slice(0, 10).map(p => (
                  <div key={p.position_id} className="flex items-center justify-between bg-brand-card/50 rounded-lg px-3 py-2 text-sm">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-brand-text-bright font-medium truncate">{p.event_id.slice(0, 10)}</span>
                      {p.duration_hours != null && (
                        <span className="text-brand-text/30 text-xs">{p.duration_hours}h</span>
                      )}
                    </div>
                    <div className={p.pnl && p.pnl >= 0 ? "text-brand-green font-medium text-xs" : "text-brand-red font-medium text-xs"}>
                      {p.pnl && p.pnl >= 0 ? "+" : ""}${(p.pnl || 0).toFixed(2)}
                      {p.pnl_pct != null && ` (${p.pnl_pct >= 0 ? "+" : ""}${p.pnl_pct.toFixed(1)}%)`}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
