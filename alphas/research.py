import pandas as pd
import numpy as np
import sys
import os
import importlib.util

# 引用模組
sys.path.append(os.getcwd())
try:
    from backtesting.pure_engine import PureBacktestEngine
    from backtesting.data_factory import BacktestDataFactory
except ImportError:
    pass

class ResearchEnvironment:
    def __init__(self, strategy_file, symbol="BTCUSDT", interval="1h", split_date="2025-06-01"):
        """
        初始化研發環境：載入策略、準備 IS 數據
        """
        self.split_date = pd.to_datetime(split_date)
        
        # 1. 載入策略模組 (為了取得 requirements)
        self.strategy_func, self.requirements = self._load_strategy(strategy_file)
        print(f"[Research] 載入策略: {os.path.basename(strategy_file)}")
        print(f"[Research] 特徵需求: {self.requirements}")

        # 2. 準備數據 (只做一次)
        print("[Research] 正在載入 In-Sample 數據 (這可能需要幾秒鐘)...")
        factory = BacktestDataFactory() # skip_backup=True
        
        # 這裡我們先撈取稍多一點的數據，然後再切
        # 實務上建議 end_time 設為 split_date，確保完全沒碰到 OS
        full_df = factory.prepare_features(symbol, interval, feature_ids=self.requirements, end_time=split_date)
        
        # 強制確保只保留 split_date 之前的數據
        self.df_is = full_df[full_df['datetime'] < self.split_date].reset_index(drop=True)
        
        print(f"[Research] IS 數據準備完成: {len(self.df_is)} 筆 (截止 {self.df_is['datetime'].max()})")
        print("-" * 50)

    def _load_strategy(self, filepath):
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"找不到檔案: {filepath}")
        module_name = os.path.basename(filepath).replace(".py", "")
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        reqs = getattr(module, 'requirements', [])
        return module.run, reqs

    def evaluate(self, params):
        """
        核心函數：傳入一組參數，回傳這組參數的績效分數
        """
        # 1. 包裝策略函數，注入參數
        # 這是為了讓 pure_engine 可以呼叫 func(row, account) 而不需要知道 params
        def strategy_wrapper(row, account):
            return self.strategy_func(row, account, params=params)

        # 2. 執行極速回測
        # engine 初始化很快，因為 df 已經在記憶體裡了
        engine = PureBacktestEngine(self.df_is, initial_balance=10000)
        engine.run(strategy_wrapper)
        
        # 3. 計算核心指標 (只算 Sharpe 或 Return 用於比較)
        equity = pd.Series([r['equity'] for r in engine.account.equity_curve])
        
        if len(equity) < 2:
            return -999.0 # 沒交易或爆倉

        # 計算 Sharpe
        pct_change = equity.pct_change().dropna()
        if pct_change.std() == 0:
            return 0.0
            
        sharpe = (pct_change.mean() / pct_change.std()) * np.sqrt(365 * 24)
        
        # 計算總報酬
        total_return = (equity.iloc[-1] / 10000) - 1
        
        return {
            "sharpe": sharpe,
            "return": total_return,
            "final_balance": equity.iloc[-1]
        }