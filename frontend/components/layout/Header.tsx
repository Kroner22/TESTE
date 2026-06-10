"use client"

import { useMarketData } from "@/hooks/useMarketData"
import { cn } from "@/lib/utils"
import { BarChart3, Bell, TrendingUp, Home } from "lucide-react"
import { LiveMarketBadge } from "@/components/truth/LiveMarketBadge"
import Link from "next/link"
import { usePathname } from "next/navigation"

const navItems = [
  { href: "/", label: "Início", icon: Home },
  { href: "/opportunities", label: "Oportunidades", icon: TrendingUp },
  { href: "/analytics", label: "Mercado", icon: BarChart3 },
  { href: "/alerts", label: "Alertas", icon: Bell },
]

export function Header() {
  const { apiConnected, primaryBookmaker } = useMarketData()
  const pathname = usePathname()

  return (
    <header className="sticky top-0 z-40 border-b border-brand-border/50 bg-brand-bg/80 backdrop-blur-md">
      <div className="flex items-center justify-between px-6 h-14">
        <div className="flex items-center gap-8">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-brand-accent/15 flex items-center justify-center">
              <span className="text-sm font-bold text-brand-accent">BI</span>
            </div>
            <div>
              <span className="text-base font-bold text-brand-text-bright tracking-tight">Betano Intelligence</span>
            </div>
          </Link>

          <nav className="flex items-center gap-1">
            {navItems.map((item) => {
              const isActive = pathname === item.href
              const Icon = item.icon
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-2 px-3.5 py-2 text-sm rounded-xl transition-all duration-200",
                    isActive
                      ? "bg-brand-accent/10 text-brand-accent font-medium"
                      : "text-brand-text hover:text-brand-text-bright hover:bg-brand-card/50"
                  )}
                >
                  <Icon className="w-4 h-4" />
                  {item.label}
                </Link>
              )
            })}
          </nav>
        </div>

        <div className="flex items-center gap-4">
          <LiveMarketBadge />
          <span className="text-brand-border/30 h-5 w-px bg-current" />
          <span className="text-xs text-brand-text/50">{primaryBookmaker}</span>
        </div>
      </div>
    </header>
  )
}
