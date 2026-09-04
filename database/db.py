"""
Module 6: SQLite Database Setup & Connection Management

Provides database initialization, tables for:
- market_cap_cache: Cached market caps and company names
- signals: Daily screener signals with pivot levels, RSI, target, SL, score
- trades: Executed/approved trades, P&L tracking, broker status
- system_logs: Screener run logs and scheduler heartbeats
- users: Single-user authentication credentials
"""

import sys
import sqlite3
import hashlib
import os
import logging
from pathlib import Path
from datetime import datetime

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (
    DATABASE_PATH,
    DEFAULT_USERNAME,
    DEFAULT_PASSWORD,
)

logger = logging.getLogger(__name__)


def hash_password(password: str, salt: bytes = None) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with salt."""
    if salt is None:
        salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return f"{salt.hex()}:{key.hex()}"


def verify_password(stored_hash: str, provided_password: str) -> bool:
    """Verify stored PBKDF2 password hash."""
    try:
        salt_hex, key_hex = stored_hash.split(":")
        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(key_hex)
        key = hashlib.pbkdf2_hmac("sha256", provided_password.encode("utf-8"), salt, 100000)
        return hashlib.sha256(key).digest() == hashlib.sha256(expected_key).digest()
    except Exception:
        return False


def get_db_connection(db_path=DATABASE_PATH):
    """Returns a SQLite connection with Row factory enabled."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=DATABASE_PATH):
    """Initializes all database tables and seeds default user."""
    os.makedirs(Path(db_path).parent, exist_ok=True)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Market Cap Cache Table
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

        # 2. Screener Signals Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                company_name TEXT,
                exchange TEXT DEFAULT 'NSE',
                dual_listed INTEGER DEFAULT 0,
                scan_date TEXT NOT NULL,
                current_price REAL NOT NULL,
                suggested_entry REAL NOT NULL,
                traditional_s1 REAL,
                traditional_s2 REAL,
                fibonacci_s1 REAL,
                fibonacci_s2 REAL,
                rsi_value REAL,
                rsi_signal_value REAL,
                divergence_confirmed INTEGER DEFAULT 1,
                divergence_bars_ago INTEGER,
                target_price REAL NOT NULL,
                stop_loss REAL NOT NULL,
                market_cap_cr REAL,
                score INTEGER NOT NULL,
                quantity INTEGER DEFAULT 0,
                total_investment REAL DEFAULT 0.0,
                risk_reward_ratio REAL DEFAULT 0.0,
                status TEXT DEFAULT 'PENDING',  -- PENDING, APPROVED, REJECTED, EXPIRED
                created_at TEXT NOT NULL
            )
            """
        )

        # 3. Trades Table (Executed / Approved Trades)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER,
                symbol TEXT NOT NULL,
                broker_order_id TEXT,
                order_type TEXT DEFAULT 'BUY',
                quantity INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                target_price REAL NOT NULL,
                stop_loss REAL NOT NULL,
                current_price REAL,
                pnl REAL DEFAULT 0.0,
                pnl_pct REAL DEFAULT 0.0,
                status TEXT DEFAULT 'OPEN',     -- OPEN, TARGET_HIT, SL_HIT, CLOSED
                entry_date TEXT NOT NULL,
                exit_price REAL,
                exit_date TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (signal_id) REFERENCES signals (id)
            )
            """
        )

        # 4. System Logs Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                source TEXT NOT NULL,
                message TEXT NOT NULL
            )
            """
        )

        # 5. Users Table (Single user login)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        # Seed default user if not exists
        cursor.execute("SELECT id FROM users WHERE username = ?", (DEFAULT_USERNAME,))
        if not cursor.fetchone():
            pwd_hash = hash_password(DEFAULT_PASSWORD)
            cursor.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (DEFAULT_USERNAME, pwd_hash, datetime.now().isoformat()),
            )
            logger.info(f"Initialized default user '{DEFAULT_USERNAME}' in database.")

        # Run graceful migrations for existing tables
        migrate_db(conn)

        conn.commit()
    logger.info(f"Database initialized successfully at {db_path}")


def migrate_db(conn):
    """Gracefully migrates database schema for existing databases."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(signals)")
    cols = {row["name"] for row in cursor.fetchall()}

    if "exchange" not in cols:
        logger.info("Migrating signals table: adding 'exchange' column...")
        cursor.execute("ALTER TABLE signals ADD COLUMN exchange TEXT DEFAULT 'NSE'")

    if "dual_listed" not in cols:
        logger.info("Migrating signals table: adding 'dual_listed' column...")
        cursor.execute("ALTER TABLE signals ADD COLUMN dual_listed INTEGER DEFAULT 0")

    conn.commit()


if __name__ == "__main__":
    init_db()
    print("Database tables created and default user seeded successfully!")
