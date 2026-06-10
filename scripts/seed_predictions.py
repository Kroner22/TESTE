"""Gera odds sinteticas + detecta oportunidades de value bet para todos os eventos."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['RUNTIME_MODE'] = 'SIMULATION'

from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from backend.app.database import engine, SessionLocal, Base
from backend.app.database import Event, OddsRecord, OpportunityRecord
from backend.domains.value.detector import ValueDetector
from backend.domains.value.models import MarketOdds

BOOKMAKERS = ["Bet365", "Pinnacle", "DraftKings", "FanDuel", "BetMGM"]

SPORT_BASE_ODDS = {
    "soccer":         {"home": (1.8, 2.5), "draw": (3.0, 3.8), "away": (2.8, 4.5)},
    "basketball":     {"home": (1.5, 2.2), "away": (1.7, 2.8)},
    "american_football": {"home": (1.6, 2.4), "away": (1.8, 2.6)},
    "baseball":       {"home": (1.7, 2.2), "away": (1.8, 2.3)},
    "hockey":         {"home": (1.8, 2.4), "away": (2.0, 2.8)},
    "tennis":         {"home": (1.5, 2.0), "away": (1.8, 2.8)},
    "mma":            {"home": (1.6, 2.2), "away": (1.8, 3.0)},
    "boxing":         {"home": (1.5, 2.5), "away": (1.8, 3.5)},
    "rugbyleague":    {"home": (1.7, 2.3), "away": (1.9, 2.5)},
    "cricket":        {"home": (1.6, 2.2), "away": (1.8, 2.6)},
    "aussierules":    {"home": (1.7, 2.3), "away": (1.9, 2.5)},
    "golf":           {"home": (2.0, 3.0), "away": (2.0, 3.0)},
    "handball":       {"home": (1.5, 2.0), "away": (1.7, 2.5)},
    "lacrosse":       {"home": (1.6, 2.2), "away": (1.8, 2.8)},
    "politics":       {"home": (1.3, 2.0), "away": (1.8, 4.0)},
}


def rand_range(lo: float, hi: float) -> Decimal:
    import random
    v = lo + random.random() * (hi - lo)
    return Decimal(str(round(v, 2)))


def generate_odds(event: Event) -> list[OddsRecord]:
    import random
    sport = event.sport
    config = SPORT_BASE_ODDS.get(sport, SPORT_BASE_ODDS["soccer"])
    outcomes = list(config.keys())
    records = []

    # Inject mispricing on ~15% of events for real value opportunities
    misprice = random.random() < 0.15
    misprice_outcome = random.choice(outcomes) if misprice else None

    for bk in random.sample(BOOKMAKERS, random.randint(2, 4)):
        for outcome in outcomes:
            lo, hi = config[outcome]
            odd = rand_range(lo, hi)
            # Deliberately inflate odds for one outcome on mispriced events
            if misprice and outcome == misprice_outcome:
                odd = odd * Decimal(str(round(random.uniform(1.3, 1.8), 2)))
            records.append(OddsRecord(
                event_id=event.event_id,
                market="h2h",
                outcome=outcome,
                bookmaker=bk,
                odd=odd,
                timestamp=datetime.now(timezone.utc),
                is_opening=False,
                is_closing=False,
            ))
    return records


def main():
    import random
    random.seed(42)
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()

    existing = db.query(OddsRecord).count()
    if existing > 0:
        print(f"Ja existem {existing} odds. Pulando geracao.")
    else:
        events = db.query(Event).all()
        print(f"Gerando odds para {len(events)} eventos...")
        all_odds = []
        for ev in events:
            all_odds.extend(generate_odds(ev))
        db.bulk_save_objects(all_odds)
        db.commit()
        print(f"  -> {len(all_odds)} odds geradas")

    # Run value detector
    detector = ValueDetector(min_ev=0.01, min_confidence=0.1)
    events = db.query(Event).all()
    print(f"Detectando oportunidades em {len(events)} eventos...")

    opp_count_before = db.query(OpportunityRecord).count()
    if opp_count_before > 0:
        print(f"Ja existem {opp_count_before} oportunidades. Pulando.")
        db.close()
        return

    total_opps = 0
    for ev in events:
        odds_records = db.query(OddsRecord).filter(
            OddsRecord.event_id == ev.event_id,
            OddsRecord.market == "h2h",
        ).all()

        if not odds_records:
            continue

        outcomes: dict[str, list] = {}
        for o in odds_records:
            outcomes.setdefault(o.outcome, []).append(o.odd)

        best = {outc: max(odds_list) for outc, odds_list in outcomes.items()}
        best_dec = {k: Decimal(str(v)) for k, v in best.items()}
        if "draw" not in best_dec:
            best_dec["draw"] = Decimal("3.50")

        market_odds = MarketOdds(
            event_id=ev.event_id,
            sport=ev.sport,
            home_team=ev.home_team,
            away_team=ev.away_team,
            market="h2h",
            outcomes=best_dec,
        )

        opps = detector.scan([market_odds])
        for opp in opps:
            db.add(OpportunityRecord(
                event_id=opp.event_id,
                market=opp.market,
                outcome=opp.outcome,
                bookmaker="aggregated",
                odd=opp.bookmaker_odd,
                implied_prob=Decimal(str(round(opp.implied_probability, 4))),
                fair_prob=Decimal(str(round(opp.fair_probability, 4))),
                ev=Decimal(str(round(opp.expected_value, 4))),
                edge_score=Decimal(str(round(opp.edge_pct, 2))),
                confidence_score=Decimal(str(round(opp.confidence, 3))),
                kelly_stake=Decimal(str(round(opp.kelly_stake, 4))),
                value_grade=opp.grade.value,
                risk_level=opp.risk_level.value,
                detected_at=datetime.now(timezone.utc),
                is_active=True,
            ))
            total_opps += 1

    db.commit()
    db.close()
    print(f"  -> {total_opps} oportunidades salvas")


if __name__ == "__main__":
    main()
