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
        
        # 從 Config 讀取模式
        self.mode = self.config.get("risk", "allocation_mode", "EQUAL_WEIGHT")
        self.rebalance_days = self.config.get("risk", "rebalance_days", 30)
        self.total_strategies = self.config.get("risk", "total_strategies", 1)

        # 初始化狀態 (從檔案讀取)
        self.target_weights = {}
        self.last_rebalance_time = datetime.min
        self._load_state()

    # ==========================
    #  持久化存儲 (Persistence)
    # ==========================
    def _load_state(self):
        """ 從 JSON 檔案讀取上次的權重與時間 """
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    data = json.load(f)
                    self.target_weights = data.get("weights", {})
                    time_str = data.get("last_rebalance_time", "")
                    if time_str:
                        self.last_rebalance_time = datetime.fromisoformat(time_str)
                logging.info(f"[Portfolio] 狀態載入成功。上次 Rebalance: {self.last_rebalance_time}")
            except Exception as e:
                logging.error(f"[Portfolio] 讀取狀態檔失敗，重置為預設值: {e}")
        else:
            logging.info("[Portfolio] 無狀態檔，將初始化為全新狀態。")

    def _save_state(self):
        """ 將當前權重與時間寫入 JSON """
        data = {
            "last_rebalance_time": self.last_rebalance_time.isoformat(),
            "weights": self.target_weights
        }
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(data, f, indent=4)
            logging.info("[Portfolio] 狀態已儲存至 portfolio_state.json")
        except Exception as e:
            logging.error(f"[Portfolio] 狀態儲存失敗: {e}")

    # ==========================
    #  Sharpe 計算邏輯
    # ==========================
    def _calculate_sharpe(self, pnl_list):
        if not pnl_list or len(pnl_list) < 2:
            return 0.0
        returns = np.array(pnl_list)
        mean_ret = np.mean(returns)
        std_ret = np.std(returns)
        return (mean_ret / std_ret) if std_ret != 0 else 0.0

    def check_and_rebalance(self):
        """ 檢查是否滿足週期，並執行 Rebalance """
        now = datetime.now()
        
        # 檢查時間：如果是 datetime.min 代表第一次跑，直接觸發
        if self.last_rebalance_time != datetime.min:
            if now - self.last_rebalance_time < timedelta(days=self.rebalance_days):
                return # 時間還沒到

        logging.info(f"[Portfolio]  週期 ({self.rebalance_days}天) 到達，執行 Sharpe Rebalance...")

        # 1. 取得數據 (過去 N 天日損益)
        daily_pnls = self.db.get_daily_pnl_history(days=self.rebalance_days)
        all_strategies = list(daily_pnls.keys())

        # 如果沒資料，先暫時不做改變 (或初始化)
        if not all_strategies:
            logging.warning("[Portfolio] 無歷史數據，維持現狀")
            self.last_rebalance_time = now # 更新時間以免一直重複觸發
            self._save_state()
            return

        # 2. 計算 Sharpe 並排名
        scores = []
        for strat in all_strategies:
            sharpe = self._calculate_sharpe(daily_pnls[strat])
            scores.append((strat, sharpe))
        
        # 由高到低排序
        scores.sort(key=lambda x: x[1], reverse=True)
        
        # 3. 制定規則 (剔除最後 2 名)
        cutoff_index = max(0, len(scores) - 2)
        active_strats = [x[0] for x in scores[:cutoff_index]]
        removed_strats = [x[0] for x in scores[cutoff_index:]]

        # 4. 分配新權重
        new_weights = {}
        weight_per_strat = 1.0 / len(active_strats) if active_strats else 0
        
        for strat in active_strats:
            new_weights[strat] = weight_per_strat
        for strat in removed_strats:
            new_weights[strat] = 0.0

        # 5. 更新狀態並存檔
        self.target_weights = new_weights
        self.last_rebalance_time = now
        self._save_state() # <--- 關鍵：寫入硬碟

        logging.info(f"Rebalance 完成！")
        logging.info(f" 晉級: {active_strats} (權重: {weight_per_strat:.2f})")
        logging.info(f" 觀察: {removed_strats}")

    # ==========================
    #  主要對外接口
    # ==========================
    def calculate_allocation(self, strategy_name, total_wallet_balance):
        
        # 模式 A: Sharpe Rebalance (優勝劣汰)
        if self.mode == "SHARPE_REBALANCE":
            # 每次分配前檢查是否需要調整權重
            self.check_and_rebalance()
            
            # 從記憶體(或剛載入的檔案)取得權重
            # 如果是新策略不在名單內，預設給 0 (觀察期)
            weight = self.target_weights.get(strategy_name, 0.0)
            
            # 若權重為 0，回傳 0 (讓 TradeManager 進入影子模式)
            if weight == 0:
                return 0
                
            return total_wallet_balance * weight * self.leverage

        # 模式 B: Equal Weight (簡單等權)
        elif self.mode == "EQUAL_WEIGHT":
            # 簡單邏輯：總資金 / 設定的策略總數
            if self.total_strategies > 0:
                return (total_wallet_balance / self.total_strategies) * self.leverage
            return 0
            
        # 預設
        return 0

    def update_position_record(self, strategy, delta_qty, trade_price):
        """ 這裡保持不變，負責呼叫 DB 存損益 """
        # ... (同之前的實作) ...
        # (這裡省略以節省篇幅，邏輯是計算 avg_price, pnl 並呼叫 db.save_strategy_state)
        # 這裡的邏輯不需要改動，因為它只負責會計
        
        # 為了完整性，把上一版的 update_position_record 貼在下方 (或保留您現有的)
        current_pos, avg_price, total_pnl = self.db.get_strategy_state(strategy)
        new_pos = current_pos + delta_qty
        realized_pnl = 0.0
        
        if current_pos * delta_qty > 0: # 加倉
            total_cost = (current_pos * avg_price) + (delta_qty * trade_price)
            avg_price = total_cost / new_pos
        elif current_pos * delta_qty < 0: # 減倉
            close_qty = abs(delta_qty)
            if current_pos > 0:
                pnl = (trade_price - avg_price) * close_qty
            else:
                pnl = (avg_price - trade_price) * close_qty
            realized_pnl = pnl
            total_pnl += realized_pnl
            if abs(new_pos) < 1e-8:
                new_pos = 0; avg_price = 0
        elif current_pos == 0:
            avg_price = trade_price
            
        self.db.save_strategy_state(strategy, new_pos, avg_price, total_pnl)
        return realized_pnl