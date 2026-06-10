"use client"

import { useState, useEffect, useCallback, createContext, useContext, useRef, useMemo } from "react"
import type {
  ValueOpportunity, MarketOdds, SystemStatus, AlertItem,
  PerformanceSnapshot, MarketAnalytics, SortConfig, WsMessage, OpportunityLevel,
  MarketConsensus, SharpMoveEvent, InconsistencyEvent, LatencyProviderStats,
  DataMode, ValidationReport, PaperTradePosition, EfficiencyReport,
} from "@/lib/types"
import {
  generateOpportunities, generateMarketOdds, generateSystemStatus,
  generateAlerts, generatePerformanceHistory, computeAnalytics,
  PRIMARY_BOOKMAKER,
} from "@/lib/mock-data"
import { sortOpportunities, paginate } from "@/lib/utils"
import { useWebSocket } from "./useWebSocket"
import { api, isApiReachable } from "@/lib/api"

interface MarketDataContextType {
  opportunities: ValueOpportunity[]
  markets: MarketOdds[]
  status: SystemStatus
  alerts: AlertItem[]
  performance: PerformanceSnapshot[]
  analytics: MarketAnalytics
  lastUpdate: string
  sort: SortConfig
  setSort: (s: SortConfig) => void
  page: number
  setPage: (p: number) => void
  perPage: number
  totalPages: number
  filteredCount: number
  pageOpportunities: ValueOpportunity[]
  sportFilter: string
  setSportFilter: (s: string) => void
  gradeFilter: string
  setGradeFilter: (s: string) => void
  apiConnected: boolean
  refreshing: boolean
  refresh: () => void
  primaryBookmaker: string
  marketMoving: boolean
  lastUpdates: Record<string, string>
  oddsFlash: Record<string, "up" | "down" | null>
  marketConsensus: MarketConsensus[]
  sharpMoves: SharpMoveEvent[]
  inconsistencies: InconsistencyEvent[]
  latencyRanking: LatencyProviderStats[]
  truthConfidence: number
  bestEarlySource: string | null
  dataMode: DataMode
  validationReport: ValidationReport | null
  paperPositions: PaperTradePosition[]
  closedPositions: PaperTradePosition[]
  bankroll: number
  efficiencyReport: EfficiencyReport | null
}

const MarketDataContext = createContext<MarketDataContextType>(null!)

export function useMarketData() {
  return useContext(MarketDataContext)
}

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws/live"

function toOpportunity(item: any): ValueOpportunity {
  const odd = item.odd ?? item.bookmakerOdd ?? 0
  return {
    id: item.event_id || item.id || crypto.randomUUID(),
    eventId: item.event_id,
    sport: item.sport || "soccer",
    league: item.league || "",
    homeTeam: item.home_team || item.homeTeam || "",
    awayTeam: item.away_team || item.awayTeam || "",
    market: item.market || "h2h",
    outcome: item.outcome || "home",
    bookmaker: item.bookmaker,
    bookmakerOdd: odd,
    betanoOdd: item.betano_odd ?? odd,
    marketAvgOdd: item.market_avg_odd ?? odd,
    bestOdd: item.best_odd ?? odd,
    bestBookmaker: item.best_bookmaker || item.bookmaker,
    eventDate: item.event_date || new Date().toISOString().split("T")[0],
    eventTimeUtc: item.event_time_utc || "20:00",
    eventTimeLocal: item.event_time_local || "17:00",
    marketTypeLabel: item.market_type_label || "1X2 / Resultado Final",
    opportunityLevel: item.opportunity_level || "medium",
    betanoNavigationPath: item.betano_navigation_path || `${item.sport || "Esporte"} → Evento`,
    fairOdd: +(1 / (item.fair_prob / 100 || 0.01)).toFixed(2) || 0,
    fairProbability: +(item.fair_prob ?? 0) / 100,
    impliedProbability: +(item.implied_prob ?? 0) / 100,
    expectedValue: item.ev ? +(item.ev / 100).toFixed(4) : 0,
    edgePct: item.edge_score ?? 0,
    kellyStake: item.kelly_stake ?? 0,
    confidence: item.confidence ?? 0,
    riskScore: 0,
    riskLevel: item.risk_level || "MEDIUM",
    grade: item.value_grade || "SPECULATIVE",
    volatility: item.volatility ?? 0,
    trend: "stable",
    detectedAt: item.detected_at || item.captured_at || new Date().toISOString(),
    expiresAt: new Date(Date.now() + 3600000).toISOString(),
    oddsHistory: null,
  }
}

const ALERT_TYPE_MAP: Record<string, AlertItem["type"]> = {
  value_opportunity: "opportunity",
  opportunity: "opportunity",
  risk: "risk",
  movement: "movement",
  drift: "drift",
  system: "system",
}

const SEVERITY_MAP: Record<string, AlertItem["severity"]> = {
  critical: "critical",
  high: "warning",
  warning: "warning",
  info: "info",
  low: "info",
}

function toAlert(item: any): AlertItem {
  return {
    id: crypto.randomUUID(),
    type: ALERT_TYPE_MAP[item.alert_type] || "system",
    severity: SEVERITY_MAP[item.severity] || "info",
    message: item.message,
    timestamp: item.created_at || item.timestamp || new Date().toISOString(),
    evValue: item.ev_value ?? null,
    sport: null,
  }
}

export function MarketDataProvider({ children }: { children: React.ReactNode }) {
  const [opportunities, setOpportunities] = useState<ValueOpportunity[]>([])
  const [markets, setMarkets] = useState<MarketOdds[]>([])
  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const [performance, setPerformance] = useState<PerformanceSnapshot[]>([])
  const [status, setStatus] = useState<SystemStatus>({
    connected: false, lastUpdate: "", uptime: 0,
    eventsTracked: 0, modelsActive: 4, latencyMs: 0,
    regime: "normal", wsReconnects: 0,
  })
  const [lastUpdate, setLastUpdate] = useState("")
  const [marketMoving, setMarketMoving] = useState(false)
  const [lastUpdates, setLastUpdates] = useState<Record<string, string>>({})
  const [oddsFlash, setOddsFlash] = useState<Record<string, "up" | "down" | null>>({})
  const [marketConsensus, setMarketConsensus] = useState<MarketConsensus[]>([])
  const [sharpMoves, setSharpMoves] = useState<SharpMoveEvent[]>([])
  const [inconsistencies, setInconsistencies] = useState<InconsistencyEvent[]>([])
  const [latencyRanking, setLatencyRanking] = useState<LatencyProviderStats[]>([])
  const [truthConfidence, setTruthConfidence] = useState(0.85)
  const [bestEarlySource, setBestEarlySource] = useState<string | null>(null)
  const [dataMode, setDataMode] = useState<DataMode>({ mode: "SIMULATION", reason: "Carregando...", providerCount: 0, clvOpen: 0, clvClosed: 0 })
  const [validationReport, setValidationReport] = useState<ValidationReport | null>(null)
  const [paperPositions, setPaperPositions] = useState<PaperTradePosition[]>([])
  const [closedPositions, setClosedPositions] = useState<PaperTradePosition[]>([])
  const [bankroll, setBankroll] = useState(1000)
  const [efficiencyReport, setEfficiencyReport] = useState<EfficiencyReport | null>(null)
  const [sort, setSort] = useState<SortConfig>({ field: "ev", dir: "desc" })
  const [page, setPage] = useState(1)
  const [sportFilter, setSportFilter] = useState("all")
  const [gradeFilter, setGradeFilter] = useState("all")
  const [apiConnected, setApiConnected] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const perPage = 15

  const wsHandlers = useMemo(() => ({
    opportunities: (data: any) => {
      const items = Array.isArray(data) ? data : data?.data || []
      if (items.length > 0) {
        setOpportunities(prev => {
          const merged = [...items.map(toOpportunity), ...prev]
          const seen = new Set<string>()
          return merged.filter(o => {
            if (seen.has(o.id)) return false
            seen.add(o.id)
            return true
          }).slice(0, 100)
        })
      }
    },
    alerts: (data: any) => {
      const items = Array.isArray(data) ? data : data?.data || []
      if (items.length > 0) {
        setAlerts(prev => {
          const merged = [...items.map(toAlert), ...prev]
          return merged.slice(0, 50)
        })
      }
    },
    odds_update: (data: any) => {
      const changes = Array.isArray(data) ? data : data?.data || [data].filter(Boolean)
      const ts = data?.timestamp || new Date().toISOString()
      for (const change of changes) {
        if (change?.event_id) {
          setOpportunities(prev => prev.map(o => {
            if (o.eventId === change.event_id) {
              const newBetanoOdd = change.odd ?? o.betanoOdd
              const direction = newBetanoOdd > o.betanoOdd ? "up" : newBetanoOdd < o.betanoOdd ? "down" : null
              return {
                ...o,
                betanoOdd: newBetanoOdd,
                marketAvgOdd: change.market_avg_odd ?? o.marketAvgOdd,
                bestOdd: change.best_odd ?? o.bestOdd,
                volatility: change.delta_pct ? Math.min(1, o.volatility + Math.abs(change.delta_pct) / 20) : o.volatility,
              }
            }
            return o
          }))
          setLastUpdates(prev => ({ ...prev, [change.event_id]: ts }))
          if (change.odd) {
            setOddsFlash(prev => ({ ...prev, [change.event_id]: change.odd > (change.prev_odd ?? change.odd) ? "up" : "down" }))
          }
        }
      }
      setLastUpdate(ts)
    },
    market_move: (data: any) => {
      setMarketMoving(true)
      setTimeout(() => setMarketMoving(false), 3000)
      if (data?.event_id) {
        setOddsFlash(prev => ({ ...prev, [data.event_id]: data.direction === "up" ? "up" : "down" }))
        setTimeout(() => {
          setOddsFlash(prev => ({ ...prev, [data.event_id]: null }))
        }, 2000)
      }
    },
    opp_add: (data: any) => {
      const opp = data?.data || data
      if (opp?.event_id) {
        setOpportunities(prev => {
          const exists = prev.some(o => o.eventId === opp.event_id)
          if (exists) return prev
          return [toOpportunity(opp), ...prev].slice(0, 100)
        })
        setLastUpdates(prev => ({ ...prev, [opp.event_id]: data?.timestamp || new Date().toISOString() }))
      }
    },
    opp_remove: (data: any) => {
      const eid = data?.event_id || data?.data?.event_id
      if (eid) {
        setOpportunities(prev => prev.filter(o => o.eventId !== eid))
      }
    },
    market_truth_update: (data: any) => {
      const d = data?.data || data
      if (d?.event_id) {
        setMarketConsensus(prev => {
          const item: MarketConsensus = {
            eventId: d.event_id,
            market: d.market || "1X2",
            outcome: d.outcome || "",
            consensusOdd: d.consensus_odd ?? 0,
            confidence: d.confidence ?? 0.5,
            providerCount: d.provider_count ?? 0,
            outlierCount: d.outlier_count ?? 0,
            deviationPct: d.deviation_pct ?? 0,
            providerOdds: d.provider_odds ?? {},
            timestamp: d.timestamp ?? Date.now(),
          }
          const filtered = prev.filter(c => c.eventId !== item.eventId || c.market !== item.market)
          return [...filtered, item].slice(-50)
        })
        if (d.confidence) setTruthConfidence(d.confidence)
      }
    },
    sharp_move: (data: any) => {
      const d = data?.data || data
      if (d?.event_id) {
        const move: SharpMoveEvent = {
          eventId: d.event_id,
          market: d.market || "",
          moveType: d.move_type || "steam",
          magnitudePct: d.magnitude_pct ?? 0,
          velocityPctPerMin: d.velocity_pct_per_min ?? 0,
          direction: d.direction || "up",
          durationSeconds: d.duration_seconds ?? 0,
          confidence: d.confidence ?? 0,
        }
        setSharpMoves(prev => [move, ...prev].slice(0, 20))
        setMarketMoving(true)
        setTimeout(() => setMarketMoving(false), 4000)
      }
    },
    inconsistency: (data: any) => {
      const d = data?.data || data
      if (d?.event_id) {
        const inc: InconsistencyEvent = {
          eventId: d.event_id,
          market: d.market || "",
          inconsistencyType: d.inconsistency_type || "provider_divergence",
          severity: d.severity ?? 0,
          providerA: d.provider_a || "",
          providerB: d.provider_b || "",
          oddA: d.odd_a ?? 0,
          oddB: d.odd_b ?? 0,
          deviationPct: d.deviation_pct ?? 0,
        }
        setInconsistencies(prev => [inc, ...prev].slice(0, 20))
      }
    },
    latency_update: (data: any) => {
      const d = data?.data || data
      if (d?.provider_ranking) {
        setLatencyRanking(d.provider_ranking.map((r: any) => ({
          provider: r.provider,
          avgMs: r.avg_ms ?? 0,
          medianMs: r.median_ms ?? 0,
          p95Ms: r.p95_ms ?? 0,
          samples: r.samples ?? 0,
        })))
        if (d.best_early_source) setBestEarlySource(d.best_early_source)
      }
    },
    data_mode: (data: any) => {
      const d = data?.data || data
      if (d?.mode) {
        setDataMode({
          mode: d.mode,
          reason: d.reason || "",
          providerCount: d.provider_count ?? 0,
          clvOpen: d.clv_open ?? 0,
          clvClosed: d.clv_closed ?? 0,
        })
      }
    },
    validation_report: (data: any) => {
      const d = data?.data || data
      if (d?.total_entries != null) {
        setValidationReport(d)
      }
    },
    clv_record: (data: any) => {
      const d = data?.data || data
      if (d?.event_id) {
        setAlerts(prev => {
          const msg = d.clv_pct > 0
            ? `CLV+ ${d.clv_pct.toFixed(1)}% em ${d.event_id.slice(0, 12)} (${d.bookmaker})`
            : `CLV ${d.clv_pct.toFixed(1)}% em ${d.event_id.slice(0, 12)} — edge não confirmado`
          const alertItem: AlertItem = {
            id: `clv-${Date.now()}`,
            type: d.clv_pct > 0 ? "opportunity" : "risk",
            severity: d.clv_pct > 1 ? "critical" : d.clv_pct > 0 ? "info" : "warning",
            message: msg,
            timestamp: data?.timestamp || new Date().toISOString(),
            evValue: d.clv_pct,
            sport: null,
          }
          return [alertItem, ...prev].slice(0, 50)
        })
      }
    },
    paper_trading_update: (data: any) => {
      const d = data?.data || data
      if (d?.action === "open" && d?.position_id) {
        const pos: PaperTradePosition = {
          position_id: d.position_id,
          event_id: d.event_id || "",
          market: d.market || "h2h",
          outcome: d.outcome || "",
          bookmaker: d.bookmaker || "",
          entry_odd: d.entry_odd ?? 0,
          entry_ev: d.entry_ev ?? 0,
          stake: d.stake ?? 0,
          is_open: true,
          pnl: null,
          pnl_pct: null,
        }
        setPaperPositions(prev => [pos, ...prev].slice(0, 50))
        if (d.bankroll) setBankroll(d.bankroll)
      } else if (d?.action === "close" && d?.position_id) {
        const closed: PaperTradePosition = {
          position_id: d.position_id,
          event_id: d.event_id || "",
          market: "",
          outcome: "",
          bookmaker: "",
          entry_odd: d.entry_odd ?? 0,
          entry_ev: 0,
          stake: 0,
          is_open: false,
          pnl: d.pnl ?? 0,
          pnl_pct: d.pnl_pct ?? 0,
          duration_hours: d.duration_hours ?? null,
        }
        setClosedPositions(prev => [closed, ...prev].slice(0, 100))
        setPaperPositions(prev => prev.filter(p => p.position_id !== d.position_id))
        if (d.bankroll) setBankroll(d.bankroll)
      }
    },
    paper_trading_summary: (data: any) => {
      const d = data?.data || data
      if (d?.bankroll) setBankroll(d.bankroll)
    },
    efficiency_report: (data: any) => {
      const d = data?.data || data
      if (d?.verdict) {
        setEfficiencyReport(d)
      }
    },
    pong: () => {},
  }), [])

  const { connected, reconnectCount } = useWebSocket(WS_URL, wsHandlers)

  const fetchFromApi = useCallback(async () => {
    setRefreshing(true)
    try {
      const [oppsRes, alertsRes] = await Promise.all([
        api.opportunities.list({ limit: 50 }).catch(() => null),
        api.alerts.list({ limit: 20 }).catch(() => null),
      ])
      if (oppsRes) setOpportunities(oppsRes.map(toOpportunity))
      if (alertsRes) setAlerts(alertsRes.map(toAlert))
      setApiConnected(true)
    } catch {
      setApiConnected(false)
    } finally {
      setRefreshing(false)
    }
  }, [])

  const refresh = useCallback(() => {
    if (apiConnected) fetchFromApi()
  }, [apiConnected, fetchFromApi])

  useEffect(() => {
    isApiReachable().then(reachable => {
      if (reachable) {
        setApiConnected(true)
        fetchFromApi()
      }
    })
  }, [fetchFromApi])

  useEffect(() => {
    if (connected) {
      setStatus(s => ({ ...s, connected: true, wsReconnects: reconnectCount }))
    } else {
      setStatus(s => ({ ...s, connected: false }))
    }
  }, [connected, reconnectCount])

  useEffect(() => {
    const useMock = !apiConnected || opportunities.length === 0
    if (useMock) {
      setOpportunities(generateOpportunities(25))
      setMarkets(generateMarketOdds(12))
      setAlerts(prev => prev.length > 0 ? prev : generateAlerts(10))
      setPerformance(generatePerformanceHistory(60))
      const sys = generateSystemStatus()
      setStatus(prev => ({ ...prev, ...sys, connected }))
    }

    const interval = setInterval(() => {
      if (apiConnected) {
        fetchFromApi()
        return
      }
      const ts = new Date().toISOString()
      setOpportunities(prev => {
        const updated = prev.map(o => {
          const newOdd = +(o.bookmakerOdd + (Math.random() - 0.5) * 0.04).toFixed(2)
          const direction = newOdd > o.bookmakerOdd ? "up" : newOdd < o.bookmakerOdd ? "down" : null
          if (direction) {
            setOddsFlash(f => ({ ...f, [o.eventId]: direction }))
            setTimeout(() => setOddsFlash(f => ({ ...f, [o.eventId]: null })), 1500)
          }
          return {
            ...o,
            bookmakerOdd: newOdd,
            expectedValue: +(o.expectedValue + (Math.random() - 0.5) * 0.005).toFixed(4),
            edgePct: +(o.edgePct + (Math.random() - 0.5) * 0.4).toFixed(2),
            volatility: +(o.volatility + (Math.random() - 0.5) * 0.03).toFixed(3),
          }
        })
        if (Math.random() > 0.82) {
          const fresh = generateOpportunities(1)
          if (fresh.length > 0) {
            updated.unshift(fresh[0])
            if (updated.length > 50) updated.pop()
          }
        }

        // Mock truth layer data (inside setOpportunities to access latest opportunities)
        if (!apiConnected && updated.length > 0) {
          const sampleOpp = updated[Math.floor(Math.random() * updated.length)]
          setMarketConsensus(prevCs => {
            const consensus: MarketConsensus = {
              eventId: sampleOpp.eventId,
              market: "1X2",
              outcome: "home",
              consensusOdd: sampleOpp.betanoOdd,
              confidence: 0.7 + Math.random() * 0.25,
              providerCount: 4 + Math.floor(Math.random() * 2),
              outlierCount: Math.random() > 0.85 ? 1 : 0,
              deviationPct: Math.random() * 2,
              providerOdds: {
                Betano: sampleOpp.betanoOdd,
                bet365: +(sampleOpp.betanoOdd * (1 + (Math.random() - 0.5) * 0.02)).toFixed(2),
                Sportingbet: +(sampleOpp.betanoOdd * (1 + (Math.random() - 0.5) * 0.03)).toFixed(2),
                Bwin: +(sampleOpp.betanoOdd * (1 + (Math.random() - 0.5) * 0.025)).toFixed(2),
              },
              timestamp: Date.now(),
            }
            const filtered = prevCs.filter(c => c.eventId !== consensus.eventId)
            return [...filtered, consensus].slice(-20)
          })
          setTruthConfidence(0.75 + Math.random() * 0.2)

          if (Math.random() > 0.92) {
            setSharpMoves(prevM => {
              const move: SharpMoveEvent = {
                eventId: sampleOpp.eventId,
                market: "1X2",
                moveType: Math.random() > 0.5 ? "steam" : "reverse_line",
                magnitudePct: 2 + Math.random() * 4,
                velocityPctPerMin: 1 + Math.random() * 3,
                direction: Math.random() > 0.5 ? "up" : "down",
                durationSeconds: 30 + Math.random() * 90,
                confidence: 0.6 + Math.random() * 0.35,
              }
              return [move, ...prevM].slice(0, 20)
            })
          }

          if (Math.random() > 0.95) {
            setInconsistencies(prevI => {
              const inc: InconsistencyEvent = {
                eventId: sampleOpp.eventId,
                market: "1X2",
                inconsistencyType: "provider_divergence",
                severity: 0.3 + Math.random() * 0.5,
                providerA: "Betano",
                providerB: "bet365",
                oddA: sampleOpp.betanoOdd,
                oddB: +(sampleOpp.betanoOdd * (1 + (Math.random() - 0.5) * 0.05)).toFixed(2),
                deviationPct: 1 + Math.random() * 3,
              }
              return [inc, ...prevI].slice(0, 20)
            })
          }

          setLatencyRanking([
            { provider: "Betfair", avgMs: 10 + Math.random() * 5, medianMs: 9, p95Ms: 18, samples: 500 },
            { provider: "Betano", avgMs: 15 + Math.random() * 5, medianMs: 14, p95Ms: 25, samples: 500 },
            { provider: "bet365", avgMs: 25 + Math.random() * 8, medianMs: 23, p95Ms: 40, samples: 500 },
            { provider: "Bwin", avgMs: 35 + Math.random() * 10, medianMs: 33, p95Ms: 55, samples: 500 },
            { provider: "Sportingbet", avgMs: 40 + Math.random() * 10, medianMs: 38, p95Ms: 65, samples: 500 },
          ])
        setBestEarlySource("Betfair")
      }

      // Mock validation report
      if (!apiConnected && Math.random() > 0.9) {
        setValidationReport({
          total_entries: 35 + Math.floor(Math.random() * 20),
          closed_entries: 25 + Math.floor(Math.random() * 10),
          open_entries: Math.floor(Math.random() * 5),
          avg_clv_pct: -0.5 + Math.random() * 2,
          median_clv_pct: -0.3 + Math.random() * 1.5,
          positive_rate: 40 + Math.random() * 30,
          avg_ev: 0.03 + Math.random() * 0.06,
          ev_clv_correlation: 0.2 + Math.random() * 0.4,
          avg_timing_hours: 10 + Math.random() * 20,
          optimal_timing_rate: 50 + Math.random() * 30,
          avg_detection_delay_ms: 100 + Math.random() * 300,
          market_efficiency_score: 0.3 + Math.random() * 0.6,
          model_accuracy_score: 0.4 + Math.random() * 0.4,
          profit_simulation_roi: -5 + Math.random() * 15,
          total_kelly_stake: 0.25 + Math.random() * 0.5,
          sharpe_ratio: -0.5 + Math.random() * 2,
        })
        setBankroll(950 + Math.random() * 100)
      }

      // Mock paper positions
      if (!apiConnected && Math.random() > 0.92) {
        const ts = Date.now()
        setPaperPositions(prev => {
          if (prev.length >= 5) {
            const newPos = { ...prev[0], position_id: `pos_mock_${ts}` }
            return prev.map(p => {
              const pnl = (Math.random() - 0.4) * 20
              return { ...p, is_open: false, pnl: +pnl.toFixed(2), pnl_pct: +(pnl / 10).toFixed(2), duration_hours: Math.floor(Math.random() * 12) }
            })
          }
          const fresh: PaperTradePosition = {
            position_id: `pos_mock_${ts}`,
            event_id: `evt_${Math.random().toString(36).slice(2, 8)}`,
            market: "h2h",
            outcome: Math.random() > 0.5 ? "home" : "away",
            bookmaker: "Betano",
            entry_odd: +(1.5 + Math.random() * 3).toFixed(2),
            entry_ev: +(0.05 + Math.random() * 0.15).toFixed(4),
            stake: +(8 + Math.random() * 15).toFixed(2),
            is_open: true,
            pnl: null,
            pnl_pct: null,
          }
          return [...prev, fresh]
        })
      }

      // Mock efficiency report
      if (!apiConnected && Math.random() > 0.95) {
        const edgeConf = 0.2 + Math.random() * 0.6
        setEfficiencyReport({
          overfitting: {
            score: Math.random() * 0.5,
            severity: Math.random() > 0.6 ? "MODERADA" : "BAIXA",
            description: "Gap EV→CLV dentro da faixa aceitável",
          },
          timing_lag: {
            avg_delay_seconds: 30 + Math.random() * 120,
            optimal_entry_pct: 40 + Math.random() * 40,
            late_entry_pct: 10 + Math.random() * 30,
            clv_decay_per_hour: Math.random() * 0.02,
            best_entry_window: "EARLY_OPTIMAL",
          },
          persistent_edge: edgeConf > 0.4,
          edge_confidence: +edgeConf.toFixed(2),
          false_positive_rate: +(20 + Math.random() * 40).toFixed(1),
          corrected_rate: +(5 + Math.random() * 15).toFixed(1),
          market_speed_ms: +(100 + Math.random() * 500).toFixed(1),
          verdict: edgeConf > 0.5
            ? "EDGE REAL DETECTADO — CLV consistentemente positivo"
            : "SEM EDGE — Alta taxa de falso positivo",
        })
      }

        // Mock data mode
        if (!apiConnected) {
          setDataMode({
            mode: "SIMULATION",
            reason: "Modo simulação local (sem conexão com backend)",
            providerCount: 5,
            clvOpen: Math.floor(Math.random() * 5),
            clvClosed: 10 + Math.floor(Math.random() * 20),
          })
        }

        return updated
      })
      setLastUpdates(prev => {
        const next = { ...prev }
        for (const o of opportunities) {
          if (!next[o.eventId] || Math.random() > 0.7) next[o.eventId] = ts
        }
        if (Math.random() > 0.85) setMarketMoving(true)
        setTimeout(() => setMarketMoving(false), 3000)
        return next
      })
      setStatus(prev => ({
        ...prev,
        lastUpdate: ts,
        latencyMs: +(prev.latencyMs + (Math.random() - 0.5) * 10).toFixed(0),
        uptime: prev.uptime + 0.001,
        eventsTracked: prev.eventsTracked + (Math.random() > 0.7 ? 1 : 0),
      }))
      setLastUpdate(ts)
    }, apiConnected ? 15000 : 3000)

    return () => clearInterval(interval)
  }, [connected, apiConnected, fetchFromApi])

  const filtered = useMemo(() => {
    let result = opportunities
    if (sportFilter !== "all") {
      result = result.filter(o => o.sport === sportFilter)
    }
    if (gradeFilter !== "all") {
      result = result.filter(o => o.grade === gradeFilter)
    }
    return result
  }, [opportunities, sportFilter, gradeFilter])

  const filteredCount = filtered.length
  const totalPages = Math.max(1, Math.ceil(filteredCount / perPage))
  const safePage = Math.min(page, totalPages)

  const sorted = useMemo(() => sortOpportunities(filtered, sort), [filtered, sort])
  const pageOpportunities = useMemo(() => paginate(sorted, safePage, perPage), [sorted, safePage, perPage])

  const analytics = useMemo(() => computeAnalytics(opportunities), [opportunities])

  return (
    <MarketDataContext.Provider value={{
      opportunities, markets, status, alerts, performance, analytics,
      lastUpdate, sort, setSort, page: safePage, setPage, perPage,
      totalPages, filteredCount, pageOpportunities,
      sportFilter, setSportFilter, gradeFilter, setGradeFilter,
      apiConnected, refreshing, refresh,
      primaryBookmaker: PRIMARY_BOOKMAKER,
      marketMoving, lastUpdates, oddsFlash,
      marketConsensus, sharpMoves, inconsistencies, latencyRanking,
      truthConfidence, bestEarlySource,
      dataMode, validationReport,
      paperPositions, closedPositions, bankroll, efficiencyReport,
    }}>
      {children}
    </MarketDataContext.Provider>
  )
}
