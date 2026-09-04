"""
Configuration settings for NSE Swing Trading Stock Screener & Semi-Automated Bot.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# Base Paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = BASE_DIR / "database" / "trading_bot.db"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DATABASE_PATH.parent, exist_ok=True)

# NSE & BSE Universe & Market Cap Filter
NSE_EQUITY_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
BSE_EQUITY_URL = "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?Group=&Scripcode=&industry=&segment=Equity&status=Active"
BSE_BACKUP_URL = "https://www.bseindia.com/corporates/List_Scrips.html"
MIN_MARKET_CAP_INR = 20_000_000_000  # ₹2,000 Crore INR (1 Cr = 10^7 INR)
MARKET_CAP_CACHE_HOURS = 24  # Cache market caps to avoid redundant yfinance queries
BATCH_SIZE = 50
BATCH_DELAY_SECONDS = 1.0

# Criteria 1: Traditional Daily Pivots
# P  = (High + Low + Close) / 3
# S1 = (2 * P) - High
# S2 = P - (High - Low)
TRADITIONAL_PIVOT_TOLERANCE = 0.005  # Within 0.5% of S1 or S2
S1_S2_MAX_GAP_RATIO = 0.015         # Gap between S1 and S2 < 1.5% of price

# Criteria 2: Fibonacci Daily Pivots
# S1 = P - 0.382 * (High - Low)
# S2 = P - 0.618 * (High - Low)
FIBONACCI_PIVOT_TOLERANCE = 0.025   # Within 2.5% tolerance of Fib S1 or S2

# Criteria 3: RSI Bullish Divergence
RSI_PERIOD = 14
RSI_SOURCE = "Close"
RSI_DIVERGENCE_LOOKBACK_MIN = 5     # Minimum bars between lows
RSI_DIVERGENCE_LOOKBACK_MAX = 60    # Maximum bars to scan for previous low
RSI_RECENCY_BARS = 10               # Divergence must be detected within last 10 daily bars
RSI_OVERSOLD_THRESHOLD = 40.0       # RSI at signal point <= 40

# Trade Parameters
TRADE_CAPITAL_INR = 10_000.0        # Capital per trade
PROFIT_TARGET_PCT = 0.15            # +15% from entry price
STOP_LOSS_BUFFER_PCT = 0.005        # 0.5% below lower S2 (min of Trad S2 and Fib S2)
TRADE_TYPE = "CNC"                  # Delivery / Swing

# Scheduler Settings
TIMEZONE = "Asia/Kolkata"
DAILY_RUN_HOUR = 15
DAILY_RUN_MINUTE = 30               # 3:30 PM IST (Market close)

# Security & Authentication (Single User)
DEFAULT_USERNAME = os.getenv("BOT_USERNAME", "admin")
DEFAULT_PASSWORD = os.getenv("BOT_PASSWORD", "trader2026")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "nse_swing_bot_secure_secret_key_2026")
JWT_EXPIRY_HOURS = 72

# Broker Mode: 'MOCK', 'ZERODHA', 'ANGEL'
BROKER_MODE = os.getenv("BROKER_MODE", "MOCK")
