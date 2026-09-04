"""
Broker package initialization.
"""
from .base import BaseBroker
from .mock_broker import MockBroker
from .zerodha_kite import ZerodhaKiteBroker
from .angel_one import AngelOneBroker

def get_broker(mode: str = None) -> BaseBroker:
    from config import BROKER_MODE
    selected_mode = (mode or BROKER_MODE).upper()
    if selected_mode == "ZERODHA":
        return ZerodhaKiteBroker()
    elif selected_mode == "ANGEL":
        return AngelOneBroker()
    else:
        return MockBroker()
