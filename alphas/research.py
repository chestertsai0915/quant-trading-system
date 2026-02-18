# research.py
import pandas as pd
import numpy as np
import sys
import os
import importlib.util

sys.path.append(os.getcwd())
try:
    from backtesting.pure_engine import PureBacktestEngine
    from backtesting.data_factory import BacktestDataFactory
except ImportError:
    pass

class ResearchEnvironment:
    def __init__(self, strategy_file, symbol="BTCUSDT", interval="1h", split_date="2025-06-01"):
        self.split_date = pd.to_datetime(split_date)
        
        # 1. 載入策略
        self.strategy_func, self.requirements = self._load_strategy(strategy_file)
        print(f"[Research] 載入策略完成，需求特徵: {self.requirements}")

        # 2. 載入數據 (只做一次)
        print("[Research] 正在載入 IS 數據...")
        factory = BacktestDataFactory(skip_backup=True)
        
        # 這裡直接用策略裡寫死的 requirements 去撈資料
        full_df = factory.prepare_features(
            symbol, interval, 
            feature_ids=self.requirements, 
            end_time=split_date
        )
        
        self.df_is = full_df.reset_index(drop=True)
        print(f"[Research] 數據準備完成: {len(self.df_is)} 筆")

    def _load_strategy(self, filepath):
        if not os.path.exists(filepath): raise FileNotFoundError(filepath)
        module_name = os.path.basename(filepath).replace(".py", "")
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        reqs = getattr(module, 'requirements', [])
        return module.run, reqs

    def evaluate(self, params):
        """
        傳入參數 -> 跑回測 -> 回傳 Sharpe
        """
        # 包裝策略，注入參數
        def strategy_wrapper(row, account):
            return self.strategy_func(row, account, params=params)

        # 執行回測 (Next Open 模式，確保精準)
        engine = PureBacktestEngine(self.df_is, initial_balance=10000, mode='next_open')
        engine.run(strategy_wrapper)
        
        equity_curve = engine.account.equity_curve
        if len(equity_curve) < 2: return -999.0

        equity = pd.Series([r['equity'] for r in equity_curve])
        pct = equity.pct_change().dropna()
        
        if pct.std() == 0: return 0.0
        
        sharpe = (pct.mean() / pct.std()) * np.sqrt(365 * 24)
        total_return = (equity.iloc[-1] / 10000) - 1
        
        return {
            "sharpe": sharpe,
            "return": total_return
        }