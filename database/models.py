"""
Database Models & Queries for Signals, Trades, Users, and Logs.
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.db import get_db_connection, verify_password, hash_password


# ─────────────────────────────────────────────────────────────
# SIGNALS
# ─────────────────────────────────────────────────────────────

def insert_signal(signal_data: Dict[str, Any], db_path=None) -> int:
    """Inserts a screener signal into the database."""
    conn = get_db_connection(db_path) if db_path else get_db_connection()
    scan_date = datetime.now().strftime("%Y-%m-%d")
    now_iso = datetime.now().isoformat()
    exchange = signal_data.get("exchange", "NSE")
    dual_listed = 1 if signal_data.get("dual_listed", False) else 0

    with conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO signals (
                symbol, company_name, exchange, dual_listed, scan_date, current_price, suggested_entry,
                traditional_s1, traditional_s2, fibonacci_s1, fibonacci_s2,
                rsi_value, rsi_signal_value, divergence_confirmed, divergence_bars_ago,
                target_price, stop_loss, market_cap_cr, score, quantity,
                total_investment, risk_reward_ratio, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_data["symbol"],
                signal_data.get("company_name", ""),
                exchange,
                dual_listed,
                scan_date,
                signal_data["current_price"],
                signal_data["suggested_entry"],
                signal_data.get("traditional_s1"),
                signal_data.get("traditional_s2"),
                signal_data.get("fibonacci_s1"),
                signal_data.get("fibonacci_s2"),
                signal_data.get("rsi_value"),
                signal_data.get("rsi_signal_value"),
                1 if signal_data.get("divergence_confirmed", True) else 0,
                signal_data.get("divergence_bars_ago", 0),
                signal_data["target_price"],
                signal_data["stop_loss"],
                signal_data.get("market_cap_cr", 0.0),
                signal_data.get("score", 5),
                signal_data.get("quantity", 0),
                signal_data.get("total_investment", 0.0),
                signal_data.get("risk_reward_ratio", 0.0),
                signal_data.get("status", "PENDING"),
                now_iso,
            ),
        )
        return cursor.lastrowid


def save_screener_results(signals: List[Dict[str, Any]], db_path=None) -> List[int]:
    """Saves a batch of screener signals to the database."""
    ids = []
    for sig in signals:
        sig_id = insert_signal(sig, db_path=db_path)
        ids.append(sig_id)
    return ids


def _format_signal_row(row: Any) -> Dict[str, Any]:
    """Formats a database row into a signal dictionary with exchange and dual_listed defaults."""
    d = dict(row)
    d["exchange"] = d.get("exchange") or "NSE"
    d["dual_listed"] = bool(d.get("dual_listed", 0))
    return d


def get_latest_signals(limit: int = 100, db_path=None) -> List[Dict[str, Any]]:
    """Retrieves the latest signals sorted by scan_date and score descending."""
    conn = get_db_connection(db_path) if db_path else get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM signals 
            ORDER BY id DESC 
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        return [_format_signal_row(row) for row in rows]


def get_signal_by_id(signal_id: int, db_path=None) -> Optional[Dict[str, Any]]:
    """Retrieves a single signal by its ID."""
    conn = get_db_connection(db_path) if db_path else get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM signals WHERE id = ?", (signal_id,))
        row = cursor.fetchone()
        return _format_signal_row(row) if row else None


def update_signal_status(signal_id: int, status: str, db_path=None):
    """Updates the status of a signal (e.g. APPROVED, REJECTED)."""
    conn = get_db_connection(db_path) if db_path else get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE signals SET status = ? WHERE id = ?", (status, signal_id))
        conn.commit()


# ─────────────────────────────────────────────────────────────
# TRADES
# ─────────────────────────────────────────────────────────────

def create_trade(
    signal_id: int,
    symbol: str,
    quantity: int,
    entry_price: float,
    target_price: float,
    stop_loss: float,
    broker_order_id: str = "MOCK_ORDER",
    notes: str = "",
    db_path=None,
) -> int:
    """Creates a new trade in the database."""
    conn = get_db_connection(db_path) if db_path else get_db_connection()
    now_iso = datetime.now().isoformat()
    now_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO trades (
                signal_id, symbol, broker_order_id, order_type, quantity,
                entry_price, target_price, stop_loss, current_price,
                pnl, pnl_pct, status, entry_date, notes, created_at
            ) VALUES (?, ?, ?, 'BUY', ?, ?, ?, ?, ?, 0.0, 0.0, 'OPEN', ?, ?, ?)
            """,
            (
                signal_id,
                symbol,
                broker_order_id,
                quantity,
                entry_price,
                target_price,
                stop_loss,
                entry_price,
                now_date,
                notes,
                now_iso,
            ),
        )
        trade_id = cursor.lastrowid
        # Also mark the signal as APPROVED
        cursor.execute("UPDATE signals SET status = 'APPROVED' WHERE id = ?", (signal_id,))
        conn.commit()
        return trade_id


def get_active_trades(db_path=None) -> List[Dict[str, Any]]:
    """Retrieves all open trades."""
    conn = get_db_connection(db_path) if db_path else get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades WHERE status = 'OPEN' ORDER BY id DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_trade_history(db_path=None) -> List[Dict[str, Any]]:
    """Retrieves all trades (both open and closed) for history tracking."""
    conn = get_db_connection(db_path) if db_path else get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades ORDER BY id DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def update_trade_pnl(trade_id: int, current_price: float, db_path=None):
    """Updates the live price and P&L for an active trade."""
    conn = get_db_connection(db_path) if db_path else get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT entry_price, quantity, target_price, stop_loss FROM trades WHERE id = ?", (trade_id,))
        row = cursor.fetchone()
        if not row:
            return

        entry_price = row["entry_price"]
        qty = row["quantity"]
        target = row["target_price"]
        sl = row["stop_loss"]

        pnl = round((current_price - entry_price) * qty, 2)
        pnl_pct = round(((current_price - entry_price) / entry_price) * 100.0, 2) if entry_price > 0 else 0.0

        status = "OPEN"
        exit_price = None
        exit_date = None
        if current_price >= target:
            status = "TARGET_HIT"
            exit_price = target
            exit_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elif current_price <= sl:
            status = "SL_HIT"
            exit_price = sl
            exit_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            """
            UPDATE trades 
            SET current_price = ?, pnl = ?, pnl_pct = ?, status = ?,
                exit_price = COALESCE(?, exit_price),
                exit_date = COALESCE(?, exit_date)
            WHERE id = ?
            """,
            (current_price, pnl, pnl_pct, status, exit_price, exit_date, trade_id),
        )
        conn.commit()


# ─────────────────────────────────────────────────────────────
# SYSTEM LOGS
# ─────────────────────────────────────────────────────────────

def add_log(level: str, source: str, message: str, db_path=None):
    """Adds a log message to the system_logs table."""
    conn = get_db_connection(db_path) if db_path else get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO system_logs (timestamp, level, source, message) VALUES (?, ?, ?, ?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), level.upper(), source, message),
        )
        conn.commit()


def get_recent_logs(limit: int = 50, db_path=None) -> List[Dict[str, Any]]:
    """Retrieves the most recent system logs."""
    conn = get_db_connection(db_path) if db_path else get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM system_logs ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


# ─────────────────────────────────────────────────────────────
# USERS & AUTH
# ─────────────────────────────────────────────────────────────

def authenticate_user(username: str, password: str, db_path=None) -> bool:
    """Verifies username and password."""
    conn = get_db_connection(db_path) if db_path else get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if not row:
            return False
        return verify_password(row["password_hash"], password)
