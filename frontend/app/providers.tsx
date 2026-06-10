"use client"

import { MarketDataProvider } from "@/hooks/useMarketData"

export function Providers({ children }: { children: React.ReactNode }) {
  return <MarketDataProvider>{children}</MarketDataProvider>
}
