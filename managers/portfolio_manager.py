import logging
import json
import os
from datetime import datetime, timedelta
from .allocation_strategies import SharpeRebalanceStrategy

STATE_FILE = "portfolio_state.json"

class PortfolioManager:
    def __init__(self, config, db):
        self.config = config
        self.db = db
        self.rebalance_days = self.config.get("risk", "rebalance_days", 30)
        self.mode = self.config.get("risk", "allocation_mode", "SHARPE_REBALANCE")

        self.target_weights = {}
        self.base_quantities = {}
        self.last_rebalance_time = datetime.min
        
        # 初始化策略模組
        if self.mode == "SHARPE_REBALANCE":
            self.strategy = SharpeRebalanceStrategy(config, db)
        else:
            logging.warning(f"[Portfolio] 未知模式 {self.mode}，預設使用 SharpeRebalance")
            self.strategy = SharpeRebalanceStrategy(config, db)

        self._load_state()

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    data = json.load(f)
                    self.target_weights = data.get("weights", {})
                    self.base_quantities = data.get("base_quantities", {})
                    time_str = data.get("last_rebalance_time", "")
                    if time_str:
                        self.last_rebalance_time = datetime.fromisoformat(time_str)
            except Exception as e:
                logging.error(f"[Portfolio] 讀取狀態失敗: {e}")

    def _save_state(self):
        data = {
            "last_rebalance_time": self.last_rebalance_time.isoformat(),
            "weights": self.target_weights,
            "base_quantities": self.base_quantities
        }
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logging.error(f"[Portfolio] 儲存失敗: {e}")

    def check_and_rebalance(self, total_equity, current_price):
        now = datetime.now()
        
        # 判斷是否為「第一次運行」 (看狀態檔是否存在/時間是否為 min)
        is_first_run = (self.last_rebalance_time == datetime.min)

        # 1. 檢查時間 (如果不是第一次，且時間沒到，就跳過)
        if not is_first_run:
            if now - self.last_rebalance_time < timedelta(days=self.rebalance_days):
                return 

        trigger_reason = "初始啟動" if is_first_run else "週期到達"
        logging.info(f"[Portfolio]  {trigger_reason}，呼叫策略 ({self.mode}) 執行分配...")

        #  修正重點：傳入 Config 裡的策略名單
        active_strategies_list = self.config.get("trading", "strategies", [])
        
        # 2. 呼叫策略計算
        result = self.strategy.calculate_rebalance(
            total_equity, 
            current_price, 
            self.rebalance_days,
            active_strategies_list, # <--- 只傳入 Config 有的
            is_first_run            # <--- 告訴策略這是第一次，請強制初始化
        )
        
        if not result:
            logging.warning("[Portfolio] 策略回傳無數據，稍後重試")
            return

        # 3. 更新狀態
        self.target_weights = result["weights"]
        self.base_quantities = result["quantities"]
        self.last_rebalance_time = now
        self._save_state()

        logging.info(f" 分配完成 (價格: {current_price})")
        logging.info(f"   晉級: {result['active']}")
        logging.info(f"   觀察: {result['removed']}")

    def get_strategy_base_quantity(self, strategy_name, total_equity, current_price):
        """ 對外接口 """
        self.check_and_rebalance(total_equity, current_price)
        
        qty = self.base_quantities.get(strategy_name)
        
        # 如果是新加入的策略 (Config 有，但 State 裡還沒算到)
        if qty is None:
            # 判斷系統是否還在初始階段
            is_system_initial = (len(self.target_weights) == 0)
            
            weight, qty = self.strategy.get_initial_settings(
                strategy_name, total_equity, current_price, is_system_initial
            )
            
            self.base_quantities[strategy_name] = qty
            self.target_weights[strategy_name] = weight
            self._save_state()
            
        return qty, self.target_weights.get(strategy_name, 0.0)

    def update_position_record(self, strategy, delta_qty, trade_price):
        # 這部分保持不變，因為它是純 DB 操作
        current_pos, avg_price, total_pnl = self.db.get_strategy_state(strategy)
        new_pos = current_pos + delta_qty
        realized_pnl = 0.0
        
        if current_pos * delta_qty > 0: 
            total_cost = (current_pos * avg_price) + (delta_qty * trade_price)
            avg_price = total_cost / new_pos
        elif current_pos * delta_qty < 0: 
            close_qty = abs(delta_qty)
            if current_pos > 0: pnl = (trade_price - avg_price) * close_qty
            else: pnl = (avg_price - trade_price) * close_qty
            realized_pnl = pnl
            total_pnl += realized_pnl
            if abs(new_pos) < 1e-8: new_pos = 0; avg_price = 0
        elif current_pos == 0:
            avg_price = trade_price
            
        self.db.save_strategy_state(strategy, new_pos, avg_price, total_pnl)
        return realized_pnl