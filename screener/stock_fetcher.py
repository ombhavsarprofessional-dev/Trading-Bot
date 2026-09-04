"""
Module 1: NSE Stock Fetcher + Market Cap Filter

- Downloads the complete equity list from NSE India:
  https://archives.nseindia.com/content/equities/EQUITY_L.csv
- Strips whitespace and filters for Series 'EQ' (Equity shares)
- Appends '.NS' to each symbol for yfinance compatibility
- Filters by Market Cap > 2000 Crore INR (20,000,000,000 INR)
- Batches processing in groups of 50 with 1s delays to avoid rate limits
- Utilizes local SQLite cache to avoid redundant network hits
"""

import io
import time
import sqlite3
import logging
import sys
from pathlib import Path
from typing import List, Dict, Optional

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure stdout handles UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
import pandas as pd
import yfinance as yf

from config import (

    NSE_EQUITY_URL,
    MIN_MARKET_CAP_INR,
    MARKET_CAP_CACHE_HOURS,
    BATCH_SIZE,
    BATCH_DELAY_SECONDS,
    DATABASE_PATH,
    DATA_DIR,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def init_cache_db(db_path=DATABASE_PATH):
    """Ensure market cap cache table exists."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS market_cap_cache (
                symbol TEXT PRIMARY KEY,
                company_name TEXT,
                market_cap REAL,
                updated_at INTEGER
            )
            """
        )
        conn.commit()


def fetch_nse_equity_list() -> pd.DataFrame:
    """
    Downloads the official NSE equity list (EQUITY_L.csv).
    Saves a local copy in data/EQUITY_L.csv as a reliable backup.
    Returns cleaned pandas DataFrame with 'SYMBOL', 'NAME OF COMPANY', and 'SYMBOL_NS'.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    local_csv = DATA_DIR / "EQUITY_L.csv"

    try:
        logger.info(f"Downloading NSE equity list from {NSE_EQUITY_URL}...")
        response = requests.get(NSE_EQUITY_URL, headers=headers, timeout=15)
        response.raise_for_status()
        csv_text = response.text
        # Save to local cache
        with open(local_csv, "w", encoding="utf-8") as f:
            f.write(csv_text)
        logger.info(f"Successfully downloaded and saved to {local_csv}")
    except Exception as e:
        logger.warning(f"Failed to fetch live CSV from NSE: {e}. Checking local cache...")
        if local_csv.exists():
            logger.info("Using cached local EQUITY_L.csv")
            with open(local_csv, "r", encoding="utf-8") as f:
                csv_text = f.read()
        else:
            raise RuntimeError(f"Unable to download NSE equity list and no local cache found: {e}")

    df = pd.read_csv(io.StringIO(csv_text))
    # Strip column names
    df.columns = df.columns.str.strip()

    # Filter for Series 'EQ' (standard equity shares)
    if "SERIES" in df.columns:
        df["SERIES"] = df["SERIES"].astype(str).str.strip()
        df = df[df["SERIES"] == "EQ"].copy()

    df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip()
    df["NAME OF COMPANY"] = df["NAME OF COMPANY"].astype(str).str.strip()
    df["SYMBOL_NS"] = df["SYMBOL"] + ".NS"

    logger.info(f"Loaded {len(df)} equity stocks from NSE list.")
    return df


def get_cached_market_caps(db_path=DATABASE_PATH, max_age_hours=MARKET_CAP_CACHE_HOURS) -> Dict[str, Dict]:
    """Retrieve non-expired market caps from SQLite cache."""
    init_cache_db(db_path)
    cached = {}
    current_ts = int(time.time())
    cutoff_ts = current_ts - (max_age_hours * 3600)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT symbol, company_name, market_cap, updated_at 
            FROM market_cap_cache 
            WHERE updated_at >= ?
            """,
            (cutoff_ts,),
        )
        for row in cursor.fetchall():
            cached[row[0]] = {
                "symbol": row[0],
                "company_name": row[1],
                "market_cap": row[2],
                "updated_at": row[3],
            }
    return cached


def save_market_caps_to_cache(records: List[Dict], db_path=DATABASE_PATH):
    """Save/update fetched market caps in SQLite cache."""
    if not records:
        return
    init_cache_db(db_path)
    current_ts = int(time.time())
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.executemany(
            """
            INSERT INTO market_cap_cache (symbol, company_name, market_cap, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                company_name=excluded.company_name,
                market_cap=excluded.market_cap,
                updated_at=excluded.updated_at
            """,
            [(r["symbol"], r["company_name"], r["market_cap"], current_ts) for r in records],
        )
        conn.commit()


def fetch_single_ticker_market_cap(symbol: str) -> Optional[float]:
    """Fetch market cap for a single ticker using fast_info."""
    try:
        ticker = yf.Ticker(symbol)
        mcap = getattr(ticker.fast_info, "market_cap", None)
        if mcap is not None and mcap > 0:
            return float(mcap)
    except Exception:
        pass
    return None


def filter_stocks_by_market_cap(
    equity_df: Optional[pd.DataFrame] = None,
    min_mcap_inr: float = MIN_MARKET_CAP_INR,
    batch_size: int = BATCH_SIZE,
    batch_delay: float = BATCH_DELAY_SECONDS,
    limit: Optional[int] = None,
    use_cache: bool = True,
    progress_callback=None,
) -> List[Dict]:
    """
    Filters NSE stocks with Market Cap > min_mcap_inr (default 2000 Cr INR).
    Processes in batches of batch_size with batch_delay seconds delay.
    Returns list of dicts:
      [{'symbol': 'INFY.NS', 'raw_symbol': 'INFY', 'company_name': 'Infosys Limited', 'market_cap': 4.5e12}]
    """
    if equity_df is None:
        equity_df = fetch_nse_equity_list()

    if limit is not None and limit > 0:
        equity_df = equity_df.head(limit).copy()

    cached_data = get_cached_market_caps() if use_cache else {}
    to_fetch = []
    qualified_stocks = []

    for _, row in equity_df.iterrows():
        symbol_ns = row["SYMBOL_NS"]
        company = row["NAME OF COMPANY"]
        raw_symbol = row["SYMBOL"]

        if symbol_ns in cached_data:
            mcap = cached_data[symbol_ns]["market_cap"]
            if mcap and mcap >= min_mcap_inr:
                qualified_stocks.append(
                    {
                        "symbol": symbol_ns,
                        "raw_symbol": raw_symbol,
                        "company_name": company,
                        "market_cap": mcap,
                        "cached": True,
                    }
                )
        else:
            to_fetch.append({"symbol": symbol_ns, "raw_symbol": raw_symbol, "company_name": company})

    logger.info(
        f"Market Cap Filter: {len(cached_data)} cached, {len(qualified_stocks)} cached qualified, "
        f"{len(to_fetch)} remaining to fetch."
    )

    # Process remaining in batches
    total_to_fetch = len(to_fetch)
    for i in range(0, total_to_fetch, batch_size):
        batch = to_fetch[i : i + batch_size]
        batch_results = []

        logger.info(
            f"Processing market cap batch {i // batch_size + 1}/{(total_to_fetch + batch_size - 1) // batch_size} "
            f"({len(batch)} symbols)..."
        )

        for item in batch:
            sym = item["symbol"]
            mcap = fetch_single_ticker_market_cap(sym)
            if mcap is not None:
                batch_results.append(
                    {
                        "symbol": sym,
                        "raw_symbol": item["raw_symbol"],
                        "company_name": item["company_name"],
                        "market_cap": mcap,
                    }
                )
                if mcap >= min_mcap_inr:
                    qualified_stocks.append(
                        {
                            "symbol": sym,
                            "raw_symbol": item["raw_symbol"],
                            "company_name": item["company_name"],
                            "market_cap": mcap,
                            "cached": False,
                        }
                    )

        # Save batch results to SQLite cache
        if batch_results and use_cache:
            save_market_caps_to_cache(batch_results)

        if progress_callback:
            progress_callback(min(i + batch_size, total_to_fetch), total_to_fetch)

        # Sleep between batches if more remain
        if i + batch_size < total_to_fetch and batch_delay > 0:
            time.sleep(batch_delay)

    logger.info(
        f"Completed Market Cap Filtering. Total {len(qualified_stocks)} stocks > INR {min_mcap_inr / 1e7:,.0f} Cr."
    )
    return qualified_stocks


if __name__ == "__main__":
    print("Testing Step 1: NSE Stock Fetcher & Market Cap Filter...")
    # Fetch first 15 stocks as a rapid verification test
    stocks = filter_stocks_by_market_cap(limit=15, batch_size=5, batch_delay=0.5)
    print(f"\nFound {len(stocks)} stocks qualifying > INR 2000 Cr in test sample:")
    for s in stocks:
        cr_val = s["market_cap"] / 1e7
        print(f"  - {s['symbol']} ({s['company_name']}): INR {cr_val:,.2f} Cr")

