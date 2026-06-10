"""Gera paper trades simulados a partir das oportunidades existentes."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['RUNTIME_MODE'] = 'SIMULATION'

import random
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import func
from backend.app.database import SessionLocal, PaperTradeRecord, OpportunityRecord, Event

random.seed(99)


def generate_entry_price(base_odd: Decimal) -> Decimal:
    jitter = Decimal(str(round(random.uniform(-0.05, 0.05), 4)))
    return max(Decimal("1.1"), base_odd + jitter)


def generate_exit_price(entry_odd: Decimal, is_winner: bool) -> Decimal:
    if is_winner:
        return entry_odd * Decimal(str(round(random.uniform(1.0, 1.15), 4)))
    else:
        return entry_odd * Decimal(str(round(random.uniform(0.85, 0.99), 4)))


def main():
    db = SessionLocal()
    existing = db.query(PaperTradeRecord).count()
    if existing > 0:
        print(f"Ja existem {existing} paper trades. Pulando.")
        db.close()
        return

    opps = db.query(OpportunityRecord).all()
    events = {e.event_id: e for e in db.query(Event).all()}
    print(f"Gerando paper trades para {len(opps)} oportunidades...")

    trades = []
    for opp in opps:
        ev = events.get(opp.event_id)
        if not ev:
            continue

        # ~60% win rate for higher-grade predictions
        grade_win_rate = {
            "ELITE": 0.75, "STRONG": 0.65, "SOLID": 0.58,
            "SPECULATIVE": 0.48, "NOISE": 0.40,
        }
        win_rate = grade_win_rate.get(opp.value_grade, 0.50)
        is_winner = random.random() < win_rate

        entry_odd = generate_entry_price(opp.odd)
        entry_time = ev.start_time - timedelta(hours=random.uniform(1, 48))
        exit_time = ev.start_time + timedelta(hours=random.uniform(0.5, 4))
        exit_odd = generate_exit_price(entry_odd, is_winner)

        stake = Decimal(str(round(random.uniform(20, 200), 2)))
        pnl = stake * (exit_odd - entry_odd) / entry_odd
        pnl_pct = (exit_odd - entry_odd) / entry_odd * 100

        trades.append(PaperTradeRecord(
            position_id=f"pt_{uuid.uuid4().hex[:12]}",
            event_id=opp.event_id,
            market=opp.market or "h2h",
            outcome=opp.outcome,
            bookmaker="aggregated",
            entry_odd=entry_odd,
            entry_ev=opp.ev,
            stake=stake,
            entry_timestamp=entry_time,
            is_open=False,
            exit_odd=exit_odd,
            exit_timestamp=exit_time,
            pnl=pnl,
            pnl_pct=pnl_pct,
            confidence=opp.confidence_score,
            kelly_fraction=Decimal("0.25"),
        ))

    db.bulk_save_objects(trades)
    db.commit()

    total = db.query(PaperTradeRecord).count()
    winners = db.query(PaperTradeRecord).filter(
        PaperTradeRecord.pnl > 0).count()
    total_pnl = db.query(func.sum(PaperTradeRecord.pnl)).filter(
        PaperTradeRecord.pnl.isnot(None)
    ).scalar() or 0

    db.close()
    print(f"  -> {total} trades gerados ({winners} vencedores)")
    print(f"  -> P&L total: ${float(total_pnl):.2f}")
    print(f"  -> Win rate: {winners/total*100:.1f}%")


if __name__ == "__main__":
    main()
