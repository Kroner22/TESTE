import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"
import type { SortConfig, ValueOpportunity, TrendDir, ValueGrade } from "./types"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(value: number, decimals = 2): string {
  return value.toFixed(decimals)
}

export function formatPercent(value: number): string {
  const sign = value >= 0 ? "+" : ""
  return `${sign}${(value * 100).toFixed(2)}%`
}

export function formatPercentSimple(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

export function formatOdds(value: number): string {
  return value.toFixed(2)
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("pt-BR", { month: "short", day: "numeric" })
}

export function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const sec = Math.floor(diff / 1000)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}min`
  const hr = Math.floor(min / 60)
  return `${hr}h`
}

export function probabilityToOdds(prob: number): number {
  if (prob <= 0) return 0
  return +(1 / prob).toFixed(2)
}

export function sortOpportunities(opps: ValueOpportunity[], sort: SortConfig): ValueOpportunity[] {
  return [...opps].sort((a, b) => {
    let cmp = 0
    switch (sort.field) {
      case "ev":
        cmp = a.expectedValue - b.expectedValue
        break
      case "edge":
        cmp = a.edgePct - b.edgePct
        break
      case "volatility":
        cmp = (a.volatility ?? 0) - (b.volatility ?? 0)
        break
      case "confidence":
        cmp = a.confidence - b.confidence
        break
      case "kelly":
        cmp = a.kellyStake - b.kellyStake
        break
      case "odd":
        cmp = a.bookmakerOdd - b.bookmakerOdd
        break
      case "timestamp":
        cmp = new Date(a.detectedAt).getTime() - new Date(b.detectedAt).getTime()
        break
    }
    return sort.dir === "desc" ? -cmp : cmp
  })
}

export function paginate<T>(items: T[], page: number, perPage: number): T[] {
  return items.slice((page - 1) * perPage, page * perPage)
}

export function gradeStars(grade: ValueGrade): string {
  switch (grade) {
    case "ELITE": return "★★★★★"
    case "STRONG": return "★★★★"
    case "SOLID": return "★★★"
    case "SPECULATIVE": return "★★"
    case "NOISE": return "★"
  }
}

export function gradeLabel(grade: ValueGrade): string {
  switch (grade) {
    case "ELITE": return "Excelente"
    case "STRONG": return "Boa"
    case "SOLID": return "Sólida"
    case "SPECULATIVE": return "Especulativa"
    case "NOISE": return "Ruído"
  }
}

export function qualityLabel(confidence: number): string {
  if (confidence >= 0.8) return "Muito Alta"
  if (confidence >= 0.6) return "Alta"
  if (confidence >= 0.4) return "Média"
  return "Baixa"
}

export function opportunitySummary(opp: ValueOpportunity): string {
  const nome = `${opp.homeTeam} vs ${opp.awayTeam}`
  const odd = opp.bookmakerOdd.toFixed(2)
  const prob = (opp.fairProbability * 100).toFixed(0)
  return `${nome} — Odd ${odd}, ~${prob}% de chance real`
}

export function trendColor(trend: TrendDir): string {
  switch (trend) {
    case "up": return "text-brand-green"
    case "down": return "text-brand-red"
    case "stable": return "text-brand-text"
  }
}

export function opportunityLevelLabel(level: string): string {
  switch (level) {
    case "high": return "Alta oportunidade"
    case "medium": return "Oportunidade moderada"
    case "low": return "Baixa oportunidade"
    default: return level
  }
}

export function opportunityLevelColor(level: string): string {
  switch (level) {
    case "high": return "text-brand-red"
    case "medium": return "text-brand-amber"
    case "low": return "text-brand-green"
    default: return "text-brand-text"
  }
}

export function opportunityLevelBg(level: string): string {
  switch (level) {
    case "high": return "bg-brand-red/10"
    case "medium": return "bg-brand-amber/10"
    case "low": return "bg-brand-green/10"
    default: return "bg-brand-border/50"
  }
}

export function opportunityLevelDot(level: string): string {
  switch (level) {
    case "high": return "🔴"
    case "medium": return "🟡"
    case "low": return "🟢"
    default: return "⚪"
  }
}

export function isValidOpportunity(opp: ValueOpportunity): boolean {
  if (!opp.homeTeam || !opp.awayTeam) return false
  if (!opp.eventDate) return false
  if (!opp.eventTimeUtc) return false
  if (!opp.marketTypeLabel) return false
  if (!opp.betanoNavigationPath) return false
  return true
}
