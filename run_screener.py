"""
CLI Screener Runner: Run the screener on-demand from the terminal.

Usage:
  python run_screener.py                 # Run default screener
  python run_screener.py --limit 50      # Quick test scan on 50 stocks
  python run_screener.py --no-save       # Scan without saving to SQLite
"""

import sys
import argparse
import logging
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from database.db import init_db
from database.models import save_screener_results, add_log
from screener.engine import run_screener_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CLI_SCREENER")


def main():
    parser = argparse.ArgumentParser(description="NSE Swing Trading Screener CLI")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of stocks to scan (e.g. 50 for quick test)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not save generated signals to SQLite database",
    )
    args = parser.parse_args()

    init_db()

    print("\n" + "=" * 80)
    print("           NSE SWING TRADING SCREENER (CLI MODE)")
    print("  Double Bottom Pivot Confluence (Trad + Fib) & RSI Bullish Divergence")
    print("=" * 80 + "\n")

    logger.info(f"Initiating screener (limit={args.limit})...")
    signals = run_screener_engine(limit_universe=args.limit)

    print("\n" + "-" * 80)
    print(f"SCREENING RESULTS: {len(signals)} QUALIFIED SIGNALS FOUND")
    print("-" * 80)

    if not signals:
        print("No stocks satisfied all 3 strict criteria in this scan.")
        print("Criteria: Trad S1/S2 gap < 1.5%, Fib S1/S2 within 1%, RSI Bullish Divergence in last 10 bars.\n")
        return

    # Print clean table
    header = (
        f"{'Score':<6} {'Symbol':<14} {'Entry (INR)':<13} {'Target (+15%)':<14} "
        f"{'Stop Loss':<12} {'R:R':<6} {'RSI':<6} {'Market Cap (Cr)':<15}"
    )
    print(header)
    print("-" * len(header))

    for s in signals:
        print(
            f"{s['score']:<6} {s['symbol']:<14} {s['suggested_entry']:<13.2f} "
            f"{s['target_price']:<14.2f} {s['stop_loss']:<12.2f} "
            f"{s['risk_reward_ratio']:<6.1f} {s['rsi_value'] or 0:<6.1f} "
            f"{s['market_cap_cr']:<15,.1f}"
        )
    print("-" * len(header) + "\n")

    if not args.no_save:
        saved_ids = save_screener_results(signals)
        add_log("INFO", "CLI", f"CLI run completed: {len(signals)} signals saved (IDs: {saved_ids})")
        print(f"Saved {len(saved_ids)} signals to SQLite database.")


if __name__ == "__main__":
    main()
