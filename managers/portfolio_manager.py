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
        self.last_rebalance_time = datetime.min
        
        if self.mode == "SHARPE_REBALANCE":
            self.strategy = SharpeRebalanceStrategy(config, db)
        else:
            self.strategy = SharpeRebalanceStrategy(config, db)

        self._load_state()

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    data = json.load(f)
                    self.target_weights = data.get("weights", {})
                    time_str = data.get("last_rebalance_time", "")
                    if time_str:
                        self.last_rebalance_time = datetime.fromisoformat(time_str)
            except Exception as e:
                logging.error(f"[Portfolio] 讀取狀態失敗: {e}")

    def _save_state(self):
        data = {
            "last_rebalance_time": self.last_rebalance_time.isoformat(),
            "weights": self.target_weights
        }
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logging.error(f"[Portfolio] 儲存失敗: {e}")

    def check_and_rebalance(self, total_equity, current_price):
        now = datetime.now()
        is_first_run = (self.last_rebalance_time == datetime.min)

        if not is_first_run:
            if now - self.last_rebalance_time < timedelta(days=self.rebalance_days):
                return 

        logging.info(f"[Portfolio] 週期到達，執行分配...")
        active_strategies_list = self.config.get("trading", "strategies", [])

        result = self.strategy.calculate_rebalance(
            total_equity, current_price, self.rebalance_days, active_strategies_list, is_first_run
        )
        
        if not result: return

        self.target_weights = result["weights"]
        self.last_rebalance_time = now
        self._save_state()

        logging.info(f" 分配完成. 晉級: {result['active']}")

    #  [新增] 獲取所有權重 (用於計算 Global Target)
    def get_all_weights(self, total_equity, current_price):
        """ 確保權重是最新的，並回傳整個字典 """
        self.check_and_rebalance(total_equity, current_price)
        return self.target_weights

    #  [新增] 獲取單一權重 (如果是新策略則初始化)
    def ensure_strategy_weight(self, strategy_name):
        if strategy_name not in self.target_weights:
            is_initial = (len(self.target_weights) == 0)
            weight = self.strategy.get_initial_settings(strategy_name, is_initial)
            self.target_weights[strategy_name] = weight
            self._save_state()
        return self.target_weights[strategy_name]