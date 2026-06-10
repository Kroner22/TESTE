const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

interface ApiError {
  status: number
  message: string
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_URL}${path}`
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    throw { status: res.status, message: body.detail || res.statusText } as ApiError
  }
  return res.json()
}

export function isApiReachable(): Promise<boolean> {
  return request<{ status: string }>("/health/live")
    .then(() => true)
    .catch(() => false)
}

export namespace api {
  // ── Health ──
  export const health = {
    live: () => request<{ status: string }>("/health/live"),
    ready: () => request<{ status: string }>("/health/ready"),
    info: () => request<Record<string, unknown>>("/health/info"),
  }

  // ── Events ──
  export const events = {
    list: (params?: { sport?: string; status?: string; limit?: number }) => {
      const q = new URLSearchParams()
      if (params?.sport) q.set("sport", params.sport)
      if (params?.status) q.set("status", params.status)
      if (params?.limit) q.set("limit", String(params.limit))
      return request<Array<{
        event_id: string; sport: string; home_team: string
        away_team: string; start_time: string; status: string
      }>>(`/api/v1/events?${q}`)
    },
    odds: (eventId: string, limit?: number) => {
      const q = limit ? `?limit=${limit}` : ""
      return request<Array<{
        market: string; outcome: string; bookmaker: string
        odd: number; timestamp: string; is_opening: boolean
      }>>(`/api/v1/events/${eventId}/odds${q}`)
    },
  }

  // ── Opportunities ──
  export const opportunities = {
    list: (params?: { min_ev?: number; min_confidence?: number; limit?: number }) => {
      const q = new URLSearchParams()
      if (params?.min_ev) q.set("min_ev", String(params.min_ev))
      if (params?.min_confidence) q.set("min_confidence", String(params.min_confidence))
      if (params?.limit) q.set("limit", String(params.limit))
      return request<Array<{
        event_id: string; market: string; outcome: string; bookmaker: string
        odd: number; ev: number; fair_prob: number; implied_prob: number
        confidence: number; edge_score: number; kelly_stake: number
        value_grade: string; risk_level: string
      }>>(`/api/v1/opportunities?${q}`)
    },
  }

  // ── Alerts ──
  export const alerts = {
    list: (params?: { severity?: string; limit?: number }) => {
      const q = new URLSearchParams()
      if (params?.severity) q.set("severity", params.severity)
      if (params?.limit) q.set("limit", String(params.limit))
      return request<Array<{
        event_id: string; alert_type: string; severity: string
        message: string; ev_value: number | null; created_at: string
      }>>(`/api/v1/alerts?${q}`)
    },
  }

  // ── CLV ──
  export const clv = {
    submitRecords: (records: Array<{
      event_id: string; outcome: string; bookmaker: string
      captured_odd: number; captured_at: string
      closing_odd: number; closed_at: string
      opening_odd?: number; opening_at?: string
      simulated_ev?: number; simulated_kelly?: number; model_edge?: number
    }>) =>
      request<{ submitted: number; total: number }>("/api/v1/clv/records", {
        method: "POST",
        body: JSON.stringify(records),
      }),

    getReport: () => request<ClvApiReport>("/api/v1/clv/report"),
    getReportText: () => request<{ text: string }>("/api/v1/clv/report/text"),
    getDistribution: () => request<ClvDistribution>("/api/v1/clv/distribution"),
    getByBookmaker: () => request<Array<BookmakerClvStats>>("/api/v1/clv/by-bookmaker"),
    getTiming: () => request<TimingAnalysis>("/api/v1/clv/timing"),
    getLeaks: () => request<{ leaks: Array<unknown>; count: number }>("/api/v1/clv/leaks"),
    getCorrelation: () => request<ClvCorrelation>("/api/v1/clv/correlation"),
    getTTest: () => request<Record<string, unknown>>("/api/v1/clv/t-test"),
    clearRecords: () => request<{ cleared: number }>("/api/v1/clv/records", { method: "DELETE" }),
  }
}

export interface ClvApiReport {
  generated_at: string
  n_records: number
  n_events: number
  n_bookmakers: number
  overall_clv_pct: number
  verdict: string
  recommendations: string[]
  model_quality: string
  distribution?: ClvDistribution
  correlation?: ClvCorrelation
  timing?: TimingAnalysis
  by_bookmaker?: BookmakerClvStats[]
}

export interface ClvDistribution {
  total_records: number
  mean_clv: number
  median_clv: number
  std_clv: number
  min_clv: number
  max_clv: number
  positive_count: number
  positive_pct: number
  negative_count: number
  negative_pct: number
  neutral_count: number
  grade_distribution: Record<string, number>
}

export interface ClvCorrelation {
  pearson_r: number
  spearman_rho: number
  p_value: number
  interpretation: string
}

export interface TimingAnalysis {
  avg_hours_to_close: number
  early_pct: number
  optimal_pct: number
  late_pct: number
  dead_pct: number
  best_timing_clv: number
  worst_timing_clv: number
  early_avg_clv: number
  late_avg_clv: number
}

export interface BookmakerClvStats {
  bookmaker: string
  n_bets: number
  avg_clv_pct: number
  median_clv_pct: number
  std_clv_pct: number
  positive_rate: number
  elite_rate: number
  catastrophic_rate: number
  avg_timing_score: number
  best_outcome: string
  worst_outcome: string
}
