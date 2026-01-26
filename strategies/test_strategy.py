# strategies/test_strategy.py
from .base_strategy import BaseStrategy

class TestStrategy(BaseStrategy):
    def __init__(self):
        super().__init__(name="TEST_FORCE_BUY")

    def generate_signal(self):
        # 無論如何，直接回傳買入訊號
        return {
            'action': 'LONG',
            'quantity': 0.005,  # 隨便寫，RiskManager 會重算
            'reason': '強制測試下單功能'
        }