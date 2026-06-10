from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Callable, Awaitable

from backend.app.database import SessionLocal, ClvRecordPersistence
from backend.app.log_config import get_logger
from backend.domains.clv.calculator import build_clv_record, compute_clv
from backend.domains.clv.analyzer import (
    compute_distribution, compute_by_bookmaker, compute_correlation, compute_timing_analysis,
)
from backend.domains.clv.models import ClvRecord, ClvReport, ClvSnapshot

logger = get_logger(__name__)


class EntryOddsCapture:
    event_id: str
    market: str
    outcome: str
    bookmaker: str
    odd: Decimal
    prob: float
    timestamp: datetime
    ev: float
    confidence: float
    is_open: bool

    def __init__(self, event_id: str, market: str, outcome: str, bookmaker: str, odd: Decimal, timestamp: datetime, ev: float = 0.0, confidence: float = 0.0):
        self.event_id = event_id
        self.market = market
        self.outcome = outcome
        self.bookmaker = bookmaker
        self.odd = odd
        self.prob = float(1.0 / float(odd)) if odd > 1 else 0.0
        self.timestamp = timestamp
        self.ev = ev
        self.confidence = confidence
        self.is_open = True


class ClvFeedbackLoop:
    """
    Continuous CLV feedback loop.

    Flow:
    1. Opportunity detected → capture entry odds (EntryOddsCapture)
    2. Odds stream continues → track closing odds
    3. Event closes → compute CLV = captured vs closing
    4. Store ClvRecord
    5. Periodically generate ClvReport
    """

    def __init__(self):
        self._entries: dict[str, EntryOddsCapture] = {}
        self._closing_odds: dict[str, list[ClvSnapshot]] = defaultdict(list)
        self._clv_records: list[ClvRecord] = []
        self._reports: list[ClvReport] = []
        self._last_report_time = 0.0
        self._report_interval = 60.0

        self._broadcast_callback: Optional[Callable[[dict], Awaitable[None]]] = None

    def set_broadcast_callback(self, callback: Callable[[dict], Awaitable[None]]):
        self._broadcast_callback = callback

    def capture_entry(self, event_id: str, market: str, outcome: str, bookmaker: str, odd: Decimal, ev: float = 0.0, confidence: float = 0.0):
        key = self._entry_key(event_id, market, outcome, bookmaker)
        if key not in self._entries:
            self._entries[key] = EntryOddsCapture(
                event_id=event_id, market=market, outcome=outcome, bookmaker=bookmaker,
                odd=odd, timestamp=datetime.now(timezone.utc), ev=ev, confidence=confidence,
            )
            logger.info("clv_entry_captured", event_id=event_id, bookmaker=bookmaker, odd=float(odd))

    def track_odds_snapshot(self, event_id: str, market: str, outcome: str, bookmaker: str, odd: Decimal, is_closing: bool = False):
        ts = datetime.now(timezone.utc)
        self._closing_odds[bookmaker].append(ClvSnapshot(
            event_id=event_id, market=market, outcome=outcome, bookmaker=bookmaker,
            odd=odd, prob=float(1.0 / float(odd)) if odd > 1 else 0.0, timestamp=ts,
            is_closing=is_closing, version=len(self._closing_odds[bookmaker]),
        ))
        if len(self._closing_odds[bookmaker]) > 1000:
            self._closing_odds[bookmaker] = self._closing_odds[bookmaker][-500:]

    def find_closing_odd(self, event_id: str, market: str, outcome: str, bookmaker: str) -> Optional[ClvSnapshot]:
        candidates = [s for s in self._closing_odds.get(bookmaker, []) if s.event_id == event_id and s.market == market and s.outcome == outcome]
        if not candidates:
            return None
        return max(candidates, key=lambda s: s.timestamp)

    def close_entry(self, event_id: str, market: str, outcome: str, bookmaker: str) -> Optional[ClvRecord]:
        entry_key = self._entry_key(event_id, market, outcome, bookmaker)
        entry = self._entries.get(entry_key)
        if not entry:
            return None

        closing = self.find_closing_odd(event_id, market, outcome, bookmaker)
        if not closing:
            return None

        record = build_clv_record(
            event_id=event_id,
            market=market,
            outcome=outcome,
            bookmaker=bookmaker,
            captured_odd=entry.odd,
            captured_at=entry.timestamp,
            closing_odd=closing.odd,
            closed_at=closing.timestamp,
            opening_odd=entry.odd,
            opening_at=entry.timestamp,
            simulated_ev=entry.ev,
        )

        self._clv_records.append(record)
        entry.is_open = False
        self._persist_clv_record(record, entry)

        logger.info("clv_entry_closed", event_id=event_id, clv_pct=round(record.clv_pct, 2), grade=record.grade.value)

        if self._broadcast_callback:
            import asyncio
            asyncio.ensure_future(self._broadcast_callback({
                "type": "clv_record",
                "data": {
                    "event_id": event_id,
                    "market": market,
                    "outcome": outcome,
                    "bookmaker": bookmaker,
                    "clv_pct": round(record.clv_pct, 2),
                    "grade": record.grade.value,
                    "closing_odd": float(closing.odd),
                    "captured_odd": float(entry.odd),
                    "hours_to_close": round(record.hours_to_close, 1),
                    "timing_efficiency": record.timing_efficiency.value,
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))

        return record

    def get_open_entries(self) -> list[EntryOddsCapture]:
        return [e for e in self._entries.values() if e.is_open]

    def get_open_count(self) -> int:
        return sum(1 for e in self._entries.values() if e.is_open)

    def get_closed_count(self) -> int:
        return len(self._clv_records)

    def generate_report(self) -> ClvReport:
        records = self._clv_records

        if not records:
            report = ClvReport(n_records=0)
        else:
            distribution = compute_distribution(records)
            by_bk = compute_by_bookmaker(records)
            correlation = compute_correlation(records)
            timing = compute_timing_analysis(records)

            total_ev = sum(r.simulated_ev for r in records)
            total_clv = sum(r.clv_pct for r in records)
            n = len(records)
            positive_clv = sum(1 for r in records if r.clv_pct > 0)
            negative_clv = sum(1 for r in records if r.clv_pct < 0)

            avg_ev = total_ev / n if n > 0 else 0
            avg_clv = total_clv / n if n > 0 else 0

            ev_accuracy = positive_clv / n * 100 if n > 0 else 0
            model_efficiency = (avg_clv - avg_ev) if n > 0 else 0

            if avg_clv > 0 and distribution.positive_pct > 50:
                verdict = "Modelo VALIDADO — edge real detectado contra o mercado"
                recommendations = [
                    "Continuar capturando entradas nas mesmas condições",
                    "Aumentar exposição gradual (Kelly fractional)",
                    "Monitorar degradação do edge ao longo do tempo",
                ]
            elif avg_clv > 0 and distribution.positive_pct <= 50:
                verdict = "Sinal positivo porém inconsistente — mais dados necessários"
                recommendations = ["Aumentar amostra antes de conclusão", "Revisar critérios de filtragem"]
            elif avg_clv < -1.0:
                verdict = "Modelo INVALIDADO — edge negativo contra o mercado real"
                recommendations = [
                    "Revisar completamente o modelo de fair probability",
                    "Verificar timing de captura versus movimento real",
                    "Ajustar parâmetros de overround removal",
                ]
            else:
                verdict = "Resultados inconclusivos — continuar coletando dados"
                recommendations = ["Aguardar mais 100+ entradas antes de conclusão"]

            report = ClvReport(
                n_records=n,
                n_events=len(set(r.event_id for r in records)),
                n_bookmakers=len(set(r.bookmaker for r in records)),
                overall_clv=avg_clv,
                overall_clv_pct=avg_clv,
                distribution=distribution,
                by_bookmaker=by_bk,
                correlation=correlation,
                timing=timing,
                model_quality=f"EV médio: {avg_ev:.2%} | CLV médio: {avg_clv:.2%} | Acurácia EV→CLV: {ev_accuracy:.1f}% | Eficiência: {model_efficiency:+.2%}",
                verdict=verdict,
                recommendations=recommendations,
            )

        now = time.time()
        if now - self._last_report_time > self._report_interval:
            self._reports.append(report)
            self._last_report_time = now
            if len(self._reports) > 50:
                self._reports = self._reports[-50:]

            if self._broadcast_callback:
                import asyncio
                asyncio.ensure_future(self._broadcast_callback({
                    "type": "clv_report",
                    "data": {
                        "n_records": report.n_records,
                        "overall_clv_pct": round(report.overall_clv_pct, 2),
                        "positive_pct": round(report.distribution.positive_pct, 1) if report.distribution else 0,
                        "verdict": report.verdict,
                        "model_quality": report.model_quality,
                        "n_bookmakers": report.n_bookmakers,
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }))

        return report

    def get_latest_report(self) -> Optional[ClvReport]:
        return self._reports[-1] if self._reports else None

    def load_from_db(self):
        """Load historical CLV records from database."""
        db = SessionLocal()
        try:
            records = db.query(ClvRecordPersistence).all()
            for rec in records:
                clv_rec = ClvRecord(
                    event_id=rec.event_id,
                    market=rec.market,
                    outcome=rec.outcome,
                    bookmaker=rec.bookmaker,
                    clv_pct=float(rec.clv_pct),
                    grade=rec.clv_grade,
                    simulated_ev=float(rec.simulated_ev or 0),
                    timing_efficiency=rec.timing_efficiency,
                    hours_to_close=float(rec.hours_to_close or 0),
                )
                self._clv_records.append(clv_rec)
            if records:
                logger.info("clv_records_loaded_from_db", count=len(records))
        except Exception as e:
            logger.error("clv_records_load_failed", error=str(e))
        finally:
            db.close()

    def _persist_clv_record(self, record: ClvRecord, entry: EntryOddsCapture):
        db = SessionLocal()
        try:
            rec = ClvRecordPersistence(
                event_id=record.event_id,
                market=record.market,
                outcome=record.outcome,
                bookmaker=record.bookmaker,
                entry_odd=Decimal(str(float(entry.odd))),
                closing_odd=Decimal(str(record.closing_odd)) if hasattr(record, 'closing_odd') else Decimal('0'),
                entry_timestamp=entry.timestamp,
                closing_timestamp=datetime.now(timezone.utc),
                clv_pct=Decimal(str(record.clv_pct)),
                clv_grade=record.grade.value if hasattr(record.grade, 'value') else str(record.grade),
                simulated_ev=Decimal(str(record.simulated_ev)),
                timing_efficiency=record.timing_efficiency.value if hasattr(record.timing_efficiency, 'value') else str(record.timing_efficiency),
                hours_to_close=Decimal(str(record.hours_to_close)),
            )
            db.add(rec)
            db.commit()
        except Exception as e:
            logger.error("clv_record_persist_failed", event_id=record.event_id, error=str(e))
        finally:
            db.close()

    def _entry_key(self, event_id: str, market: str, outcome: str, bookmaker: str) -> str:
        return f"{event_id}:{market}:{outcome}:{bookmaker}"
