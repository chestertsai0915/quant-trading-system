import math

class RiskManager:
    def __init__(self, fixed_usdt_amount=50, leverage=1):
        """
        :param fixed_usdt_amount: 每次開倉的價值 (USDT)
        :param leverage: 槓桿倍數 (建議先用 1)
        """
        self.fixed_usdt_amount = fixed_usdt_amount
        self.leverage = leverage

    def calculate_quantity(self, current_price):
        """
        計算下單數量
        Quantity = (目標投入金額 * 槓桿) / 當前價格
        """
        if current_price <= 0:
            return 0
        
        # 計算名義價值 (Notional Value)
        target_notional = self.fixed_usdt_amount * self.leverage
        
        # 計算幣的數量
        quantity = target_notional / current_price
        
        return quantity

    def check_risk(self, account_balance):
        """
        風險檢查 (簡單版)
        如果餘額不足，回傳 False
        """
        if account_balance < self.fixed_usdt_amount:
            return False
        return True