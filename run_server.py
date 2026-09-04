"""
Main Server Runner for NSE Swing Trading Bot.

Initializes:
1. SQLite Database & Schema
2. APScheduler background service for 3:30 PM IST daily run
3. Flask REST API Server on port 5000
"""

import sys
import logging
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from database.db import init_db
from scheduler.daily_scheduler import start_scheduler, get_scheduler_status
from backend.app import app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
)
logger = logging.getLogger("RUN_SERVER")


def main():
    print("=" * 70)
    print("       NSE SWING TRADING BOT & SCREENER SERVER")
    print("=" * 70)

    # 1. Initialize SQLite Database
    logger.info("Initializing SQLite database...")
    init_db()

    # 2. Start APScheduler Background Service
    logger.info("Starting APScheduler for daily 3:30 PM IST runs...")
    start_scheduler()
    status = get_scheduler_status()
    print(f"\n[*] Scheduler Schedule: {status['schedule_time']}")
    print(f"[*] Next Scheduled Run: {status['next_run_time']}")
    print("[*] Web Dashboard URL:   http://127.0.0.1:5000\n")
    print("[*] Default Login: username: admin | password: trader2026")
    print("=" * 70)

    # 3. Start Flask API server
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
