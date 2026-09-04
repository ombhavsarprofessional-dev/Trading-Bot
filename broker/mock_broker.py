"""
Mock Broker implementation for Paper Trading and Dashboard Testing.
"""

import time
import random
import logging
from typing import Dict, Any
from .base import BaseBroker

logger = logging.getLogger(__name__)


class MockBroker(BaseBroker):
    """
    Simulates real broker behavior for safe testing and semi-automated approval flow.
    """

    def __init__(self):
        self.orders = {}

    def place_buy_order(
        self,
        symbol: str,
        quantity: int,
        price: float,
        order_type: str = "LIMIT",
        product: str = "CNC",
    ) -> Dict[str, Any]:
        order_id = f"MOCK_{int(time.time())}_{random.randint(1000, 9999)}"
        order_details = {
            "order_id": order_id,
            "broker": "MOCK_BROKER",
            "symbol": symbol,
            "quantity": quantity,
            "price": price,
            "order_type": order_type,
            "product": product,
            "status": "COMPLETE",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "message": f"Simulated CNC BUY {quantity} shares of {symbol} at INR {price:.2f}",
        }
        self.orders[order_id] = order_details
        logger.info(f"[MOCK BROKER] {order_details['message']} (ID: {order_id})")
        return order_details

    def place_target_and_stop_loss(
        self,
        symbol: str,
        quantity: int,
        entry_price: float,
        target_price: float,
        stop_loss: float,
    ) -> Dict[str, Any]:
        gtt_id = f"MOCK_GTT_{int(time.time())}_{random.randint(1000, 9999)}"
        gtt_details = {
            "gtt_id": gtt_id,
            "broker": "MOCK_BROKER",
            "symbol": symbol,
            "quantity": quantity,
            "target_price": target_price,
            "stop_loss": stop_loss,
            "status": "ACTIVE",
            "message": (
                f"Simulated GTT OCO order placed for {symbol}: "
                f"Target = INR {target_price:.2f} (+15%), Stop Loss = INR {stop_loss:.2f} (-0.5% below S2)"
            ),
        }
        logger.info(f"[MOCK BROKER] {gtt_details['message']} (GTT ID: {gtt_id})")
        return gtt_details

    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        return self.orders.get(
            order_id,
            {"order_id": order_id, "status": "COMPLETE", "message": "Simulated executed order"},
        )
