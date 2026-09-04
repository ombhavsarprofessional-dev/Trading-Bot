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
import json
import re
import difflib
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
    BSE_EQUITY_URL,
    BSE_BACKUP_URL,
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
    if "ISIN NUMBER" in df.columns:
        df["ISIN"] = df["ISIN NUMBER"].astype(str).str.strip()
    elif "ISIN" in df.columns:
        df["ISIN"] = df["ISIN"].astype(str).str.strip()
    else:
        df["ISIN"] = ""

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
        isin = str(row.get("ISIN", "")).strip()

        if symbol_ns in cached_data:
            mcap = cached_data[symbol_ns]["market_cap"]
            if mcap and mcap >= min_mcap_inr:
                qualified_stocks.append(
                    {
                        "symbol": symbol_ns,
                        "raw_symbol": raw_symbol,
                        "company_name": company,
                        "market_cap": mcap,
                        "isin": isin,
                        "exchange": "NSE",
                        "dual_listed": False,
                        "cached": True,
                    }
                )
        else:
            to_fetch.append({"symbol": symbol_ns, "raw_symbol": raw_symbol, "company_name": company, "isin": isin})

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
                            "isin": item.get("isin", ""),
                            "exchange": "NSE",
                            "dual_listed": False,
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


def fetch_nse_stocks(
    equity_df: Optional[pd.DataFrame] = None,
    min_mcap_inr: float = MIN_MARKET_CAP_INR,
    batch_size: int = BATCH_SIZE,
    batch_delay: float = BATCH_DELAY_SECONDS,
    limit: Optional[int] = None,
    use_cache: bool = True,
    progress_callback=None,
) -> List[Dict]:
    """
    Fetches qualifying NSE stocks tagged with exchange='NSE'.
    """
    stocks = filter_stocks_by_market_cap(
        equity_df=equity_df,
        min_mcap_inr=min_mcap_inr,
        batch_size=batch_size,
        batch_delay=batch_delay,
        limit=limit,
        use_cache=use_cache,
        progress_callback=progress_callback,
    )
    for s in stocks:
        s["exchange"] = "NSE"
        s.setdefault("dual_listed", False)
    return stocks


def fetch_bse_stocks(
    min_mcap_inr: float = MIN_MARKET_CAP_INR,
    limit: Optional[int] = None,
    min_market_cap_cr: Optional[float] = None,
) -> List[Dict]:
    """
    Downloads BSE equity list and returns list of dicts with:
    - symbol: e.g. '500325.BO'
    - company_name: Name of issuer
    - exchange: 'BSE'
    - market_cap: INR market cap (> ₹2,000 Crore)
    - isin, raw_symbol, scrip_id
    Falls back gracefully to local backup or secondary URL if blocked.
    """
    if min_market_cap_cr is not None:
        min_mcap_inr = min_market_cap_cr * 1e7
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.bseindia.com/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.5",
    }
    local_bse_json = DATA_DIR / "BSE_EQUITY.json"
    data = None

    try:
        logger.info(f"Downloading BSE equity list from {BSE_EQUITY_URL}...")
        resp = requests.get(BSE_EQUITY_URL, headers=headers, timeout=15)
        resp.raise_for_status()
        raw_json = resp.json()
        if isinstance(raw_json, list) and len(raw_json) > 0:
            data = raw_json
            # Save local backup
            with open(local_bse_json, "w", encoding="utf-8") as f:
                json.dump(data, f)
            logger.info(f"Successfully downloaded and cached {len(data)} BSE records to {local_bse_json}")
    except Exception as e:
        logger.warning(f"BSE API request failed: {e}. Checking local cache or fallback...")
        if local_bse_json.exists():
            logger.info(f"Loading BSE data from local backup {local_bse_json}")
            try:
                with open(local_bse_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as read_err:
                logger.error(f"Error reading local BSE cache: {read_err}")

        if not data:
            try:
                logger.info(f"Attempting fallback to {BSE_BACKUP_URL}...")
                resp = requests.get(BSE_BACKUP_URL, headers=headers, timeout=15)
                # Parse HTML table if available
                dfs = pd.read_html(io.StringIO(resp.text))
                if dfs and not dfs[0].empty:
                    df = dfs[0]
                    logger.info(f"Parsed {len(df)} rows from fallback HTML table.")
            except Exception as fb_err:
                logger.error(f"Fallback request also failed: {fb_err}")

    if not data:
        logger.error("Unable to load BSE equity list from API or local cache.")
        return []

    min_mcap_cr = min_mcap_inr / 1e7
    qualified_bse = []

    for item in data:
        try:
            status = str(item.get("Status", "")).strip().lower()
            segment = str(item.get("Segment", "")).strip().lower()
            if status != "active" or (segment and segment != "equity"):
                continue

            scrip_cd = str(item.get("SCRIP_CD", "")).strip()
            if not scrip_cd:
                continue

            company_name = str(item.get("Issuer_Name") or item.get("Scrip_Name") or "").strip()
            scrip_id = str(item.get("scrip_id", "")).strip()
            isin = str(item.get("ISIN_NUMBER", "")).strip().upper()

            # Mktcap in BSE API is in Crore INR
            mcap_val = item.get("Mktcap")
            if mcap_val is None:
                continue
            mcap_cr = float(mcap_val)
            if mcap_cr < min_mcap_cr:
                continue

            mcap_inr = mcap_cr * 1e7
            symbol = f"{scrip_cd}.BO"

            qualified_bse.append({
                "symbol": symbol,
                "raw_symbol": scrip_cd,
                "scrip_id": scrip_id,
                "company_name": company_name,
                "market_cap": mcap_inr,
                "isin": isin,
                "exchange": "BSE",
                "dual_listed": False,
                "cached": True,
            })
        except Exception:
            continue

    logger.info(f"Loaded {len(qualified_bse)} BSE stocks with Market Cap > INR {min_mcap_cr:,.0f} Cr.")
    if limit is not None and limit > 0:
        qualified_bse = qualified_bse[:limit]
    return qualified_bse


def normalize_company_name(name: str) -> str:
    """
    Normalizes company name for multi-exchange fuzzy comparison:
    - Lowercase
    - Removes punctuation and parenthesis content
    - Strips corporate suffixes (limited, ltd, pvt, corp, holdings, etc.)
    """
    if not name:
        return ""
    s = name.lower()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    words = s.split()

    suffixes = {
        "limited", "ltd", "private", "pvt", "corp", "corporation",
        "co", "company"
    }

    # Trim known legal/corporate entity suffixes from end of word sequence
    changed = True
    while changed and words:
        changed = False
        if words[-1] in suffixes:
            words.pop()
            changed = True

    return " ".join(words)


def fetch_all_stocks(
    limit: Optional[int] = None,
    use_cache: bool = True,
    progress_callback=None,
    limit_nse: Optional[int] = None,
    limit_bse: Optional[int] = None,
    min_market_cap_cr: Optional[float] = None,
    min_mcap_inr: float = MIN_MARKET_CAP_INR,
) -> List[Dict]:
    """
    Combines NSE and BSE stocks (> ₹2000 Cr).
    Deduplicates: If a company appears in both NSE and BSE, keeps the NSE version
    (better liquidity) and tags with dual_listed=True.
    Returns combined list tagged with exchange field ('NSE' or 'BSE').
    """
    if min_market_cap_cr is not None:
        min_mcap_inr = min_market_cap_cr * 1e7

    effective_limit_nse = limit_nse if limit_nse is not None else limit
    effective_limit_bse = limit_bse if limit_bse is not None else limit

    nse_stocks = fetch_nse_stocks(limit=effective_limit_nse, min_mcap_inr=min_mcap_inr, use_cache=use_cache, progress_callback=progress_callback)
    bse_stocks = fetch_bse_stocks(limit=effective_limit_bse, min_mcap_inr=min_mcap_inr)

    # Build lookup indices for NSE stocks
    nse_isin_map: Dict[str, int] = {}
    nse_norm_map: Dict[str, int] = {}

    for i, stock in enumerate(nse_stocks):
        isin = stock.get("isin", "").strip().upper()
        if isin and isin != "NAN":
            nse_isin_map[isin] = i
        norm = normalize_company_name(stock.get("company_name", ""))
        if norm:
            nse_norm_map[norm] = i

    combined = list(nse_stocks)
    bse_added = 0

    for bse in bse_stocks:
        b_isin = bse.get("isin", "").strip().upper()
        b_norm = normalize_company_name(bse.get("company_name", ""))

        match_idx = None
        if b_isin and b_isin in nse_isin_map:
            match_idx = nse_isin_map[b_isin]
        elif b_norm and b_norm in nse_norm_map:
            match_idx = nse_norm_map[b_norm]
        elif b_norm:
            # Fuzzy match against NSE normalized names
            for n_norm, idx in nse_norm_map.items():
                if len(b_norm) >= 4 and len(n_norm) >= 4:
                    ratio = difflib.SequenceMatcher(None, b_norm, n_norm).ratio()
                    if ratio >= 0.88:
                        match_idx = idx
                        break

        if match_idx is not None:
            # Company exists in both NSE & BSE -> Retain NSE version, mark dual_listed=True
            combined[match_idx]["dual_listed"] = True
            combined[match_idx]["bse_symbol"] = bse["symbol"]
        else:
            # BSE exclusive stock
            bse["dual_listed"] = False
            combined.append(bse)
            bse_added += 1

    logger.info(
        f"Multi-exchange Universe: {len(nse_stocks)} NSE + {len(bse_stocks)} BSE -> "
        f"{len(combined)} combined ({bse_added} BSE-exclusive, {len(combined) - bse_added} NSE/dual-listed)."
    )

    if limit is not None and limit > 0:
        return combined[:limit]
    return combined


if __name__ == "__main__":
    print("Testing Step 1: NSE Stock Fetcher & Market Cap Filter...")
    # Fetch first 15 stocks as a rapid verification test
    stocks = filter_stocks_by_market_cap(limit=15, batch_size=5, batch_delay=0.5)
    print(f"\nFound {len(stocks)} stocks qualifying > INR 2000 Cr in test sample:")
    for s in stocks:
        cr_val = s["market_cap"] / 1e7
        print(f"  - {s['symbol']} ({s['company_name']}): INR {cr_val:,.2f} Cr")

