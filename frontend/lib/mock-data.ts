import type {
  ValueOpportunity, MarketOdds, AlertItem, PerformanceSnapshot,
  SystemStatus, Sport, TrendDir, ValueGrade, RiskLevel, Regime,
  OddsPoint, OddsHistory, MarketAnalytics, OpportunityLevel,
} from "./types"

const SPORTS: Sport[] = ["soccer", "basketball", "tennis", "american_football"]

const TEAMS: Record<string, string[]> = {
  soccer: ["Manchester City", "Liverpool", "Arsenal", "Barcelona", "Real Madrid", "Bayern Munich", "PSG", "Juventus"],
  basketball: ["LA Lakers", "Boston Celtics", "Golden State", "Miami Heat", "Chicago Bulls", "New York Knicks", "Brooklyn Nets", "Milwaukee Bucks"],
  tennis: ["Alcaraz C.", "Sinner J.", "Djokovic N.", "Medvedev D.", "Federer R.", "Nadal R."],
  american_football: ["Kansas City", "San Francisco", "Philadelphia", "Dallas Cowboys", "Buffalo Bills", "Cincinnati Bengals"],
}

const BOOKMAKERS = ["Betano", "Pinnacle", "Bet365", "DraftKings", "FanDuel", "Betway"]
export const PRIMARY_BOOKMAKER = "Betano"
const LEAGUES: Record<string, string> = {
  soccer: "Premier League",
  basketball: "NBA",
  tennis: "ATP",
  american_football: "NFL",
}

const MARKET_LABELS: Record<string, string> = {
  soccer: "1X2 / Resultado Final",
  basketball: "Vencedor da Partida",
  tennis: "Vencedor da Partida",
  american_football: "Vencedor da Partida (Moneyline)",
}

const NAV_PATHS: Record<string, (home: string, away: string) => string> = {
  soccer: (h, a) => `Futebol → Inglaterra → Premier League → ${h} vs ${a} → Mercado 1X2`,
  basketball: (h, a) => `Basquete → EUA → NBA → ${h} vs ${a} → Vencedor`,
  tennis: (h, a) => `Tênis → ATP → ATP Tour → ${h} vs ${a} → Vencedor`,
  american_football: (h, a) => `Futebol Americano → EUA → NFL → ${h} vs ${a} → Moneyline`,
}

let _idCounter = 0
function nextId(): string { return `${++_idCounter}` }
function pick<T>(arr: T[]): T { return arr[Math.floor(Math.random() * arr.length)] }
function pickBiased<T>(arr: T[], biasIndex = 0, biasWeight = 0.6): T {
  return Math.random() < biasWeight ? arr[biasIndex] : pick(arr)
}
function rand(min: number, max: number): number { return Math.random() * (max - min) + min }
function randInt(min: number, max: number): number { return Math.floor(rand(min, max + 1)) }

function generateOddsHistory(): OddsHistory {
  const n = randInt(10, 25)
  const openingOdd = +(rand(1.2, 6.0)).toFixed(2)
  const drift = rand(-0.15, 0.15)
  const currentOdd = +(openingOdd * (1 + drift)).toFixed(2)
  const now = Date.now()
  const interval = randInt(2, 8) * 60000
  const ticks: OddsPoint[] = []
  let val = openingOdd
  for (let i = 0; i < n; i++) {
    val += (currentOdd - openingOdd) / n + rand(-0.02, 0.02)
    val = Math.max(1.01, val)
    ticks.push({
      timestamp: new Date(now - (n - i) * interval).toISOString(),
      odd: +val.toFixed(2),
      bookmaker: pick(BOOKMAKERS),
    })
  }
  const volatility = +rand(0.05, 0.6).toFixed(3)
  const maxMove = +Math.max(...ticks.map((t, i) =>
    i === 0 ? 0 : Math.abs(t.odd - ticks[i - 1].odd)
  )).toFixed(2)
  const trend: TrendDir = currentOdd > openingOdd * 1.03 ? "up" : currentOdd < openingOdd * 0.97 ? "down" : "stable"
  return {
    eventId: `hist_${nextId()}`,
    outcome: "home",
    openingOdd,
    currentOdd,
    movement: ticks,
    volatility,
    trend,
    tickCount: n,
    maxMove,
  }
}

function generateOpportunity(): ValueOpportunity {
  const sport = pick(SPORTS)
  const teams = TEAMS[sport]
  const homeTeam = pick(teams)
  let awayTeam = pick(teams)
  while (awayTeam === homeTeam) awayTeam = pick(teams)

  const impliedProb = rand(0.25, 0.75)
  const fairProb = impliedProb + rand(-0.03, 0.12)
  const odd = +(1 / impliedProb).toFixed(2)
  const fairOdd = +(1 / fairProb).toFixed(2)
  const ev = +(fairProb * odd - 1).toFixed(4)
  const edge = +(ev * 100).toFixed(2)

  const gradeIdx = ev > 0.08 ? 0 : ev > 0.05 ? 1 : ev > 0.03 ? 2 : 3
  const riskIdx = ev > 0.08 ? 2 : ev > 0.05 ? 1 : 0
  const gradeOrder: ValueGrade[] = ["ELITE", "STRONG", "SOLID", "SPECULATIVE"]
  const riskOrder: RiskLevel[] = ["LOW", "MEDIUM", "HIGH"]

  const hist = generateOddsHistory()
  const volatility = hist.volatility + rand(-0.1, 0.1)

  const now = new Date()
  const expires = new Date(now.getTime() + randInt(1, 12) * 3600000)

  const isBetano = Math.random() < 0.55
  const bookmaker = isBetano ? PRIMARY_BOOKMAKER : pick(BOOKMAKERS.filter(b => b !== PRIMARY_BOOKMAKER))
  const betanoOdd = +(odd * (1 + rand(-0.04, 0.04))).toFixed(2)

  const otherOdds = BOOKMAKERS
    .filter(b => b !== PRIMARY_BOOKMAKER && b !== bookmaker)
    .slice(0, 3)
    .map(b => +(odd * (1 + rand(-0.06, 0.06))).toFixed(2))
  const allOdds = [betanoOdd, ...otherOdds]
  const marketAvgOdd = +((isBetano ? allOdds : [odd, ...otherOdds]).reduce((a, b) => a + b, 0) / 3).toFixed(2)
  const bestOdd = +Math.max(...allOdds).toFixed(2)
  const bestBookmaker = bestOdd === betanoOdd ? PRIMARY_BOOKMAKER : pick(BOOKMAKERS.filter(b => b !== PRIMARY_BOOKMAKER))

  const eventDateObj = new Date(now.getTime() + randInt(1, 168) * 3600000)
  const eventDate = eventDateObj.toISOString().split("T")[0]
  const eventTimeUtc = eventDateObj.toISOString().split("T")[1].slice(0, 5)
  const eventTimeLocal = eventDateObj.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
  const marketTypeLabel = MARKET_LABELS[sport]
  const betanoNavigationPath = NAV_PATHS[sport](homeTeam, awayTeam)
  const opportunityLevel: OpportunityLevel = ev > 0.07 ? "high" : ev > 0.04 ? "medium" : "low"

  return {
    id: nextId(),
    eventId: `evt_${nextId()}`,
    sport,
    league: LEAGUES[sport],
    homeTeam,
    awayTeam,
    market: "h2h",
    outcome: ev > 0 ? "home" : "away",
    bookmaker,
    bookmakerOdd: odd,
    betanoOdd,
    marketAvgOdd,
    bestOdd,
    bestBookmaker,
    eventDate,
    eventTimeUtc,
    eventTimeLocal,
    marketTypeLabel,
    opportunityLevel,
    betanoNavigationPath,
    fairOdd,
    fairProbability: +fairProb.toFixed(4),
    impliedProbability: +impliedProb.toFixed(4),
    expectedValue: ev,
    edgePct: edge,
    kellyStake: +Math.max(0, (ev / (odd - 1)) * 0.5 * rand(0.5, 1.0)).toFixed(4),
    confidence: +rand(0.4, 0.95).toFixed(3),
    riskScore: +rand(0.1, 0.7).toFixed(3),
    riskLevel: riskOrder[riskIdx],
    grade: gradeOrder[gradeIdx],
    volatility: +Math.max(0, volatility).toFixed(3),
    trend: hist.trend,
    detectedAt: now.toISOString(),
    expiresAt: expires.toISOString(),
    oddsHistory: hist,
  }
}

export function generateOpportunities(count = 20): ValueOpportunity[] {
  return Array.from({ length: count }, generateOpportunity)
    .sort((a, b) => b.expectedValue - a.expectedValue)
}

export function generateMarketOdds(count = 8): MarketOdds[] {
  return SPORTS.flatMap((sport) => {
    const teams = TEAMS[sport]
    return Array.from({ length: Math.max(1, Math.floor(count / SPORTS.length)) }, (_, i) => {
      const home = teams[i % teams.length]
      const away = teams[(i + 1) % teams.length]
      if (!home || !away || home === away) return null
      const hProb = rand(0.3, 0.6)
      const aProb = rand(0.2, 0.4)
      return {
        eventId: `mkt_${sport}_${i}`,
        sport,
        homeTeam: home,
        awayTeam: away,
        market: "h2h" as const,
        homeOdd: +(1 / hProb).toFixed(2),
        awayOdd: +(1 / aProb).toFixed(2),
        drawOdd: sport === "soccer" ? +(1 / (1 - hProb - aProb)).toFixed(2) : null,
        bookmaker: pick(BOOKMAKERS),
        capturedAt: new Date().toISOString(),
      }
    }).filter(Boolean) as MarketOdds[]
  })
}

export function generateAlerts(count = 12): AlertItem[] {
  const messages: { msg: string; type: AlertItem["type"]; sev: AlertItem["severity"] }[] = [
    { msg: "Betano está oferecendo valor acima do mercado em Manchester City vs Liverpool", type: "opportunity", sev: "critical" },
    { msg: "Oportunidade na Betano: LA Lakers @ Boston Celtics com odd acima da média", type: "opportunity", sev: "warning" },
    { msg: "Movimento forte na Betano: odds de Alcaraz caíram 8% em 2 minutos", type: "movement", sev: "warning" },
    { msg: "Betano acima do mercado: diferença de 5% em relação à média no jogo do Real Madrid", type: "drift", sev: "warning" },
    { msg: "ATENÇÃO: mercado entrou em regime CAÓTICO — evite apostas de alto risco", type: "risk", sev: "critical" },
    { msg: "Sistema atualizado: algoritmo de análise da Betano recalibrado", type: "system", sev: "info" },
    { msg: "Possível oportunidade na Betano: Sinner vs Djokovic com odd favorável", type: "opportunity", sev: "info" },
    { msg: "Betano destoa do mercado: 80% do dinheiro está no Kansas City -7.5", type: "drift", sev: "info" },
    { msg: "URGENTE: Bayern Munich caiu de 1.85 → 1.72 na Betano", type: "movement", sev: "critical" },
    { msg: "Mercado oscilando: 3 esportes com divergência entre Betano e concorrentes", type: "system", sev: "warning" },
    { msg: "Oportunidade moderada na Betano: Philadelphia @ Dallas Cowboys", type: "opportunity", sev: "info" },
    { msg: "ATENÇÃO: liquidez baixa no tênis — Betano pode estar defasada", type: "risk", sev: "warning" },
  ]
  const selected = messages.slice(0, count)
  return selected.map((m, i) => ({
    id: `alert_${nextId()}`,
    type: m.type,
    severity: m.sev,
    message: m.msg,
    timestamp: new Date(Date.now() - i * randInt(30, 300) * 1000).toISOString(),
    evValue: m.sev === "critical" ? +rand(8, 15).toFixed(1) : m.sev === "warning" ? +rand(3, 8).toFixed(1) : null,
    sport: pick(SPORTS),
  }))
}

export function generatePerformanceHistory(points = 50): PerformanceSnapshot[] {
  const now = Date.now()
  let brier = 0.18
  let roi = -2
  const snapshots: PerformanceSnapshot[] = []
  for (let i = 0; i < points; i++) {
    brier += rand(-0.008, 0.008)
    brier = Math.max(0.08, Math.min(0.35, brier))
    roi += rand(-0.5, 1.2)
    snapshots.push({
      timestamp: new Date(now + i * 86400000).toISOString(),
      brier: +brier.toFixed(4),
      accuracy: +(0.5 + (0.5 - brier)).toFixed(3),
      aucRoc: +(0.6 + rand(0, 0.25)).toFixed(3),
      roi: +roi.toFixed(2),
      nBets: randInt(3, 15),
    })
  }
  return snapshots
}

export function computeAnalytics(opps: ValueOpportunity[]): MarketAnalytics {
  const n = opps.length
  if (n === 0) return {
    totalOpportunities: 0, avgEV: 0, avgEdge: 0, bestEV: 0, bestEdge: 0,
    highConfCount: 0, eliteCount: 0, strongCount: 0, avgConfidence: 0,
    volatileEvents: 0, alertsActive: 0, bestBookmaker: "—",
    opportunitiesBySport: {},
  }

  const sumEV = opps.reduce((s, o) => s + o.expectedValue, 0)
  const sumEdge = opps.reduce((s, o) => s + o.edgePct, 0)
  const sumConf = opps.reduce((s, o) => s + o.confidence, 0)
  const bestEV = Math.max(...opps.map(o => o.expectedValue))
  const bestEdge = Math.max(...opps.map(o => o.edgePct))
  const highConf = opps.filter(o => o.confidence > 0.7).length
  const elite = opps.filter(o => o.grade === "ELITE").length
  const strong = opps.filter(o => o.grade === "STRONG").length
  const volatile = opps.filter(o => (o.volatility ?? 0) > 0.3).length

  const bySport: Record<string, number> = {}
  for (const o of opps) {
    bySport[o.sport] = (bySport[o.sport] || 0) + 1
  }

  const bkCounts: Record<string, number> = {}
  for (const o of opps) {
    bkCounts[o.bookmaker] = (bkCounts[o.bookmaker] || 0) + 1
  }
  const bestBk = Object.entries(bkCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || "—"

  return {
    totalOpportunities: n,
    avgEV: +(sumEV / n * 100).toFixed(2),
    avgEdge: +(sumEdge / n).toFixed(2),
    bestEV: +(bestEV * 100).toFixed(2),
    bestEdge: +bestEdge.toFixed(2),
    highConfCount: highConf,
    eliteCount: elite,
    strongCount: strong,
    avgConfidence: +(sumConf / n).toFixed(3),
    volatileEvents: volatile,
    alertsActive: volatile + elite + Math.floor(n * 0.2),
    bestBookmaker: bestBk,
    opportunitiesBySport: bySport,
  }
}

export function generateSystemStatus(): SystemStatus {
  const regimes: Regime[] = ["calm", "normal", "volatile", "chaotic"]
  return {
    connected: true,
    lastUpdate: new Date().toISOString(),
    uptime: randInt(1, 168),
    eventsTracked: randInt(50, 300),
    modelsActive: 4,
    latencyMs: +rand(8, 80).toFixed(0),
    regime: pick(regimes),
    wsReconnects: randInt(0, 3),
  }
}
