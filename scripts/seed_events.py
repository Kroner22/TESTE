"""Popula a tabela de eventos com dados sinteticos para os 15 esportes suportados."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['RUNTIME_MODE'] = 'SIMULATION'

import random
from datetime import datetime, timedelta, timezone
from backend.app.database import engine, SessionLocal, Base, Event
from backend.app.auth import User

random.seed(42)

SPORTS = [
    "soccer", "basketball", "american_football", "baseball", "hockey",
    "tennis", "mma", "boxing", "rugbyleague", "cricket", "aussierules",
    "golf", "handball", "lacrosse", "politics",
]

TEAMS = {
    "soccer":         [("Man City", "Liverpool"), ("Real Madrid", "Barcelona"), ("Bayern", "Dortmund"), ("PSG", "Marseille"), ("Juventus", "Milan")],
    "basketball":     [("Lakers", "Celtics"), ("Warriors", "Nuggets"), ("Bucks", "Heat"), ("Suns", "Thunder")],
    "american_football": [("Chiefs", "49ers"), ("Ravens", "Bengals"), ("Eagles", "Cowboys"), ("Bills", "Dolphins")],
    "baseball":       [("Yankees", "RedSox"), ("Dodgers", "Giants"), ("Astros", "Rangers")],
    "hockey":         [("MapleLeafs", "Canadiens"), ("Bruins", "Panthers"), ("Oilers", "Flames")],
    "tennis":         [("Alcaraz", "Sinner"), ("Djokovic", "Nadal"), ("Federer", "Murray")],
    "mma":            [("McGregor", "Chandler"), ("Adesanya", "Pereira"), ("Ngannou", "Fury")],
    "boxing":         [("Tyson", "Lewis"), ("Ali", "Frazier"), ("Mayweather", "Pacquiao")],
    "rugbyleague":    [("Roosters", "Storm"), ("Rabbitohs", "Panthers"), ("Broncos", "Cowboys")],
    "cricket":        [("India", "Australia"), ("England", "Pakistan"), ("NZ", "SAfrica")],
    "aussierules":    [("Cats", "Magpies"), ("Lions", "Blues"), ("Dockers", "Eagles")],
    "golf":           [("Scheffler", "Rahm"), ("McIlroy", "Koepka"), ("Spieth", "Thomas")],
    "handball":       [("Barcelona", "PSG"), ("Aalborg", "Kiel"), ("Veszprem", "Barca")],
    "lacrosse":       [("Whipsnakes", "Archers"), ("Atlas", "Redwoods"), ("Chaos", "Waterdogs")],
    "politics":       [("Democrat", "Republican"), ("Labour", "Conservative"), ("Lula", "Bolsonaro")],
}


def main():
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()

    existing = db.query(Event).count()
    if existing > 0:
        print(f"Ja existem {existing} eventos. Pulando geracao.")
        db.close()
        return

    events = []
    now = datetime.now(timezone.utc)
    for sport in SPORTS:
        pairs = TEAMS[sport]
        for home, away in pairs:
            start = now + timedelta(hours=random.uniform(2, 72))
            events.append(Event(
                event_id=f"{sport}_{home.lower()}_{away.lower()}_{random.randint(100,999)}",
                sport=sport,
                home_team=home,
                away_team=away,
                start_time=start,
                status="scheduled",
            ))

    db.bulk_save_objects(events)
    db.commit()
    db.close()
    print(f"  -> {len(events)} eventos criados ({len(SPORTS)} esportes)")


if __name__ == "__main__":
    main()
