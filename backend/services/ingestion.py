from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.database import SessionLocal, Event, OddsRecord, OpportunityRecord, AlertRecord
from backend.app.log_config import get_logger
from backend.services.providers.base import BaseProvider, OddsUpdate, OddsEvent, ProviderConfig
from backend.services.providers.mock_provider import MockProvider

from backend.domains.value.probability import compute_fair_probabilities
from backend.domains.value.ev import compute_expected_value, classify_value_grade
from backend.domains.value.kelly import compute_kelly
from backend.domains.value.confidence import compute_confidence
from backend.domains.value.risk import compute_risk_score

from backend.services.reconciliation.market_truth import (
    MarketTruthService, SurveyPoint, SharpMoveEvent, InconsistencyEvent,
)
from backend.services.reconciliation.market_emulator import MarketEmulator
from backend.services.reconciliation.real_data_pipeline import RealDataPipeline
from backend.services.reconciliation.clv_feedback_loop import ClvFeedbackLoop
from backend.services.reconciliation.validation_report import ValidationReportGenerator
from backend.services.reconciliation.secondary_odds_provider import SecondaryOddsProvider
from backend.services.reconciliation.event_unifier_service import EventUnifierService, UnifiedEvent
from backend.services.reconciliation.market_snapshot_engine import MarketSnapshotEngine
from backend.services.reconciliation.paper_trading_engine import PaperTradingEngine
from backend.services.reconciliation.market_efficiency_analyzer import MarketEfficiencyAnalyzer
from backend.services.reconciliation.alert_engine import AlertEngine, AlertEvent
from backend.services.reconciliation.telemetry import ProviderTelemetry
from backend.services.providers.real.provider_manager import ProviderManager
from backend.services.mode import RuntimeMode, get_mode_manager
from backend.services.providers.real.provider_registry import get_registry
from backend.services.providers.real.provider_health_monitor import get_health_monitor
from backend.app.models.real_market import init_real_market_tables

logger = get_logger(__name__)


class OddsIngestionService:
    """
    Ingests odds from providers, persists to DB, runs math engine,
    and broadcasts delta updates (odds_update, market_move, opp_add/remove).
    """

    def __init__(self):
        self._providers: dict[str, BaseProvider] = {}
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._broadcast_callback = None
        self._last_odds: dict[str, dict[str, Decimal]] = {}
        self._known_opps: set[str] = set()
        self._last_broadcast_time = 0.0
        self._batch_ms = 100
        self._truth_service = MarketTruthService()
        self._market_emulator = MarketEmulator()
        self._emulator_providers: set[str] = set()
        self._emulator_events_loaded = False
        self._latency_broadcast_interval = 5.0
        self._last_latency_broadcast = 0.0

        self._provider_manager = ProviderManager()
        self._mode_manager = get_mode_manager()
        self._provider_registry = get_registry()
        self._health_monitor = get_health_monitor()
        self._clv_feedback = ClvFeedbackLoop()
        self._validation = ValidationReportGenerator()
        self._data_mode = "SIMULATION"
        self._data_mode_reason = "Aguardando inicialização"
        self._validation_broadcast_interval = 30.0
        self._last_validation_broadcast = 0.0

        self._secondary_provider: Optional[BaseProvider] = None
        self._event_unifier = EventUnifierService()
        self._snapshot_engine = MarketSnapshotEngine(interval_seconds=10.0)
        self._paper_trading = PaperTradingEngine(initial_bankroll=1000.0)
        self._efficiency_analyzer = MarketEfficiencyAnalyzer()
        self._snapshot_counter = 0

        self._alert_engine = AlertEngine()
        self._telemetry = ProviderTelemetry()

    def register_provider(self, provider: BaseProvider):
        self._providers[provider.name] = provider

    @property
    def data_mode(self) -> str:
        return self._data_mode

    @property
    def data_mode_reason(self) -> str:
        return self._data_mode_reason

    def set_broadcast_callback(self, callback):
        self._broadcast_callback = callback
        self._clv_feedback.set_broadcast_callback(callback)
        self._snapshot_engine.set_broadcast_callback(callback)
        self._paper_trading.set_broadcast_callback(callback)
        self._efficiency_analyzer.set_broadcast_callback(callback)

    async def start(self):
        if self._running:
            return
        self._running = True

        # Initialize real-market tables
        try:
            init_real_market_tables()
            logger.info("real_market_tables_initialized")
        except Exception as e:
            logger.warning("real_market_tables_init_warning", error=str(e))

        # Initialize ProviderManager (real providers + fallback)
        await self._provider_manager.initialize()
        for provider in self._provider_manager.providers:
            self.register_provider(provider)
        self._data_mode = self._provider_manager.mode
        self._data_mode_reason = self._provider_manager.mode_reason

        # Initialize provider registry (registers all known providers, reusing already-initialized ones)
        try:
            pre_init = {p.name: p for p in self._providers.values()}
            await self._provider_registry.initialize(pre_initialized=pre_init)
            real_count = len(self._provider_registry.get_real_providers())
            if real_count > 0 and self._mode_manager.is_simulation:
                self._mode_manager.transition_to(
                    RuntimeMode.HYBRID,
                    f"{real_count} provedores reais disponiveis",
                )
                self._data_mode = "HYBRID"
                self._data_mode_reason = f"Modo hibrido: {real_count} provedor(es) real(is)"
                logger.info("mode_transition_hybrid", real_providers=real_count)
            logger.info("provider_registry_ready",
                        total=len(self._provider_registry.get_all()),
                        real=real_count)
        except Exception as e:
            logger.warning("provider_registry_init_warning", error=str(e))

        # Load persisted data from DB
        self._paper_trading.load_from_db()
        self._clv_feedback.load_from_db()

        for provider in self._providers.values():
            task = asyncio.create_task(self._run_provider(provider))
            self._tasks.append(task)

        # Register secondary provider independent of ProviderManager for multi-source validation
        self._secondary_provider = SecondaryOddsProvider()
        task_sec = asyncio.create_task(self._run_provider(self._secondary_provider))
        self._tasks.append(task_sec)

        # Periodic snapshot + efficiency analysis + alert broadcast
        task_snap = asyncio.create_task(self._run_snapshot_loop())
        self._tasks.append(task_snap)

        # Start provider health checks
        self._provider_manager.start_health_checks()

        logger.info("ingestion_service_started",
                    providers=list(self._providers.keys()),
                    mode=self._mode_manager.mode.value,
                    real_providers=len(self._provider_registry.get_real_providers()))

    async def stop(self):
        self._running = False
        self._provider_manager.stop_health_checks()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("ingestion_service_stopped")

    async def _run_provider(self, provider: BaseProvider):
        logger.info("run_provider_started", provider=provider.name)
        events = await provider.fetch_events()
        logger.info("run_provider_events", provider=provider.name, count=len(events))
        for i, event in enumerate(events):
            try:
                self._upsert_event(event)
            except Exception as e:
                logger.error("run_provider_initial_error", provider=provider.name, event_id=event.event_id, error=str(e))
        logger.info("run_provider_initial_done", provider=provider.name, total=len(events))

        # Streaming loop — runs in background but yields regularly
        while self._running:
            for event in events:
                try:
                    async for batch in provider.stream_odds(event.event_id):
                        if not self._running:
                            return
                        if batch:
                            await self._process_delta_batch(batch)
                except Exception as e:
                    logger.error("provider_stream_error", provider=provider.name, event_id=event.event_id, error=str(e))
                    await asyncio.sleep(5)
                await asyncio.sleep(0)

    async def _run_emulator(self):
        """Run the market emulator to simulate multi-provider data."""
        self._emulator_events_loaded = True
        em_events = self._market_emulator.get_events()
        self._emulator_providers = {p.name for p in self._market_emulator.get_providers()}
        tick = 0

        while self._running:
            for event in em_events:
                try:
                    odds_list = self._market_emulator.generate_odds(event, tick)
                    odds_updates = []
                    for provider_name, outcome, odd in odds_list:
                        latency = next(
                            (p.latency_ms for p in self._market_emulator.get_providers() if p.name == provider_name),
                            25.0,
                        )
                        odds_updates.append(OddsUpdate(
                            event_id=event.event_id,
                            market=event.market,
                            outcome=outcome,
                            bookmaker=provider_name,
                            odd=Decimal(str(odd)),
                            timestamp=datetime.now(timezone.utc),
                            is_opening=(tick == 0),
                            is_closing=False,
                        ))
                        self._truth_service.record_survey_point(SurveyPoint(
                            event_id=event.event_id,
                            market=event.market,
                            outcome=outcome,
                            provider=provider_name,
                            odd=odd,
                            timestamp=time.time(),
                            latency_ms=latency,
                        ))

                    if odds_updates:
                        await self._process_delta_batch(odds_updates, is_emulator=True)
                except Exception as e:
                    logger.error("emulator_error", event_id=event.event_id, error=str(e))

            tick += 1
            await asyncio.sleep(0.15)

    async def _run_secondary_emulator(self):
        """Generate secondary feed data for multi-source validation."""
        tick = 0
        while self._running:
            await asyncio.sleep(0.2)
            if not self._running:
                return
            if not self._secondary_provider:
                continue
            events = await self._secondary_provider.fetch_events()
            for event in events:
                odds = await self._secondary_provider.fetch_odds(event.event_id)
                if odds:
                    # Unify event across providers
                    unified = self._event_unifier.ingest_from_provider(
                        provider_name=self._secondary_provider.name,
                        event=event,
                        league="Multi-League",
                    )
                    for u in odds:
                        u.event_id = unified.canonical_id
                    await self._process_delta_batch(odds, is_emulator=True)
            tick += 1

    async def _run_snapshot_loop(self):
        """Periodically take market snapshots and run efficiency analysis."""
        while self._running:
            await asyncio.sleep(self._snapshot_engine._interval)
            if not self._running:
                return

            snapshot = self._snapshot_engine.take_snapshot()
            if snapshot:
                self._persist_snapshot(snapshot)

            stale_hours = 0.5 if self._data_mode == "SIMULATION" else 24.0
            self._paper_trading.close_stale_positions(max_age_hours=stale_hours)

            # Auto-close CLV entries that have been open long enough
            for entry in self._clv_feedback.get_open_entries():
                age_hours = (datetime.now(timezone.utc) - entry.timestamp).total_seconds() / 3600
                if age_hours > stale_hours:
                    self._clv_feedback.close_entry(entry.event_id, entry.market, entry.outcome, entry.bookmaker)

            if self._clv_feedback.get_closed_count() > 0:
                report = self._validation.generate(
                    clv_records=self._clv_feedback._clv_records,
                    open_count=self._clv_feedback.get_open_count(),
                )
                efficiency = self._efficiency_analyzer.analyze(
                    clv_records=self._clv_feedback._clv_records,
                )

                if self._broadcast_callback:
                    summary = self._paper_trading.get_performance_summary()
                    await self._broadcast_callback({
                        "type": "paper_trading_summary",
                        "data": summary,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

    async def _process_delta_batch(self, updates: list[OddsUpdate], is_emulator: bool = False):
        odds_changes: list[dict] = []
        market_moves: list[dict] = []
        now = datetime.now(timezone.utc)
        ts = now.isoformat()

        for u in updates:
            key = f"{u.event_id}:{u.market}:{u.outcome}:{u.bookmaker}"
            prev = self._last_odds.get(key)
            new_val = u.odd

            if prev is not None and prev != new_val:
                delta_pct = float((new_val - prev) / prev * 100)
                odds_changes.append({
                    "event_id": u.event_id,
                    "market": u.market,
                    "outcome": u.outcome,
                    "bookmaker": u.bookmaker,
                    "odd": float(new_val),
                    "prev_odd": float(prev),
                    "delta_pct": round(delta_pct, 2),
                    "timestamp": ts,
                })
                if abs(delta_pct) > 2.0:
                    market_moves.append({
                        "event_id": u.event_id,
                        "bookmaker": u.bookmaker,
                        "direction": "up" if delta_pct > 0 else "down",
                        "magnitude_pct": round(abs(delta_pct), 1),
                        "timestamp": ts,
                    })
            self._last_odds[key] = new_val

        opp_results = await asyncio.to_thread(self._process_odds_batch, updates)

        now_ms = time.monotonic() * 1000
        if (now_ms - self._last_broadcast_time) < self._batch_ms:
            return
        self._last_broadcast_time = now_ms

        broadcasts = []

        if odds_changes:
            broadcasts.append({"type": "odds_update", "data": odds_changes, "timestamp": ts})

        if market_moves:
            for move in market_moves[:3]:
                broadcasts.append({"type": "market_move", "data": move, "timestamp": ts})

        if opp_results:
            current_ids = {r["event_id"] for r in opp_results}
            new_ids = current_ids - self._known_opps
            removed_ids = self._known_opps - current_ids
            self._known_opps = current_ids

            for opp in opp_results:
                if opp["event_id"] in new_ids:
                    broadcasts.append({"type": "opp_add", "data": opp, "timestamp": ts})

            for rid in removed_ids:
                broadcasts.append({"type": "opp_remove", "data": {"event_id": rid}, "timestamp": ts})

        # Market Truth Layer reconciliation
        truth_messages = await self._reconcile_truth_layer(updates, ts)
        broadcasts.extend(truth_messages)

        # Feed odds into snapshot engine for diff detection
        self._snapshot_engine.record_odds(updates)

        # CLV: track every odds snapshot for closing odds
        for u in updates:
            self._clv_feedback.track_odds_snapshot(
                event_id=u.event_id, market=u.market, outcome=u.outcome,
                bookmaker=u.bookmaker, odd=u.odd,
                is_closing=u.is_closing,
            )

        # Alert engine: evaluate significant moves
        for change in odds_changes:
            alert = self._alert_engine.evaluate_odds_move(
                event_id=change["event_id"],
                outcome=change["outcome"],
                bookmaker=change["bookmaker"],
                old_odd=change["prev_odd"],
                new_odd=change["odd"],
                timestamp=time.time(),
            )
            if alert and self._broadcast_callback:
                broadcasts.append({
                    "type": "alert",
                    "data": alert.to_dict(),
                    "timestamp": ts,
                })

        # Alert engine: evaluate market divergences from truth layer
        if hasattr(self, '_truth_service'):
            pass  # divergences handled in _reconcile_truth_layer

        # Telemetry: record provider activity for every update batch
        for provider_name in {u.bookmaker for u in updates}:
            failed = provider_name in getattr(self, '_last_provider_failure', {})
            try:
                latency = self._truth_service.get_latency_stats(provider_name).get("avg_ms", 0)
            except Exception:
                latency = 0
            self._telemetry.record_provider_event(
                provider=provider_name,
                event="success" if not failed else "reconnected",
                healthy=not failed,
                latency_ms=latency,
            )

        # Data mode broadcast — includes detailed mode + registry status
        mode_summary = self._mode_manager.get_summary()
        registry_summary = self._provider_registry.get_summary() if hasattr(self, '_provider_registry') else {}
        broadcasts.append({
            "type": "data_mode",
            "data": {
                "mode": self._data_mode,
                "reason": self._data_mode_reason,
                "runtime_mode": mode_summary.get("mode"),
                "market_type": mode_summary.get("market_type"),
                "is_simulation": mode_summary.get("is_simulation"),
                "is_hybrid": mode_summary.get("is_hybrid"),
                "is_real_market": mode_summary.get("is_real_market"),
                "real_providers": registry_summary.get("real", 0),
                "active_providers": registry_summary.get("active", 0),
                "provider_count": len(self._providers),
                "clv_open": self._clv_feedback.get_open_count(),
                "clv_closed": self._clv_feedback.get_closed_count(),
                "all_real_providers": registry_summary.get("providers", {}),
            },
            "timestamp": ts,
        })

        # Periodic validation report
        now = time.time()
        if now - self._last_validation_broadcast > self._validation_broadcast_interval:
            self._last_validation_broadcast = now
            report = self._validation.generate(
                clv_records=self._clv_feedback._clv_records,
                open_count=self._clv_feedback.get_open_count(),
            )
            broadcasts.append({
                "type": "validation_report",
                "data": report.to_dict(),
                "timestamp": ts,
            })

        # Close entries that are stale
        stale_hours = 0.5 if self._data_mode == "SIMULATION" else 24.0
        for entry in self._clv_feedback.get_open_entries():
            age_hours = (datetime.now(timezone.utc) - entry.timestamp).total_seconds() / 3600
            if age_hours > stale_hours:
                self._clv_feedback.close_entry(entry.event_id, entry.market, entry.outcome, entry.bookmaker)

        if self._broadcast_callback:
            for msg in broadcasts:
                await self._broadcast_callback(msg)

    async def _reconcile_truth_layer(self, updates: list[OddsUpdate], ts: str) -> list[dict]:
        """Run multi-source reconciliation and emit truth layer events."""
        messages: list[dict] = []

        grouped: dict[str, list[SurveyPoint]] = defaultdict(list)
        for u in updates:
            sp = SurveyPoint(
                event_id=u.event_id,
                market=u.market,
                outcome=u.outcome,
                provider=u.bookmaker,
                odd=float(u.odd),
                timestamp=u.timestamp.timestamp() if hasattr(u.timestamp, "timestamp") else time.time(),
                latency_ms=self._truth_service.get_latency_stats(u.bookmaker).get("avg_ms", 25.0) if u.bookmaker in self._truth_service._latency_samples else 25.0,
            )
            key = f"{u.event_id}:{u.market}:{u.outcome}"
            grouped[key].append(sp)

        for key, points in grouped.items():
            parts = key.split(":", 2)
            eid, market, outcome = parts[0], parts[1], parts[2]

            consensus = self._truth_service.reconcile(points)
            if consensus:
                messages.append({
                    "type": "market_truth_update",
                    "data": consensus.to_dict(),
                    "timestamp": ts,
                })

            for sp in points:
                was_outlier = consensus and sp.provider in consensus.provider_odds and consensus.outlier_count > 0
                self._truth_service.update_reliability(sp.provider, bool(was_outlier))

            sharp = self._truth_service.detect_sharp_move(eid, market, outcome)
            if sharp:
                messages.append({
                    "type": "sharp_move",
                    "data": sharp.to_dict(),
                    "timestamp": ts,
                })

            inconsistency = self._truth_service.detect_inconsistency(points)
            if inconsistency:
                messages.append({
                    "type": "inconsistency",
                    "data": inconsistency.to_dict(),
                    "timestamp": ts,
                })

            latency_arb = self._truth_service.detect_latency_arbitrage(points)
            if latency_arb:
                messages.append({
                    "type": "inconsistency",
                    "data": latency_arb.to_dict(),
                    "timestamp": ts,
                })

        self._broadcast_latency_update(messages, ts)

        return messages

    def _broadcast_latency_update(self, messages: list[dict], ts: str):
        now = time.time()
        if now - self._last_latency_broadcast < self._latency_broadcast_interval:
            return
        self._last_latency_broadcast = now

        heatmap = self._truth_service.get_latency_heatmap()
        ranking = self._truth_service.get_provider_speed_ranking()
        best_source = self._truth_service.get_best_early_signal_source()

        messages.append({
            "type": "latency_update",
            "data": {
                "heatmap": heatmap,
                "provider_ranking": ranking,
                "best_early_source": best_source,
                "timestamp": ts,
            },
            "timestamp": ts,
        })

    def _upsert_event(self, event: OddsEvent) -> Event:
        db = SessionLocal()
        try:
            existing = db.query(Event).filter(Event.event_id == event.event_id).first()
            if existing:
                existing.status = event.status
                existing.updated_at = datetime.now(timezone.utc)
                db.commit()
                return existing
            record = Event(
                event_id=event.event_id,
                sport=event.sport,
                home_team=event.home_team,
                away_team=event.away_team,
                start_time=event.start_time,
                status=event.status,
            )
            db.add(record)
            db.commit()
            return record
        finally:
            db.close()

    def _persist_snapshot(self, snapshot):
        from backend.app.database import MarketSnapshotRecord
        import json
        db = SessionLocal()
        try:
            rec = MarketSnapshotRecord(
                snapshot_id=snapshot.snapshot_id,
                timestamp=datetime.fromtimestamp(snapshot.timestamp, tz=timezone.utc),
                provider_count=snapshot.provider_count,
                total_odds_points=snapshot.total_odds_points,
                total_opportunities=snapshot.total_opportunities,
                event_count=len(snapshot.events),
                snapshot_json=json.dumps({
                    "event_count": len(snapshot.events),
                    "provider_count": snapshot.provider_count,
                    "odds_points": snapshot.total_odds_points,
                    "opportunities": snapshot.total_opportunities,
                    "events": list(snapshot.events.keys()),
                }, default=str),
            )
            db.add(rec)
            db.commit()
        except Exception as e:
            logger.warning("snapshot_persist_failed", error=str(e))
        finally:
            db.close()

    def _process_odds_batch(self, updates: list[OddsUpdate]) -> list[dict]:
        db = SessionLocal()
        try:
            for u in updates:
                record = OddsRecord(
                    event_id=u.event_id,
                    market=u.market,
                    outcome=u.outcome,
                    bookmaker=u.bookmaker,
                    odd=u.odd,
                    timestamp=u.timestamp,
                    is_opening=u.is_opening,
                    is_closing=u.is_closing,
                )
                db.add(record)
            db.commit()
            return self._scan_opportunities(db, updates)
        finally:
            db.close()

    def _scan_opportunities(self, db: Session, updates: list[OddsUpdate]) -> list[dict]:
        from collections import defaultdict
        from decimal import Decimal

        grouped: dict[str, list[OddsUpdate]] = defaultdict(list)
        for u in updates:
            key = f"{u.event_id}:{u.market}"
            grouped[key].append(u)

        results = []
        for key, group in grouped.items():
            event_id = group[0].event_id
            market = group[0].market

            odds_by_outcome: dict[str, dict[str, Decimal]] = defaultdict(dict)
            for u in group:
                odds_by_outcome[u.outcome][u.bookmaker] = u.odd

            best_odds: dict[str, Decimal] = {}
            for outcome, bks in odds_by_outcome.items():
                best_odds[outcome] = max(bks.values())

            if len(best_odds) < 2:
                continue

            odds_dict = {outcome: float(odd) for outcome, odd in best_odds.items()}
            fair_probs = compute_fair_probabilities(odds_dict, method="basic")

            if not fair_probs or not fair_probs.outcomes:
                continue

            for outcome, fair_prob in fair_probs.outcomes.items():
                odd_val = float(best_odds[outcome])
                implied_prob = 1.0 / odd_val if odd_val > 1 else 0
                ev = compute_expected_value(fair_prob, odd_val)

                if ev <= 0:
                    continue

                confidence = compute_confidence(
                    sample_size=100,
                    model_prob=fair_prob,
                    historical_accuracy=0.52,
                )
                grade = classify_value_grade(ev, confidence)
                kelly = compute_kelly(fair_prob, float(odd_val))
                risk_score, risk_level = compute_risk_score(
                    n_bookmakers=len(odds_by_outcome),
                )

                opp = OpportunityRecord(
                    event_id=event_id,
                    market=market,
                    outcome=outcome,
                    bookmaker=max(odds_by_outcome[outcome], key=lambda bk: odds_by_outcome[outcome][bk]),
                    odd=Decimal(str(round(odd_val, 4))),
                    implied_prob=Decimal(str(round(implied_prob, 4))),
                    fair_prob=Decimal(str(round(fair_prob, 4))),
                    ev=Decimal(str(round(ev, 4))),
                    edge_score=Decimal(str(round(ev * 100, 2))),
                    confidence_score=Decimal(str(round(confidence, 4))),
                    kelly_stake=kelly.recommended_stake,
                    value_grade=grade.value if hasattr(grade, "value") else str(grade),
                    risk_level=risk_level.value if hasattr(risk_level, "value") else str(risk_level),
                )
                db.add(opp)

                results.append({
                    "event_id": event_id,
                    "outcome": outcome,
                    "odd": round(odd_val, 2),
                    "ev": round(ev * 100, 2),
                    "confidence": round(confidence, 2),
                    "grade": grade.value if hasattr(grade, "value") else str(grade),
                    "kelly_stake": float(kelly.recommended_stake),
                    "fair_prob": round(fair_prob * 100, 1),
                    "implied_prob": round(implied_prob * 100, 1),
                })

                threshold_ev = 0.02 if self._data_mode == "SIMULATION" else 0.05
                if ev > threshold_ev and confidence > 0.5:
                    alert = AlertRecord(
                        event_id=event_id,
                        alert_type="value_opportunity",
                        severity="high",
                        message=f"EV+ {ev*100:.1f}% on {outcome} ({event_id})",
                        ev_value=Decimal(str(round(ev, 4))),
                    )
                    db.add(alert)

                    # CLV feedback loop: capture entry odds for real CLV calculation
                    best_bookmaker = max(odds_by_outcome[outcome], key=lambda bk: odds_by_outcome[outcome][bk])
                    entry_odd = float(best_odds[outcome])
                    self._clv_feedback.capture_entry(
                        event_id=event_id,
                        market=market,
                        outcome=outcome,
                        bookmaker=best_bookmaker,
                        odd=best_odds[outcome],
                        ev=ev,
                        confidence=confidence,
                    )

                    # Paper trading: open virtual position
                    self._paper_trading.open_position(
                        event_id=event_id,
                        market=market,
                        outcome=outcome,
                        bookmaker=best_bookmaker,
                        entry_odd=entry_odd,
                        entry_ev=ev,
                        confidence=confidence,
                    )

            db.commit()

        return results
