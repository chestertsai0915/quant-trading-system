# managers/portfolio_manager.py
import logging
import json
import os
import numpy as np
from datetime import datetime, timedelta

STATE_FILE = "portfolio_state.json"

class PortfolioManager:
    def __init__(self, config, db):
        self.config = config
        self.db = db
        self.leverage = self.config.get("risk", "leverage", 1)
        self.rebalance_days = self.config.get("risk", "rebalance_days", 30)
        self.total_strategies = self.config.get("risk", "total_strategies", 1)

        # 狀態儲存: 權重, 上次時間, 以及 [新增] 固定數量
        self.target_weights = {}
        self.base_quantities = {} # { 'StrategyA': 0.05, 'StrategyB': 0.002 }
        self.last_rebalance_time = datetime.min
        self._load_state()

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    data = json.load(f)
                    self.target_weights = data.get("weights", {})
                    self.base_quantities = data.get("base_quantities", {}) # 讀取數量
                    time_str = data.get("last_rebalance_time", "")
                    if time_str:
                        self.last_rebalance_time = datetime.fromisoformat(time_str)
            except Exception as e:
                logging.error(f"[Portfolio] 讀取狀態失敗: {e}")

    def _save_state(self):
        data = {
            "last_rebalance_time": self.last_rebalance_time.isoformat(),
            "weights": self.target_weights,
            "base_quantities": self.base_quantities # 儲存數量
        }
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logging.error(f"[Portfolio] 儲存失敗: {e}")

    def _calculate_sharpe(self, pnl_list):
        if not pnl_list or len(pnl_list) < 2: return 0.0
        returns = np.array(pnl_list)
        std = np.std(returns)
        return (np.mean(returns) / std) if std != 0 else 0.0

    def check_and_rebalance(self, total_equity, current_price):
        """ 
        [核心] 檢查是否需要 Rebalance，若需要則計算新的 '固定數量'
        """
        now = datetime.now()
        
        # 1. 檢查時間 (是否滿 30 天)
        if self.last_rebalance_time != datetime.min:
            if now - self.last_rebalance_time < timedelta(days=self.rebalance_days):
                return # 時間未到，不做事

        logging.info(f"[Portfolio] 30 天週期到達，執行 Rebalance (固定數量模式)...")
        
        # 2. 取得績效數據
        daily_pnls = self.db.get_daily_pnl_history(days=self.rebalance_days)
        all_strategies = list(daily_pnls.keys())

        # 如果是第一次運行 (無歷史)，初始化所有策略
        if not all_strategies:
            # 這裡假設外部會傳入所有策略名稱，或暫時只對有交易過的策略分配
            # 為了簡單，我們假設目前沒策略，等有訊號來再補
            logging.warning("[Portfolio] 無歷史數據，重置時間")
            self.last_rebalance_time = now
            self._save_state()
            return

        # 3. 計算 Sharpe 並排名
        scores = []
        for strat in all_strategies:
            sharpe = self._calculate_sharpe(daily_pnls[strat])
            scores.append((strat, sharpe))
        scores.sort(key=lambda x: x[1], reverse=True) # 高分在前
        
        # 4. 優勝劣汰 (剔除最後 2 名)
        cutoff_index = max(0, len(scores) - 2)
        active_strats = [x[0] for x in scores[:cutoff_index]]
        removed_strats = [x[0] for x in scores[cutoff_index:]]

        # 5. 計算新的固定數量 (Fixed Quantity)
        # 公式: (總資金 / 存活策略數) / 當前幣價
        
        num_active = len(active_strats)
        allocation_per_strat = (total_equity / num_active) if num_active > 0 else 0
        
        # 存活者的固定數量 (真實交易)
        fixed_qty_active = (allocation_per_strat * self.leverage) / current_price
        
        # 被淘汰者的固定數量 (影子模式，假設本金 1000U)
        fixed_qty_shadow = (1000.0 * self.leverage) / current_price

        # 6. 更新狀態
        self.target_weights = {}
        self.base_quantities = {}

        for strat in active_strats:
            self.target_weights[strat] = 1.0 / num_active
            self.base_quantities[strat] = fixed_qty_active
            
        for strat in removed_strats:
            self.target_weights[strat] = 0.0
            self.base_quantities[strat] = fixed_qty_shadow # 即使是影子，也鎖定數量

        self.last_rebalance_time = now
        self._save_state()

        logging.info(f" Rebalance 完成 (價格: {current_price})")
        logging.info(f" 晉級 ({len(active_strats)}): 固定數量 {fixed_qty_active:.4f} BTC")
        logging.info(f"觀察 ({len(removed_strats)}): 固定數量 {fixed_qty_shadow:.4f} BTC")

    def get_strategy_base_quantity(self, strategy_name, total_equity, current_price):
        self.check_and_rebalance(total_equity, current_price)
        
        qty = self.base_quantities.get(strategy_name)
        
        if qty is None:
            # 讀取 Config 裡設定的所有策略名單
            config_strategies = self.config.get("trading", "strategies", [])
            planned_count = len(config_strategies) if config_strategies else 5
            
            #  判斷：這個策略是否在「原始先發名單」內？
            if strategy_name in config_strategies:
                # 是先發名單：給予等權重
                weight = 1.0 / planned_count
                allocated_equity = total_equity * weight
                qty = (allocated_equity * self.leverage) / current_price
                logging.info(f"[Portfolio]  先發策略初始化: {strategy_name} ({weight:.1%}) -> {qty:.4f} BTC")
            else:
                #  是名單外的 (後來加的)：給予影子模式
                weight = 0.0
                qty = (1000.0 * self.leverage) / current_price
                logging.info(f"[Portfolio]  額外策略加入: {strategy_name} (觀察期) -> {qty:.4f} BTC")

            self.base_quantities[strategy_name] = qty
            self.target_weights[strategy_name] = weight
            self._save_state()
            
        return qty, self.target_weights.get(strategy_name, 0.0)

    # update_position_record 保持不變，負責記帳
    def update_position_record(self, strategy, delta_qty, trade_price):
        current_pos, avg_price, total_pnl = self.db.get_strategy_state(strategy)
        new_pos = current_pos + delta_qty
        realized_pnl = 0.0
        
        if current_pos * delta_qty > 0: # 加倉
            total_cost = (current_pos * avg_price) + (delta_qty * trade_price)
            avg_price = total_cost / new_pos
        elif current_pos * delta_qty < 0: # 減倉
            close_qty = abs(delta_qty)
            if current_pos > 0: pnl = (trade_price - avg_price) * close_qty
            else: pnl = (avg_price - trade_price) * close_qty
            realized_pnl = pnl
            total_pnl += realized_pnl
            if abs(new_pos) < 1e-8: new_pos = 0; avg_price = 0
        elif current_pos == 0:
            avg_price = trade_price
            
        self.db.save_strategy_state(strategy, new_pos, avg_price, total_pnl)
        
        # 順便把 base_quantity 也存進 DB (雖然 json 有存，但 DB 備份比較方便)
        # 這需要修改 database.py 的 save_strategy_state 接口，或直接忽略
        # 這裡我們專注於 PnL，Base Qty 主要靠 JSON 維護即可
        
        return realized_pnl