"""
Run Today's Screener Immediately & Launch Web Dashboard.

Features:
1. Runs full screener immediately (no waiting for 3:30 PM IST).
2. Uses today's latest daily candle data across NSE + BSE universe (> ₹2000 Cr).
3. Saves qualifying signals to SQLite database.
4. Prints clean summary table in terminal:
   RANK | SYMBOL | EXCHANGE | COMPANY | PRICE | ENTRY | TARGET | SL | RSI | SCORE
5. Automatically starts Flask server and opens http://localhost:5000 in browser.
"""

import sys
import os
import argparse
import logging
import threading
import time
import webbrowser
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Ensure stdout handles UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from database.db import init_db
from database.models import save_screener_results, add_log
from screener.engine import run_screener_engine
from backend.app import app

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("RUN_TODAY")


def print_signals_table(signals):
    """Prints a clean, structured summary table of qualifying signals."""
    print("\n" + "=" * 115)
    print(f"             TODAY'S SCREENING RESULTS: {len(signals)} QUALIFIED SWING SIGNALS FOUND")
    print("=" * 115)

    if not signals:
        print("\nNo stocks satisfied all 3 strict criteria in today's scan.")
        print("Criteria: Trad S1/S2 gap < 1.5%, Fib S1/S2 within 2.5%, RSI Bullish Divergence in last 10 bars.\n")
        print("=" * 115 + "\n")
        return

    header = (
        f"{'RANK':<5} | {'SYMBOL':<14} | {'EXCHANGE':<8} | {'COMPANY':<30} | "
        f"{'PRICE':<10} | {'ENTRY':<10} | {'TARGET':<10} | {'SL':<10} | {'RSI':<6} | {'SCORE':<5}"
    )
    print(header)
    print("-" * len(header))

    for idx, s in enumerate(signals, 1):
        sym = s["symbol"]
        exch = s.get("exchange", "NSE")
        comp = s.get("company_name", "")[:30]
        price = f"₹{s['current_price']:.2f}"
        entry = f"₹{s['suggested_entry']:.2f}"
        target = f"₹{s['target_price']:.2f}"
        sl = f"₹{s['stop_loss']:.2f}"
        rsi_val = s.get("rsi_value")
        rsi_str = f"{rsi_val:.1f}" if rsi_val is not None else "--"
        score_str = f"{s['score']}/10"

        print(
            f"{idx:<5} | {sym:<14} | {exch:<8} | {comp:<30} | "
            f"{price:<10} | {entry:<10} | {target:<10} | {sl:<10} | {rsi_str:<6} | {score_str:<5}"
        )

    print("-" * len(header) + "\n")


def open_browser_delayed(url: str, delay_seconds: float = 1.2):
    """Opens the local dashboard URL in the default browser after server initialization."""
    def _open():
        time.sleep(delay_seconds)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_open, daemon=True).start()


def main():
    parser = argparse.ArgumentParser(description="Run Today's Indian Equities Screener (NSE + BSE)")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of stocks to screen (e.g. 50 for quick test)",
    )
    parser.add_argument(
        "--no-server",
        action="store_true",
        help="Run screener and print terminal table without launching Flask server",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port to run Flask dashboard server on (default 5000)",
    )
    args = parser.parse_args()

    # 1. Initialize DB and apply migrations
    init_db()

    print("\n" + "=" * 115)
    print("           INDIAN EQUITIES SWING SCREENER (NSE + BSE) - IMMEDIATE RUN")
    print("   Double Bottom Pivot Support Confluence (Trad + Fib) & RSI Bullish Divergence")
    print("=" * 115 + "\n")

    # 2. Run Screener Engine
    logger.info(f"Running today's screener on multi-exchange universe (limit={args.limit})...")
    signals = run_screener_engine(limit_universe=args.limit)

    # 3. Print Clean Summary Table
    print_signals_table(signals)

    # 4. Save results to database
    if signals:
        saved_ids = save_screener_results(signals)
        add_log("INFO", "RUN_TODAY", f"Saved {len(saved_ids)} screener signals to SQLite.")
        print(f"[+] Successfully saved {len(saved_ids)} signals to SQLite database.\n")
    else:
        add_log("INFO", "RUN_TODAY", "Today's scan completed with 0 qualifying signals.")

    # 5. Start Flask Server and Open Dashboard
    if not args.no_server:
        dashboard_url = f"http://localhost:{args.port}"
        print("=" * 115)
        print(f"[*] Starting Local Dashboard Server at: {dashboard_url}")
        print("[*] Default Credentials: username: admin | password: trader2026")
        print("=" * 115 + "\n")

        # Automatically open browser
        open_browser_delayed(dashboard_url, delay_seconds=1.0)

        # Run Flask server
        app.run(host="0.0.0.0", port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
