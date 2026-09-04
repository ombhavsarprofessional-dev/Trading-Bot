"""
Comprehensive Automated Test Suite for All 10 Modules of the NSE Swing Bot.
"""

import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from screener.stock_fetcher import fetch_nse_equity_list, filter_stocks_by_market_cap
from screener.pivot_calculator import (
    calculate_traditional_pivots,
    calculate_fibonacci_pivots,
    check_traditional_criteria,
    check_fibonacci_criteria,
    evaluate_pivot_confluence,
)
from screener.divergence_detector import calculate_rsi, detect_bullish_divergence
from screener.engine import evaluate_stock, calculate_signal_score
from scheduler.daily_scheduler import init_scheduler, get_scheduler_status
from database.db import init_db, get_db_connection
from database.models import (
    insert_signal,
    get_latest_signals,
    create_trade,
    get_active_trades,
    update_trade_pnl,
    authenticate_user,
)
from broker import get_broker
from backend.app import app


class TestNSETradingBot(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()

    # ─────────────────────────────────────────────────────────
    # Module 1: NSE Stock Fetcher & Market Cap Filter
    # ─────────────────────────────────────────────────────────
    def test_01_stock_fetcher(self):
        df = fetch_nse_equity_list()
        self.assertFalse(df.empty, "NSE equity list should not be empty")
        self.assertIn("SYMBOL", df.columns)
        self.assertIn("SYMBOL_NS", df.columns)
        self.assertTrue(all(df["SYMBOL_NS"].str.endswith(".NS")))

        # Test market cap filter on small sample with cache
        sample = filter_stocks_by_market_cap(limit=5, batch_size=5, batch_delay=0)
        self.assertIsInstance(sample, list)
        for stock in sample:
            self.assertGreaterEqual(stock["market_cap"], 20_000_000_000)

    # ─────────────────────────────────────────────────────────
    # Module 2: Pivot Point Calculator
    # ─────────────────────────────────────────────────────────
    def test_02_pivot_calculator(self):
        # Known bar: H=1005, L=995, C=1000
        # Range = 10, P = 1000
        # Trad: S1 = 2000 - 1005 = 995, S2 = 1000 - 10 = 990
        # Fib: S1 = 1000 - 3.82 = 996.18, S2 = 1000 - 6.18 = 993.82
        trad = calculate_traditional_pivots(1005.0, 995.0, 1000.0)
        self.assertAlmostEqual(trad["P"], 1000.0, places=2)
        self.assertAlmostEqual(trad["S1"], 995.0, places=2)
        self.assertAlmostEqual(trad["S2"], 990.0, places=2)

        fib = calculate_fibonacci_pivots(1005.0, 995.0, 1000.0)
        self.assertAlmostEqual(fib["P"], 1000.0, places=2)
        self.assertAlmostEqual(fib["S1"], 996.18, places=2)
        self.assertAlmostEqual(fib["S2"], 993.82, places=2)

        # Evaluate confluence at price near S1 (995.2)
        confluence = evaluate_pivot_confluence(1005.0, 995.0, 1000.0, 995.2)
        self.assertTrue(confluence["criteria_1_passed"])
        self.assertTrue(confluence["criteria_2_passed"])
        self.assertTrue(confluence["confluence_passed"])
        self.assertEqual(confluence["min_s2"], 990.0)

    # ─────────────────────────────────────────────────────────
    # Module 3: RSI & Bullish Divergence Detector
    # ─────────────────────────────────────────────────────────
    def test_03_divergence_detector(self):
        # Create synthetic series with divergence
        np.random.seed(10)
        dates = pd.date_range("2026-01-01", periods=65, freq="D")
        prices = [100.0]
        for i in range(1, 65):
            if i <= 20:
                prices.append(prices[-1] - 0.8)  # drop to ~84
            elif i <= 38:
                prices.append(prices[-1] + 1.2)  # bounce to ~105
            elif i <= 58:
                prices.append(prices[-1] - 1.4)  # drop to lower low ~77
            else:
                prices.append(prices[-1] + 0.2)  # pause

        df = pd.DataFrame(
            {
                "Open": prices,
                "High": [p + 1.0 for p in prices],
                "Low": [p - 1.0 for p in prices],
                "Close": prices,
            },
            index=dates,
        )

        rsi = calculate_rsi(df["Close"])
        self.assertEqual(len(rsi), len(df))

        res = detect_bullish_divergence(df)
        self.assertTrue(res["divergence_found"])
        self.assertLessEqual(res["rsi_t2"], 40.0)
        self.assertLess(res["price_t2"], res["price_t1"])  # Lower low
        self.assertGreater(res["rsi_t2"], res["rsi_t1"])   # Higher low

    # ─────────────────────────────────────────────────────────
    # Module 4: Screener Engine Combined Evaluation
    # ─────────────────────────────────────────────────────────
    def test_04_screener_engine(self):
        # Construct synthetic candle set that satisfies all 3 criteria
        # Prior day range: H=1005, L=995, C=1000
        # Today's close = 995.2 (hits S1 confluence)
        # Lows history with bullish divergence
        np.random.seed(10)
        dates = pd.date_range("2026-01-01", periods=65, freq="D")
        prices = [100.0]
        for i in range(1, 65):
            if i <= 20:
                prices.append(prices[-1] - 0.8)
            elif i <= 38:
                prices.append(prices[-1] + 1.2)
            elif i <= 58:
                prices.append(prices[-1] - 1.4)
            else:
                prices.append(prices[-1] + 0.2)
        # Set last bar close to 995.2 and previous bar to H=1005, L=995, C=1000
        prices[-2] = 1000.0
        prices[-1] = 995.2

        highs = [p + 1.0 for p in prices]
        lows = [p - 1.0 for p in prices]
        highs[-2] = 1005.0
        lows[-2] = 995.0

        df = pd.DataFrame(
            {"Open": prices, "High": highs, "Low": lows, "Close": prices},
            index=dates,
        )

        signal = evaluate_stock("TEST.NS", "Test Company Ltd", 25_000_000_000, df)
        self.assertIsNotNone(signal)
        self.assertEqual(signal["symbol"], "TEST.NS")
        self.assertAlmostEqual(signal["suggested_entry"], 995.2, places=1)
        # Target must be +15%
        self.assertAlmostEqual(signal["target_price"], round(995.2 * 1.15, 2), places=1)
        # Stop loss must be below min S2 (990) by 0.5% = 990 * 0.995 = 985.05
        self.assertAlmostEqual(signal["stop_loss"], 985.05, places=1)
        self.assertGreaterEqual(signal["score"], 1)
        self.assertLessEqual(signal["score"], 10)

    # ─────────────────────────────────────────────────────────
    # Module 5: Daily Scheduler
    # ─────────────────────────────────────────────────────────
    def test_05_scheduler(self):
        sched = init_scheduler()
        job = sched.get_job("daily_nse_screener")
        self.assertIsNotNone(job)
        status = get_scheduler_status()
        self.assertEqual(status["timezone"], "Asia/Kolkata")
        self.assertIn("15:30", status["schedule_time"])

    # ─────────────────────────────────────────────────────────
    # Module 6: SQLite Database Models & Persistence
    # ─────────────────────────────────────────────────────────
    def test_06_database_operations(self):
        sig_data = {
            "symbol": "TCS.NS",
            "company_name": "Tata Consultancy Services",
            "current_price": 3800.0,
            "suggested_entry": 3800.0,
            "traditional_s1": 3780.0,
            "traditional_s2": 3750.0,
            "fibonacci_s1": 3785.0,
            "fibonacci_s2": 3760.0,
            "rsi_value": 32.0,
            "rsi_signal_value": 30.0,
            "target_price": 4370.0,
            "stop_loss": 3731.25,
            "market_cap_cr": 1300000.0,
            "score": 9,
            "quantity": 2,
            "total_investment": 7600.0,
            "risk_reward_ratio": 8.29,
        }
        sig_id = insert_signal(sig_data)
        self.assertIsInstance(sig_id, int)

        # Create trade from signal
        trade_id = create_trade(
            signal_id=sig_id,
            symbol="TCS.NS",
            quantity=2,
            entry_price=3800.0,
            target_price=4370.0,
            stop_loss=3731.25,
        )
        self.assertIsInstance(trade_id, int)

        # Update PnL
        update_trade_pnl(trade_id, 3900.0)
        active = get_active_trades()
        matching = [t for t in active if t["id"] == trade_id]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["pnl"], 200.0)  # (3900 - 3800) * 2

    # ─────────────────────────────────────────────────────────
    # Module 7: Flask API Backend & Auth
    # ─────────────────────────────────────────────────────────
    def test_07_api_backend(self):
        client = app.test_client()

        # Test login
        login_res = client.post("/api/auth/login", json={"username": "admin", "password": "trader2026"})
        self.assertEqual(login_res.status_code, 200)
        token = login_res.get_json()["token"]

        # Test auth check
        headers = {"Authorization": f"Bearer {token}"}
        me_res = client.get("/api/auth/me", headers=headers)
        self.assertEqual(me_res.status_code, 200)
        self.assertEqual(me_res.get_json()["username"], "admin")

        # Test system status
        stat_res = client.get("/api/system/status", headers=headers)
        self.assertEqual(stat_res.status_code, 200)
        self.assertTrue(stat_res.get_json()["success"])

        # Test screener latest
        sig_res = client.get("/api/screener/latest", headers=headers)
        self.assertEqual(sig_res.status_code, 200)
        self.assertTrue(sig_res.get_json()["success"])

    # ─────────────────────────────────────────────────────────
    # Module 8: Frontend Files Serving
    # ─────────────────────────────────────────────────────────
    def test_08_frontend_assets(self):
        client = app.test_client()
        self.assertEqual(client.get("/").status_code, 200)
        self.assertEqual(client.get("/css/styles.css").status_code, 200)
        self.assertEqual(client.get("/js/app.js").status_code, 200)

    # ─────────────────────────────────────────────────────────
    # Module 9: Broker Integration
    # ─────────────────────────────────────────────────────────
    def test_09_broker(self):
        broker = get_broker("MOCK")
        order = broker.place_buy_order("INFY.NS", 8, 1130.0)
        self.assertEqual(order["status"], "COMPLETE")
        self.assertEqual(order["quantity"], 8)

        gtt = broker.place_target_and_stop_loss("INFY.NS", 8, 1130.0, 1299.5, 1109.4)
        self.assertEqual(gtt["status"], "ACTIVE")

    # ─────────────────────────────────────────────────────────
    # Module 10: Cloudflare Deployment Configuration
    # ─────────────────────────────────────────────────────────
    def test_10_cloudflare_config(self):
        base = Path(__file__).resolve().parent.parent
        self.assertTrue((base / "deployment" / "_headers").exists())
        self.assertTrue((base / "deployment" / "_routes.json").exists())
        self.assertTrue((base / "deployment" / "cloudflare_worker.js").exists())
        self.assertTrue((base / "deployment" / "README_DEPLOYMENT.md").exists())
        self.assertTrue((base / "frontend" / "_headers").exists())
        self.assertTrue((base / "frontend" / "_routes.json").exists())


if __name__ == "__main__":
    unittest.main()
