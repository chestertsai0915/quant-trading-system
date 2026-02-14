# managers/portfolio_manager.py
import logging

class PortfolioManager:
    def __init__(self, config, db):
        self.config = config
        self.db = db  # 依賴 DB 來讀寫數據
        self.mode = self.config.get("risk", "allocation_mode", "EQUAL_WEIGHT")
        self.total_strategies = self.config.get("risk", "total_strategies", 1)
        self.leverage = self.config.get("risk", "leverage", 1)

    def calculate_allocation(self, strategy_name, total_equity):
        # ... (原本的資金分配邏輯保持不變) ...
        # 1. 查總私房錢
        # 2. 查自己私房錢
        # 3. 算額度
        pass 

    def update_position_record(self, strategy, delta_qty, trade_price):
        """
        [核心業務邏輯] 
        計算加減倉後的：新持倉量、新均價、本次損益
        並呼叫 DB 儲存結果
        """
        # 1. 從 DB 讀取舊狀態
        current_pos, avg_price, total_pnl = self.db.get_strategy_state(strategy)
        
        new_pos = current_pos + delta_qty
        realized_pnl = 0.0
        
        # 2. 執行數學計算 (加權平均 & 損益計算)
        
        # 情境 A: 加倉 (方向相同)
        if current_pos * delta_qty > 0:
            total_cost = (current_pos * avg_price) + (delta_qty * trade_price)
            avg_price = total_cost / new_pos
            
        # 情境 B: 減倉/平倉 (方向相反)
        elif current_pos * delta_qty < 0:
            close_qty = abs(delta_qty)
            
            # 計算損益
            if current_pos > 0: # 多單平倉
                pnl = (trade_price - avg_price) * close_qty
            else: # 空單平倉
                pnl = (avg_price - trade_price) * close_qty
                
            realized_pnl = pnl
            total_pnl += realized_pnl # 更新總累積損益
            
            # 如果全部平倉，重置均價
            if abs(new_pos) < 1e-8: # 浮點數防呆
                new_pos = 0
                avg_price = 0

        # 情境 C: 新開倉 (原本是 0)
        elif current_pos == 0:
            avg_price = trade_price
            
        # 3. 將計算結果寫回 DB
        self.db.save_strategy_state(strategy, new_pos, avg_price, total_pnl)
        
        return realized_pnl