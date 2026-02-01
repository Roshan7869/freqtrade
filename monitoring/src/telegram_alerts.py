"""
Monitoring - Telegram Alerts
============================
Sends alerts to Telegram for trades and signals.
"""

import logging
import os
import sys

# sys.path handled by config.py
import requests
from shared.messaging import EventConsumer
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TelegramAlerts")


def send_telegram(message: str):
    if not Config.TELEGRAM_BOT_TOKEN or not Config.TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured")
        return

    url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(
            url,
            json={
                "chat_id": Config.TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
            },
        )
    except Exception as e:
        logger.error(f"Telegram error: {e}")


def on_event(event: dict):
    """Send alerts for trade events."""
    if "action" in event and "symbol" in event:
        msg = f"🔔 <b>{event['action']}</b> {event['symbol']}"
        if "price" in event:
            msg += f" @ {event['price']}"
        send_telegram(msg)
        logger.info(f"Alert sent: {msg}")


def main():
    consumer = EventConsumer(
        ["trade.fill", "signal.whale"], "monitoring-group", Config.KAFKA_BOOTSTRAP
    )

    logger.info("Starting Telegram Alerts...")
    consumer.consume(on_event)


if __name__ == "__main__":
    main()
