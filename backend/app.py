"""
Module 7: Flask API Backend with JWT Authentication.

Provides REST endpoints for:
- User Login & Token Verification
- Screener Signals & Manual Scan Trigger
- Trade Approval & Broker Order Dispatch
- Trade Rejection
- Active Positions & Historical P&L Tracker
- System Health, Scheduler Status & Logs
- Static Frontend Dashboard Serving
"""

import sys
import threading
import logging
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import BASE_DIR, BROKER_MODE
from database.db import init_db
from database.models import (
    authenticate_user,
    get_latest_signals,
    get_signal_by_id,
    update_signal_status,
    create_trade,
    get_active_trades,
    get_trade_history,
    update_trade_pnl,
    get_recent_logs,
    add_log,
)
from backend.auth import generate_token, jwt_required
from broker import get_broker
from scheduler.daily_scheduler import (
    init_scheduler,
    start_scheduler,
    get_scheduler_status,
    run_screener_job,
)

logger = logging.getLogger(__name__)

frontend_folder = BASE_DIR / "frontend"
app = Flask(__name__, static_folder=str(frontend_folder), static_url_path="")
CORS(app, resources={r"/api/*": {"origins": "*"}})


# ─────────────────────────────────────────────────────────────
# STATIC FRONTEND ROUTES
# ─────────────────────────────────────────────────────────────

@app.route("/")
def serve_index():
    return send_from_directory(str(frontend_folder), "index.html")


@app.route("/<path:path>")
def serve_static(path):
    file_path = frontend_folder / path
    if file_path.exists():
        return send_from_directory(str(frontend_folder), path)
    return send_from_directory(str(frontend_folder), "index.html")


# ─────────────────────────────────────────────────────────────
# AUTHENTICATION ENDPOINTS
# ─────────────────────────────────────────────────────────────

@app.route("/api/auth/login", methods=["POST"])
def login():
    """Authenticates user and returns JWT token."""
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()


    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    if authenticate_user(username, password):
        token = generate_token(username)
        add_log("INFO", "AUTH", f"User '{username}' logged in successfully.")
        return jsonify({
            "success": True,
            "token": token,
            "user": {"username": username},
        })
    else:
        add_log("WARNING", "AUTH", f"Failed login attempt for user '{username}'.")
        return jsonify({"error": "Invalid username or password"}), 401


@app.route("/api/auth/me", methods=["GET"])
@jwt_required
def get_current_user():
    """Validates session token and returns user details."""
    return jsonify({"username": request.current_user, "authenticated": True})


# ─────────────────────────────────────────────────────────────
# SCREENER ENDPOINTS
# ─────────────────────────────────────────────────────────────

@app.route("/api/screener/latest", methods=["GET"])
@jwt_required
def get_signals():
    """Returns the latest daily screener results."""
    limit = int(request.args.get("limit", 100))
    signals = get_latest_signals(limit=limit)
    nse_count = sum(1 for s in signals if (s.get("exchange") or "NSE").upper() == "NSE")
    bse_count = sum(1 for s in signals if (s.get("exchange") or "").upper() == "BSE")
    return jsonify({
        "success": True,
        "count": len(signals),
        "nse_count": nse_count,
        "bse_count": bse_count,
        "signals": signals,
    })


@app.route("/api/screener/run", methods=["POST"])
@jwt_required
def trigger_screener_run():
    """Triggers an on-demand screener scan."""
    data = request.get_json(silent=True) or {}
    limit_universe = data.get("limit_universe")

    if limit_universe is not None:
        try:
            limit_universe = int(limit_universe)
        except ValueError:
            limit_universe = None

    status = get_scheduler_status()
    if status.get("is_scanning", False):
        return jsonify({"success": False, "message": "A scan is already in progress"}), 409

    # Run in background thread to avoid blocking API response
    def background_scan():
        logger.info("Manual screener trigger initiated via API...")
        run_screener_job(limit_universe=limit_universe)

    thread = threading.Thread(target=background_scan, daemon=True)
    thread.start()

    return jsonify({
        "success": True,
        "message": "Screener scan started in background",
    })


# ─────────────────────────────────────────────────────────────
# TRADE MANAGEMENT & APPROVAL
# ─────────────────────────────────────────────────────────────

@app.route("/api/trades/approve/<int:signal_id>", methods=["POST"])
@jwt_required
def approve_trade(signal_id):
    """
    User clicks APPROVE on a stock:
    1. Validates signal
    2. Places CNC Buy Order via configured Broker API
    3. Places GTT Target & Stop Loss order via Broker API
    4. Records trade in database
    """
    signal = get_signal_by_id(signal_id)
    if not signal:
        return jsonify({"error": "Signal not found"}), 404

    if signal["status"] == "APPROVED":
        return jsonify({"error": "Signal has already been approved"}), 400

    data = request.get_json(silent=True) or {}
    custom_qty = data.get("quantity")

    qty = int(custom_qty) if custom_qty else signal["quantity"]

    if qty <= 0:
        return jsonify({"error": "Invalid order quantity"}), 400

    symbol = signal["symbol"]
    entry_price = signal["suggested_entry"]
    target_price = signal["target_price"]
    stop_loss = signal["stop_loss"]

    broker = get_broker()

    try:
        # 1. Place Buy Order
        order_res = broker.place_buy_order(
            symbol=symbol,
            quantity=qty,
            price=entry_price,
            order_type="LIMIT",
            product="CNC",
        )
        order_id = order_res.get("order_id", f"ORD_{signal_id}")

        # 2. Place Target and Stop Loss (GTT OCO)
        gtt_res = broker.place_target_and_stop_loss(
            symbol=symbol,
            quantity=qty,
            entry_price=entry_price,
            target_price=target_price,
            stop_loss=stop_loss,
        )

        # 3. Record Trade in DB
        trade_id = create_trade(
            signal_id=signal_id,
            symbol=symbol,
            quantity=qty,
            entry_price=entry_price,
            target_price=target_price,
            stop_loss=stop_loss,
            broker_order_id=order_id,
            notes=f"Approved by {request.current_user}. Broker: {order_res.get('broker', 'BROKER')}",
        )

        add_log(
            "INFO",
            "TRADE",
            f"Approved {symbol} x {qty} @ INR {entry_price}. Target: INR {target_price}, SL: INR {stop_loss} (Trade ID: {trade_id})",
        )

        return jsonify({
            "success": True,
            "message": f"Order successfully placed for {symbol}",
            "trade_id": trade_id,
            "order": order_res,
            "gtt": gtt_res,
        })

    except Exception as e:
        logger.error(f"Error executing trade for {symbol}: {e}", exc_info=True)
        add_log("ERROR", "TRADE", f"Failed trade execution for {symbol}: {e}")
        return jsonify({"error": f"Broker error: {str(e)}"}), 500


@app.route("/api/trades/reject/<int:signal_id>", methods=["POST"])
@jwt_required
def reject_trade(signal_id):
    """User clicks REJECT on a stock."""
    signal = get_signal_by_id(signal_id)
    if not signal:
        return jsonify({"error": "Signal not found"}), 404

    update_signal_status(signal_id, "REJECTED")
    add_log("INFO", "TRADE", f"Signal {signal['symbol']} marked as REJECTED by {request.current_user}")
    return jsonify({"success": True, "message": f"Signal {signal['symbol']} rejected"})


@app.route("/api/trades/active", methods=["GET"])
@jwt_required
def list_active_trades():
    """Lists all open positions with real-time or latest P&L."""
    trades = get_active_trades()
    return jsonify({
        "success": True,
        "count": len(trades),
        "trades": trades,
    })


@app.route("/api/trades/history", methods=["GET"])
@jwt_required
def list_trade_history():
    """Lists all historical trades and summary performance."""
    trades = get_trade_history()
    total_pnl = sum(t.get("pnl", 0.0) for t in trades)
    closed_trades = [t for t in trades if t.get("status") in ("TARGET_HIT", "SL_HIT", "CLOSED")]
    winning_trades = [t for t in closed_trades if t.get("pnl", 0.0) > 0]
    win_rate = round((len(winning_trades) / len(closed_trades)) * 100.0, 1) if closed_trades else 0.0

    return jsonify({
        "success": True,
        "total_trades": len(trades),
        "closed_trades": len(closed_trades),
        "total_realized_pnl": round(total_pnl, 2),
        "win_rate_pct": win_rate,
        "trades": trades,
    })


# ─────────────────────────────────────────────────────────────
# SYSTEM & LOGS ENDPOINTS
# ─────────────────────────────────────────────────────────────

@app.route("/api/system/status", methods=["GET"])
@jwt_required
def system_status():
    """Returns scheduler health, next run time, and broker mode."""
    sched_status = get_scheduler_status()
    return jsonify({
        "success": True,
        "broker_mode": BROKER_MODE,
        "scheduler": sched_status,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.route("/api/system/logs", methods=["GET"])
@jwt_required
def system_logs():
    """Returns recent system logs."""
    limit = int(request.args.get("limit", 50))
    logs = get_recent_logs(limit=limit)
    return jsonify({
        "success": True,
        "count": len(logs),
        "logs": logs,
    })


def create_app():
    """Factory to create initialized app."""
    init_db()
    return app


if __name__ == "__main__":
    init_db()
    start_scheduler()
    print("Starting Flask API server on http://127.0.0.1:5000...")
    app.run(host="0.0.0.0", port=5000, debug=False)
