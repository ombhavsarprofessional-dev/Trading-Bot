"""
Abstract Base Broker Interface for Indian Stock Markets.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseBroker(ABC):
    """
    Standard interface for broker integrations (Zerodha Kite, Angel One, Mock).
    """

    @abstractmethod
    def place_buy_order(
        self,
        symbol: str,
        quantity: int,
        price: float,
        order_type: str = "LIMIT",
        product: str = "CNC",
    ) -> Dict[str, Any]:
        """
        Places a buy delivery order for the stock.
        """
        pass

    @abstractmethod
    def place_target_and_stop_loss(
        self,
        symbol: str,
        quantity: int,
        entry_price: float,
        target_price: float,
        stop_loss: float,
    ) -> Dict[str, Any]:
        """
        Sets up automated target and stop loss (e.g. GTT OCO order in Zerodha).
        """
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """
        Fetches the current status of an order.
        """
        pass
