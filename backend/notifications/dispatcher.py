import logging
from typing import Optional

from backend.app.database import SessionLocal
from backend.app.auth import User
from backend.notifications.telegram import send_message, format_prediction_message

logger = logging.getLogger(__name__)


def dispatch_prediction(pred: dict) -> int:
    sent = 0
    db = SessionLocal()
    try:
        users = db.query(User).filter(
            User.notify_telegram == True,
            User.telegram_chat_id.isnot(None),
            User.plan == "paid",
        ).all()

        grade_order = {"ELITE": 0, "STRONG": 1, "SOLID": 2, "SPECULATIVE": 3, "NOISE": 4}
        pred_grade_val = grade_order.get(pred.get("value_grade", "NOISE"), 99)

        for user in users:
            min_grade_val = grade_order.get(user.notify_min_grade or "SOLID", 2)
            if pred_grade_val > min_grade_val:
                continue

            text = format_prediction_message(pred)

            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(send_message(user.telegram_chat_id, text))
            except RuntimeError:
                asyncio.run(send_message(user.telegram_chat_id, text))
            sent += 1

    finally:
        db.close()

    return sent


def dispatch_top_predictions(limit: int = 5) -> int:
    from backend.app.database import DB_PATH
    import sqlite3

    c = sqlite3.connect(DB_PATH)
    rows = c.execute("""
        SELECT o.event_id, o.outcome, o.odd, o.ev, o.edge_score,
               o.confidence_score, o.value_grade, o.risk_level,
               e.sport, e.home_team, e.away_team
        FROM opportunities o
        JOIN events e ON o.event_id = e.event_id
        WHERE o.is_active = 1
        ORDER BY o.ev DESC
        LIMIT ?
    """, (limit,)).fetchall()
    c.close()

    total = 0
    for row in rows:
        pred = {
            "event_id": row[0], "outcome": row[1], "odd": float(row[2]),
            "ev_pct": round(float(row[3]) * 100, 2), "edge_score": float(row[4]),
            "confidence": float(row[5]), "value_grade": row[6],
            "risk_level": row[7], "sport": row[8],
            "home_team": row[9], "away_team": row[10],
        }
        total += dispatch_prediction(pred)

    return total
