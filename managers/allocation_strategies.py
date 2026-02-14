from abc import ABC, abstractmethod
import numpy as np
import logging

class BaseAllocationStrategy(ABC):
    """
    資金分配策略介面
    """
    def __init__(self, config, db):
        self.config = config
        self.db = db
        self.leverage = self.config.get("risk", "leverage", 1)

    @abstractmethod
    def calculate_rebalance(self, total_equity, current_price, lookback_days, active_strategies_list, is_first_run):
        """
        Args:
            active_strategies_list: 從 Config 讀入的有效策略名單
            is_first_run: 是否為系統重置後的第一次運行
        """
        pass

    @abstractmethod
    def get_initial_settings(self, strategy_name, total_equity, current_price, is_system_initial_phase):
        pass

# =========================================================
#  具體實作: Sharpe Rebalance
# =========================================================
class SharpeRebalanceStrategy(BaseAllocationStrategy):
    
    def _calculate_sharpe(self, pnl_list):
        if not pnl_list or len(pnl_list) < 2: return 0.0
        returns = np.array(pnl_list)
        std = np.std(returns)
        return (np.mean(returns) / std) if std != 0 else 0.0

    def calculate_rebalance(self, total_equity, current_price, lookback_days, active_strategies_list, is_first_run):
        
        #  修正 1: 如果是第一次運行 (JSON被刪除)，強制執行等權重初始化
        if is_first_run:
            logging.info("[Alloc] 檢測到初始狀態 (First Run)，強制執行等權重分配...")
            return self._apply_equal_weight(total_equity, current_price, active_strategies_list)

        # 1. 取得 DB 歷史數據
        daily_pnls = self.db.get_daily_pnl_history(days=lookback_days)
        
        #  修正 2: 只保留 Config 裡有的策略 (過濾掉 DB 裡的幽靈策略)
        valid_strategies = [s for s in daily_pnls.keys() if s in active_strategies_list]
        
        # 還有一些在 Config 裡但 DB 沒資料的新策略
        new_strategies = [s for s in active_strategies_list if s not in daily_pnls]

        # 如果完全沒有效數據，也退回等權重
        if not valid_strategies and not new_strategies:
             logging.warning("[Alloc] 無有效歷史數據，執行等權重分配")
             return self._apply_equal_weight(total_equity, current_price, active_strategies_list)

        # 2. 計算 Sharpe 並排名 (只針對有數據的)
        scores = []
        for strat in valid_strategies:
            sharpe = self._calculate_sharpe(daily_pnls[strat])
            scores.append((strat, sharpe))
        
        scores.sort(key=lambda x: x[1], reverse=True) # 高分在前
        
        # 3. 優勝劣汰 (剔除最後 2 名)
        # 注意：如果總策略數太少，就不剔除
        cutoff_index = max(0, len(scores) - 2)
        
        # 晉級名單
        active_strats = [x[0] for x in scores[:cutoff_index]]
        # 淘汰名單
        removed_strats = [x[0] for x in scores[cutoff_index:]]
        
        # 新策略 (沒數據) 預設先進入淘汰組(觀察期)，或依您需求改成晉級組
        # 這裡採取嚴格模式：沒戰績先蹲觀察期
        for ns in new_strategies:
            removed_strats.append(ns)

        # 4. 計算數量
        num_active = len(active_strats)
        allocation_per_strat = (total_equity / num_active) if num_active > 0 else 0
        
        fixed_qty_active = (allocation_per_strat * self.leverage) / current_price
        fixed_qty_shadow = (1000.0 * self.leverage) / current_price # 模擬本金 1000U

        # 5. 組裝
        new_weights = {}
        new_quantities = {}

        for strat in active_strats:
            new_weights[strat] = 1.0 / num_active
            new_quantities[strat] = fixed_qty_active
            
        for strat in removed_strats:
            new_weights[strat] = 0.0
            new_quantities[strat] = fixed_qty_shadow

        return {
            "weights": new_weights,
            "quantities": new_quantities,
            "active": active_strats,
            "removed": removed_strats
        }

    def _apply_equal_weight(self, total_equity, current_price, strategies_list):
        """ 輔助函數：執行全體等權重 """
        count = len(strategies_list)
        if count == 0: return None
        
        weight = 1.0 / count
        allocation = total_equity * weight
        qty = (allocation * self.leverage) / current_price
        
        weights = {s: weight for s in strategies_list}
        quantities = {s: qty for s in strategies_list}
        
        return {
            "weights": weights,
            "quantities": quantities,
            "active": strategies_list,
            "removed": []
        }

    def get_initial_settings(self, strategy_name, total_equity, current_price, is_system_initial_phase):
        # 初始化單一策略時的邏輯 (通常是中途加入)
        if is_system_initial_phase:
            # 這是理論上不會發生，因為會被 _apply_equal_weight 接管
            # 但為了防呆：
            qty = (1000.0 * self.leverage) / current_price
            return 0.0, qty
        else:
            # 中途加入 -> 影子模式
            weight = 0.0
            qty = (1000.0 * self.leverage) / current_price
            logging.info(f"[Alloc]  新策略 {strategy_name} 加入 -> 進入觀察期 (Shadow)")
            return weight, qty