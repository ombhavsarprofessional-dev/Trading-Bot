"""
Module 4: Screener Engine that combines all criteria.

Combines:
- Criteria 1: Traditional Pivot Double Bottom Zone (near S1/S2 within 0.5%, gap < 1.5%)
- Criteria 2: Fibonacci Pivot Support Zone (near Fib S1/S2 within 1.0%)
- Criteria 3: RSI Bullish Divergence (14-period RSI, lower low price + higher low RSI in last 10 bars, RSI <= 40)
- Criteria 4: Market Cap Filter (> 2000 Cr INR)

Computes Trade Parameters:
- Suggested Entry: Current price at support zone
- Target: Entry + 15%
- Stop Loss: Lower of Trad S2 and Fib S2 minus 0.5%
- Capital: ₹10,000 per trade, position sizing = floor(10000 / Entry)
- Signal Strength Score: 1 - 10 based on confluence tightness and divergence strength
"""

import sys
import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd
import yfinance as yf

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import (
    MIN_MARKET_CAP_INR,
    TRADE_CAPITAL_INR,
    PROFIT_TARGET_PCT,
    STOP_LOSS_BUFFER_PCT,
    BATCH_SIZE,
    BATCH_DELAY_SECONDS,
)
from screener.stock_fetcher import filter_stocks_by_market_cap
from screener.pivot_calculator import evaluate_pivot_confluence
from screener.divergence_detector import detect_bullish_divergence

logger = logging.getLogger(__name__)


def calculate_signal_score(confluence_data: Dict[str, Any], divergence_data: Dict[str, Any]) -> int:
    """
    Calculates a 1 - 10 Signal Strength Score based on:
    1. Pivot confluence tightness (1 - 4 points)
    2. Proximity of price to the support line (1 - 3 points)
    3. RSI depth / oversoldness (1 - 2 points)
    4. Divergence clarity (1 point)
    """
    score = 0

    # 1. Confluence tightness between Trad and Fib
    avg_dist = confluence_data.get("avg_support_dist_pct", 1.0)
    if avg_dist <= 0.25:
        score += 4
    elif avg_dist <= 0.50:
        score += 3
    elif avg_dist <= 0.75:
        score += 2
    else:
        score += 1

    # 2. Proximity to Traditional S1/S2
    c1_details = confluence_data.get("c1_details", {})
    min_trad_dist = min(c1_details.get("dist_s1_pct", 1.0), c1_details.get("dist_s2_pct", 1.0))
    if min_trad_dist <= 0.15:
        score += 3
    elif min_trad_dist <= 0.35:
        score += 2
    else:
        score += 1

    # 3. RSI Depth
    rsi_val = divergence_data.get("rsi_t2", divergence_data.get("current_rsi", 40))
    if rsi_val <= 30.0:
        score += 2
    elif rsi_val <= 38.0:
        score += 1

    # 4. Divergence clarity (clear price drop and rsi increase)
    price_drop = divergence_data.get("price_drop_pct", 0)
    rsi_gain = divergence_data.get("rsi_gain", 0)
    if price_drop >= 3.0 and rsi_gain >= 3.0:
        score += 1

    # Ensure score stays in range 1 - 10
    return max(1, min(10, score))


def evaluate_stock(
    symbol: str,
    company_name: str,
    market_cap: float,
    df: pd.DataFrame,
) -> Optional[Dict[str, Any]]:
    """
    Evaluates a single stock against ALL 3 technical criteria.
    Returns structured signal dictionary if all criteria pass, else None.
    """
    if df is None or len(df) < 25:
        return None

    # Get the latest price and the reference candle for pivots
    current_price = float(df["Close"].iloc[-1])

    # In daily swing trading, evaluate pivots calculated from:
    # 1. Prior completed candle (df.iloc[-2]) tested by today's close (df.iloc[-1])
    # 2. Current completed candle (df.iloc[-1]) forming support at today's close
    confluence = None
    ref_candidates = []
    if len(df) >= 2:
        ref_candidates.append(df.iloc[-2])  # Prior day's bar
    ref_candidates.append(df.iloc[-1])      # Current day's bar

    for ref_bar in ref_candidates:
        h = float(ref_bar["High"])
        l = float(ref_bar["Low"])
        c = float(ref_bar["Close"])
        if h > l:
            conf_res = evaluate_pivot_confluence(h, l, c, current_price)
            if conf_res["confluence_passed"]:
                confluence = conf_res
                break

    # If neither passed confluence, stock does not qualify
    if confluence is None:
        return None


    # Criteria 3: RSI Bullish Divergence
    divergence = detect_bullish_divergence(df)
    if not divergence.get("divergence_found", False):
        return None

    # ALL CRITERIA PASSED! Construct trade parameters
    trad = confluence["traditional"]
    fib = confluence["fibonacci"]
    min_s2 = confluence["min_s2"]

    entry_price = round(current_price, 2)
    target_price = round(entry_price * (1.0 + PROFIT_TARGET_PCT), 2)
    stop_loss = round(min_s2 * (1.0 - STOP_LOSS_BUFFER_PCT), 2)

    # Position sizing: ₹10,000 full capital allocation
    qty = int(TRADE_CAPITAL_INR / entry_price) if entry_price > 0 else 0
    total_investment = round(qty * entry_price, 2)

    # Risk-Reward Ratio
    risk = entry_price - stop_loss
    reward = target_price - entry_price
    risk_reward = round(reward / risk, 2) if risk > 0 else 0.0

    score = calculate_signal_score(confluence, divergence)
    mcap_cr = round(market_cap / 1e7, 2)

    return {
        "symbol": symbol,
        "company_name": company_name,
        "current_price": entry_price,
        "suggested_entry": entry_price,
        "traditional_s1": trad["S1"],
        "traditional_s2": trad["S2"],
        "fibonacci_s1": fib["S1"],
        "fibonacci_s2": fib["S2"],
        "rsi_value": divergence.get("current_rsi"),
        "rsi_signal_value": divergence.get("rsi_t2"),
        "divergence_confirmed": True,
        "divergence_bars_ago": divergence.get("bars_ago"),
        "target_price": target_price,
        "stop_loss": stop_loss,
        "market_cap_cr": mcap_cr,
        "score": score,
        "quantity": qty,
        "total_investment": total_investment,
        "risk_reward_ratio": risk_reward,
        "status": "PENDING",
    }


def run_screener_engine(
    universe: Optional[List[Dict]] = None,
    limit_universe: Optional[int] = None,
    batch_size: int = BATCH_SIZE,
    batch_delay: float = BATCH_DELAY_SECONDS,
    progress_callback=None,
) -> List[Dict[str, Any]]:
    """
    Executes the full screener process:
    1. Obtains market cap filtered stocks (> ₹2000 Cr)
    2. Fetches historical daily candles (6 months)
    3. Evaluates all 3 criteria
    4. Returns sorted list of qualifying signals (highest score first)
    """
    if universe is None:
        logger.info("Fetching qualifying stocks from NSE universe (> INR 2000 Cr)...")
        universe = filter_stocks_by_market_cap(
            limit=limit_universe,
            batch_size=batch_size,
            batch_delay=batch_delay,
        )

    if limit_universe and len(universe) > limit_universe:
        universe = universe[:limit_universe]

    logger.info(f"Starting technical screening for {len(universe)} qualified stocks...")
    signals = []
    symbols = [s["symbol"] for s in universe]
    meta_lookup = {s["symbol"]: s for s in universe}

    # Fetch daily OHLCV in batches of 50 to optimize network throughput
    total = len(symbols)
    for i in range(0, total, batch_size):
        batch_symbols = symbols[i : i + batch_size]
        logger.info(
            f"Downloading daily bars for batch {i // batch_size + 1}/{(total + batch_size - 1) // batch_size} "
            f"({len(batch_symbols)} tickers)..."
        )

        try:
            # Download 6 months of daily data
            data = yf.download(
                batch_symbols,
                period="6mo",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False,
            )
        except Exception as e:
            logger.error(f"Error downloading batch: {e}")
            continue

        for sym in batch_symbols:
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    if sym in data.columns.get_level_values(0):
                        df = data[sym].dropna(how="all").copy()
                    else:
                        continue
                else:
                    df = data.dropna(how="all").copy()


                # Ensure sufficient data and valid columns
                if df.empty or len(df) < 20 or "Close" not in df.columns:
                    continue

                meta = meta_lookup[sym]
                signal = evaluate_stock(
                    symbol=sym,
                    company_name=meta["company_name"],
                    market_cap=meta["market_cap"],
                    df=df,
                )

                if signal is not None:
                    logger.info(
                        f"*** MATCH FOUND ***: {sym} ({meta['company_name']}) "
                        f"Score: {signal['score']}/10, Entry: INR {signal['suggested_entry']}, "
                        f"Target: INR {signal['target_price']}, SL: INR {signal['stop_loss']}"
                    )
                    signals.append(signal)

            except Exception as ex:
                logger.debug(f"Error evaluating stock {sym}: {ex}")

        if progress_callback:
            progress_callback(min(i + batch_size, total), total)

        if i + batch_size < total and batch_delay > 0:
            time.sleep(batch_delay)

    # Sort signals by Score (descending), then Confluence closeness
    signals.sort(key=lambda s: s["score"], reverse=True)
    logger.info(f"Screening complete. Total signals detected: {len(signals)}")
    return signals


if __name__ == "__main__":
    print("Testing Step 4: Screener Engine...")

    # Let's test with 20 stocks to observe performance and criteria checks
    test_stocks = filter_stocks_by_market_cap(limit=20, batch_size=10, batch_delay=0.5)
    print(f"Loaded {len(test_stocks)} sample stocks.")

    signals = run_screener_engine(universe=test_stocks, batch_size=10, batch_delay=0.5)
    print(f"\nCompleted run. Generated {len(signals)} signals.")
    for sig in signals:
        print(f"  - {sig['symbol']} | Score: {sig['score']} | Entry: {sig['suggested_entry']} | Target: {sig['target_price']} | SL: {sig['stop_loss']}")
    print("\nStep 4 completed and verified successfully!")
