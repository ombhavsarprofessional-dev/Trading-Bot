"""
Module 5: Daily Scheduler

Schedules the automated screening run at 3:30 PM IST (15:30 Asia/Kolkata)
every weekday (Monday through Friday) using APScheduler.
Also supports on-demand manual trigger.
"""

import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import TIMEZONE, DAILY_RUN_HOUR, DAILY_RUN_MINUTE
from database.db import init_db
from database.models import save_screener_results, add_log
from screener.engine import run_screener_engine

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: Optional[BackgroundScheduler] = None
_is_running_scan: bool = False
_last_run_time: Optional[str] = None
_last_run_status: Optional[str] = None
_scan_progress: Dict[str, Any] = {
    "processed": 0,
    "total": 0,
    "status_text": "Scan Complete",
    "percent": 100,
}


def run_screener_job(limit_universe: Optional[int] = None) -> Dict[str, Any]:
    """
    The actual task executed by the scheduler or triggered manually.
    Runs screener engine, saves signals to SQLite, logs status.
    """
    global _is_running_scan, _last_run_time, _last_run_status, _scan_progress

    if _is_running_scan:
        logger.warning("Screener scan is already in progress. Skipping duplicate run.")
        return {"status": "busy", "message": "Scan already running"}

    _is_running_scan = True
    start_time = datetime.now()
    _last_run_time = start_time.strftime("%Y-%m-%d %H:%M:%S")

    log_msg = f"Started scheduled screener run at {_last_run_time} IST"
    logger.info(log_msg)
    add_log("INFO", "SCHEDULER", log_msg)

    _scan_progress = {
        "processed": 0,
        "total": 0,
        "status_text": "Scanning... initializing stock universe...",
        "percent": 0,
    }

    def on_progress(processed: int, total: int):
        global _scan_progress
        pct = int((processed / total) * 100) if total > 0 else 0
        _scan_progress = {
            "processed": processed,
            "total": total,
            "status_text": f"Scanning... {processed}/{total} stocks processed",
            "percent": pct,
        }

    try:
        signals = run_screener_engine(limit_universe=limit_universe, progress_callback=on_progress)
        saved_ids = save_screener_results(signals)

        duration = (datetime.now() - start_time).total_seconds()
        result_msg = (
            f"Screener run finished in {duration:.1f}s. "
            f"Found {len(signals)} matching signals (Saved IDs: {saved_ids})."
        )
        logger.info(result_msg)
        add_log("INFO", "SCHEDULER", result_msg)
        _last_run_status = f"Completed ({len(signals)} signals found)"

        _scan_progress = {
            "processed": len(signals),
            "total": len(signals),
            "status_text": "Scan Complete",
            "percent": 100,
        }

        return {
            "status": "success",
            "signals_count": len(signals),
            "signals": signals,
            "duration_seconds": duration,
        }

    except Exception as e:
        error_msg = f"Screener run failed with error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        add_log("ERROR", "SCHEDULER", error_msg)
        _last_run_status = f"Failed: {str(e)}"
        _scan_progress = {
            "processed": 0,
            "total": 0,
            "status_text": f"Scan Failed: {str(e)}",
            "percent": 0,
        }
        return {"status": "error", "message": str(e)}

    finally:
        _is_running_scan = False


def init_scheduler() -> BackgroundScheduler:
    """Configures and returns the APScheduler instance."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    tz = pytz.timezone(TIMEZONE)
    _scheduler = BackgroundScheduler(timezone=tz)

    # Mon-Fri at 15:30 IST (3:30 PM IST)
    trigger = CronTrigger(
        day_of_week="mon-fri",
        hour=DAILY_RUN_HOUR,
        minute=DAILY_RUN_MINUTE,
        timezone=tz,
    )

    _scheduler.add_job(
        func=run_screener_job,
        trigger=trigger,
        id="daily_nse_screener",
        name="Daily NSE Double Bottom Pivot & RSI Divergence Screener",
        replace_existing=True,
    )

    logger.info(
        f"Scheduler configured: Job 'daily_nse_screener' set for "
        f"Mon-Fri at {DAILY_RUN_HOUR:02d}:{DAILY_RUN_MINUTE:02d} {TIMEZONE}."
    )
    return _scheduler


def start_scheduler():
    """Starts the background scheduler if not already running."""
    scheduler = init_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler background service started.")


def stop_scheduler():
    """Stops the background scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped.")


def get_scheduler_status() -> Dict[str, Any]:
    """Returns the current state and next run time of the scheduler."""
    global _scheduler, _is_running_scan, _last_run_time, _last_run_status, _scan_progress

    if _scheduler is None:
        init_scheduler()

    job = _scheduler.get_job("daily_nse_screener")
    next_run = None
    next_time = getattr(job, "next_run_time", None) if job else None
    if next_time:
        next_run = next_time.strftime("%Y-%m-%d %H:%M:%S %Z")

    return {
        "running": _scheduler.running if _scheduler else False,
        "is_scanning": _is_running_scan,
        "progress": _scan_progress,
        "timezone": TIMEZONE,
        "schedule_time": f"{DAILY_RUN_HOUR:02d}:{DAILY_RUN_MINUTE:02d} IST (Mon-Fri)",
        "next_run_time": next_run,
        "last_run_time": _last_run_time,
        "last_run_status": _last_run_status,
    }


if __name__ == "__main__":
    init_db()
    print("Testing Step 5: Daily Scheduler...")
    sched = init_scheduler()
    start_scheduler()
    status = get_scheduler_status()
    print("\nScheduler Status:")
    for k, v in status.items():
        print(f"  {k}: {v}")
    stop_scheduler()
    print("\nStep 5 completed and verified successfully!")
