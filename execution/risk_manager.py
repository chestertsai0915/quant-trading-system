import math

class RiskManager:
    def __init__(self, leverage=1):
        """
        初始只存槓桿，金額由外部傳入
        """
        self.leverage = leverage

    def calculate_quantity(self, current_price, usdt_amount):
        """
        :param current_price: 現價
        :param usdt_amount: 這次要投入多少 U (由策略決定)
        """
        if current_price <= 0: return 0
        
        target_notional = usdt_amount * self.leverage
        quantity = target_notional / current_price
        
        # 這裡可以加入精密度的處理 (Binance BTC 最小單位通常是 0.001)
        # 簡單起見先回傳 float
        return quantity

    def check_risk(self, account_balance):
        """
        風險檢查 (簡單版)
        如果餘額不足，回傳 False
        """
        if account_balance < self.fixed_usdt_amount:
            return False
        return True