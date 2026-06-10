from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from typing import Optional

from ..log_config import get_logger
from ..monitoring.metrics import scan_total, scan_duration_seconds, worker_active

logger = get_logger(__name__)

_running = False
_task: Optional[asyncio.Task] = None


async def run_scanner(
    interval: float = 5.0,
    total_stake: Decimal = Decimal("100"),
    min_profit_pct: float = 0.005,
    callback=None,
) -> None:
    """Periodically scan for value + arb opportunities."""
    global _running
    _running = True
    worker_active.labels(worker_type="scanner").set(1)

    from ...domains.value.detector import ValueDetector
    from ...domains.arbitrage.engine import ArbitrageEngine, EngineConfig
    from ...domains.arbitrage.models import ArbFilter

    detector = ValueDetector()
    engine = ArbitrageEngine(
        config=EngineConfig(
            filter_config=ArbFilter(min_profit_pct=Decimal(str(min_profit_pct))),
        )
    )

    logger.info("scanner_started", interval=interval)

    while _running:
        cycle_start = time.monotonic()
        try:
            value_ops = detector.scan([])
            scan_total.labels(scanner_type="value", status="success").inc()

            arb_snapshot = engine.snapshot()
            scan_total.labels(scanner_type="arb", status="success").inc()

            elapsed = time.monotonic() - cycle_start
            scan_duration_seconds.labels(scanner_type="full").observe(elapsed)

            if callback:
                await callback({
                    "type": "scan_result",
                    "timestamp": time.time(),
                    "duration_ms": round(elapsed * 1000, 1),
                    "value_opportunities": len(value_ops),
                    "arb_opportunities": arb_snapshot.filtered_count,
                })

        except Exception as e:
            elapsed = time.monotonic() - cycle_start
            scan_total.labels(scanner_type="value", status="error").inc()
            scan_total.labels(scanner_type="arb", status="error").inc()
            logger.error("scanner_error", error=str(e), elapsed_ms=round(elapsed * 1000, 1))

        await asyncio.sleep(max(0.1, interval - (time.monotonic() - cycle_start)))

    worker_active.labels(worker_type="scanner").set(0)
    logger.info("scanner_stopped")


async def start_scanner(
    interval: float = 5.0,
    total_stake: Decimal = Decimal("100"),
    min_profit_pct: float = 0.005,
    callback=None,
) -> None:
    global _task
    if _task is not None and not _task.done():
        logger.warning("scanner_already_running")
        return
    _task = asyncio.create_task(
        run_scanner(interval, total_stake, min_profit_pct, callback)
    )


async def stop_scanner() -> None:
    global _running, _task
    _running = False
    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
