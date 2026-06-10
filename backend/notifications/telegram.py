import logging
from typing import Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
BOT_TOKEN: Optional[str] = None


def get_bot_token() -> Optional[str]:
    global BOT_TOKEN
    if BOT_TOKEN is None:
        import os
        BOT_TOKEN = os.getenv(BOT_TOKEN_ENV)
    return BOT_TOKEN


def build_link_url(bot_username: str, chat_id: str, payload: str = "") -> str:
    return f"https://t.me/{bot_username}?start={quote(payload or chat_id)}"


async def send_message(chat_id: str, text: str) -> bool:
    token = get_bot_token()
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set, skipping message")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            })
            if resp.status_code != 200:
                logger.error("telegram send failed: %s %s", resp.status_code, resp.text)
                return False
            return True
    except Exception as e:
        logger.error("telegram send error: %s", e)
        return False


def format_prediction_message(pred: dict) -> str:
    grade_emoji = {
        "ELITE": "🔥", "STRONG": "💪", "SOLID": "✅",
        "SPECULATIVE": "📊", "NOISE": "ℹ️",
    }
    emoji = grade_emoji.get(pred["value_grade"], "📊")
    return (
        f"{emoji} <b>Value Bet Detectada</b>\n"
        f"└ {pred['home_team']} vs {pred['away_team']}\n"
        f"├ Esporte: {pred['sport']}\n"
        f"├ Mercado: {pred['outcome']} @ {pred['odd']}\n"
        f"├ EV: +{pred['ev_pct']}%\n"
        f"├ Confianca: {pred['confidence']:.0%}\n"
        f"├ Grade: {pred['value_grade']}\n"
        f"└ Risco: {pred['risk_level']}"
    )
