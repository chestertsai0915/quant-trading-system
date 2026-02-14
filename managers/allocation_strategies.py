from abc import ABC, abstractmethod
import numpy as np
import logging

class BaseAllocationStrategy(ABC):
    def __init__(self, config, db):
        self.config = config
        self.db = db
        self.leverage = self.config.get("risk", "leverage", 1)

    @abstractmethod
    def calculate_rebalance(self, total_equity, current_price, lookback_days, active_strategies_list, is_first_run):
        pass

    @abstractmethod
    def get_initial_settings(self, strategy_name, is_system_initial_phase):
        pass

class SharpeRebalanceStrategy(BaseAllocationStrategy):
    
    def _calculate_sharpe(self, pnl_list):
        if not pnl_list or len(pnl_list) < 2: return 0.0
        returns = np.array(pnl_list)
        std = np.std(returns)
        return (np.mean(returns) / std) if std != 0 else 0.0

    def calculate_rebalance(self, total_equity, current_price, lookback_days, active_strategies_list, is_first_run):
        
        # 1. 初始狀態
        if is_first_run:
            return self._apply_equal_weight(active_strategies_list)

        # 2. 獲取數據
        daily_pnls = self.db.get_daily_pnl_history(days=lookback_days)
        valid_strategies = [s for s in daily_pnls.keys() if s in active_strategies_list]
        new_strategies = [s for s in active_strategies_list if s not in daily_pnls]

        if not valid_strategies and not new_strategies:
             return self._apply_equal_weight(active_strategies_list)

        # 3. Sharpe 排名
        scores = []
        for strat in valid_strategies:
            sharpe = self._calculate_sharpe(daily_pnls[strat])
            scores.append((strat, sharpe))
        scores.sort(key=lambda x: x[1], reverse=True)
        
        # 4. 淘汰機制 (末位淘汰)
        cutoff_index = max(0, len(scores) - 2)
        active_strats = [x[0] for x in scores[:cutoff_index]]
        removed_strats = [x[0] for x in scores[cutoff_index:]]
        
        for ns in new_strategies:
            removed_strats.append(ns) 

        # 5. [純權重計算]
        new_weights = {}
        num_active = len(active_strats)
        weight_per_strat = 1.0 / num_active if num_active > 0 else 0
        
        for strat in active_strats:
            new_weights[strat] = weight_per_strat
            
        for strat in removed_strats:
            new_weights[strat] = 0.0 # 觀察期權重為 0

        return {
            "weights": new_weights,
            "active": active_strats,
            "removed": removed_strats
        }

    def _apply_equal_weight(self, strategies_list):
        count = len(strategies_list)
        if count == 0: return None
        weight = 1.0 / count
        weights = {s: weight for s in strategies_list}
        return {
            "weights": weights,
            "active": strategies_list,
            "removed": []
        }

    def get_initial_settings(self, strategy_name, is_system_initial_phase):
        # 只回傳權重，數量由 TradeManager 動態算
        if is_system_initial_phase:
            return 0.0 # 會由 rebalance 接管
        else:
            return 0.0 # 中途加入預設 0 (Shadow)