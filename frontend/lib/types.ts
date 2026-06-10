export type ValueGrade = "ELITE" | "STRONG" | "SOLID" | "SPECULATIVE" | "NOISE"
export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "EXTREME"
export type Sport = "soccer" | "basketball" | "tennis" | "american_football"
export type MarketType = "h2h" | "spread" | "totals"
export type SortField = "ev" | "edge" | "volatility" | "confidence" | "kelly" | "odd" | "timestamp"
export type SortDir = "asc" | "desc"
export type TrendDir = "up" | "down" | "stable"
export type Regime = "calm" | "normal" | "volatile" | "chaotic"

export interface OddsPoint {
  timestamp: string
  odd: number
  bookmaker: string
}

export interface OddsHistory {
  eventId: string
  outcome: string
  openingOdd: number
  currentOdd: number
  movement: OddsPoint[]
  volatility: number
  trend: TrendDir
  tickCount: number
  maxMove: number
}

export type OpportunityLevel = "low" | "medium" | "high"

export interface ValueOpportunity {
  id: string
  eventId: string
  sport: Sport
  league: string
  homeTeam: string
  awayTeam: string
  market: MarketType
  outcome: string
  bookmaker: string
  bookmakerOdd: number
  betanoOdd: number
  marketAvgOdd: number
  bestOdd: number
  bestBookmaker: string

  eventDate: string
  eventTimeUtc: string
  eventTimeLocal: string
  marketTypeLabel: string
  opportunityLevel: OpportunityLevel
  betanoNavigationPath: string

  fairOdd: number
  fairProbability: number
  impliedProbability: number
  expectedValue: number
  edgePct: number
  kellyStake: number
  confidence: number
  riskScore: number
  riskLevel: RiskLevel
  grade: ValueGrade
  volatility: number
  trend: TrendDir
  detectedAt: string
  expiresAt: string
  oddsHistory: OddsHistory | null
}

export interface MarketOdds {
  eventId: string
  sport: Sport
  homeTeam: string
  awayTeam: string
  market: MarketType
  homeOdd: number
  awayOdd: number
  drawOdd: number | null
  bookmaker: string
  capturedAt: string
}

export interface AlertItem {
  id: string
  type: "opportunity" | "risk" | "system" | "movement" | "drift"
  severity: "info" | "warning" | "critical"
  message: string
  timestamp: string
  evValue: number | null
  sport: Sport | null
}

export interface PerformanceSnapshot {
  timestamp: string
  brier: number
  accuracy: number
  aucRoc: number
  roi: number
  nBets: number
}

export interface SortConfig {
  field: SortField
  dir: SortDir
}

export interface MarketAnalytics {
  totalOpportunities: number
  avgEV: number
  avgEdge: number
  bestEV: number
  bestEdge: number
  highConfCount: number
  eliteCount: number
  strongCount: number
  avgConfidence: number
  volatileEvents: number
  alertsActive: number
  bestBookmaker: string
  opportunitiesBySport: Record<string, number>
}

export interface SystemStatus {
  connected: boolean
  lastUpdate: string
  uptime: number
  eventsTracked: number
  modelsActive: number
  latencyMs: number
  regime: Regime
  wsReconnects: number
}

export interface PaperTradePosition {
  position_id: string
  event_id: string
  market: string
  outcome: string
  bookmaker: string
  entry_odd: number
  entry_ev: number
  stake: number
  is_open: boolean
  pnl: number | null
  pnl_pct: number | null
  duration_hours?: number | null
}

export interface EfficiencyReport {
  overfitting: { score: number; severity: string; description: string } | null
  timing_lag: {
    avg_delay_seconds: number
    optimal_entry_pct: number
    late_entry_pct: number
    clv_decay_per_hour: number
    best_entry_window: string
  }
  persistent_edge: boolean
  edge_confidence: number
  false_positive_rate: number
  corrected_rate: number
  market_speed_ms: number
  verdict: string
}

export interface WsMessage {
  type: "opportunities" | "alerts" | "odds_update" | "market_snapshot" | "market_truth_update" | "sharp_move" | "inconsistency" | "latency_update" | "data_mode" | "clv_record" | "clv_report" | "validation_report" | "paper_trading_update" | "paper_trading_summary" | "efficiency_report" | "pong"
  data: any
  timestamp: string
}

export interface DataMode {
  mode: "LIVE" | "SIMULATION"
  reason: string
  providerCount: number
  clvOpen: number
  clvClosed: number
}

export interface MarketConsensus {
  eventId: string
  market: string
  outcome: string
  consensusOdd: number
  confidence: number
  providerCount: number
  outlierCount: number
  deviationPct: number
  providerOdds: Record<string, number>
  timestamp: number
}

export interface SharpMoveEvent {
  eventId: string
  market: string
  moveType: string
  magnitudePct: number
  velocityPctPerMin: number
  direction: string
  durationSeconds: number
  confidence: number
}

export interface InconsistencyEvent {
  eventId: string
  market: string
  inconsistencyType: string
  severity: number
  providerA: string
  providerB: string
  oddA: number
  oddB: number
  deviationPct: number
}

export interface LatencyProviderStats {
  provider: string
  avgMs: number
  medianMs: number
  p95Ms: number
  samples: number
}

export interface ValidationReport {
  total_entries: number
  closed_entries: number
  open_entries: number
  avg_clv_pct: number
  median_clv_pct: number
  positive_rate: number
  avg_ev: number
  ev_clv_correlation: number
  avg_timing_hours: number
  optimal_timing_rate: number
  avg_detection_delay_ms: number
  market_efficiency_score: number
  model_accuracy_score: number
  profit_simulation_roi: number
  total_kelly_stake: number
  sharpe_ratio: number
}
