from .base_strategy import BaseStrategy
import indicators as ind
import numpy as np
import pandas as pd

class QQQ_price(BaseStrategy):
    def __init__(self):
        super().__init__(name="Strategy13_QQQ_Wavelet_Trend")
        
        # --- 策略參數 ---
        self.lookback_window = 400  # 歷史分位數視窗 (注意：這是指 400 根 K 線)
        
        self.long_th = 0.7          # 進場分位數 (0.7)
        self.exit_th = 0.1          # 出場分位數 (0.1)
        

    def generate_signal(self):
        # ==========================================
        # 1. 【關鍵修改】主動混合外部特徵
        # ==========================================
        # 告訴系統：我要把 'us_stock_qqq' 資料源裡的 'QQQ_Wavelet' 欄位併進來
        # 注意：這裡會回傳一個新的 df，包含了原始 K 線 + QQQ 資料
        df = self.enrich_data_with_external(
            source_name='us_stock_qqq',
            feature_cols=['QQQ_Wavelet'] 
        )
        if 'QQQ_Wavelet' not in df.columns:
            # logging.warning(f"策略 {self.name}: 缺少 QQQ_Wavelet 數據，跳過")
            return None
        # 檢查特徵是否存在 (防呆)
        # 注意：現在要檢查的是 df，而不是 self.kline_data
        if 'QQQ_Wavelet' not in df.columns:
            return None
        
        # ==========================================
        # 2. 以下邏輯與原本完全相同 (只改變數來源為 df)
        # ==========================================
        
        # 取出特徵序列 (已經對齊到小時線了)
        wavelet_series = df['QQQ_Wavelet']
       
        # 3. 計算動態閾值 (Rolling Quantile)
        # 這裡是對 "混合後的序列" 做 rolling，代表 "過去 400 個小時" 的分位數
        long_threshold_series = wavelet_series.rolling(self.lookback_window).quantile(self.long_th)
        exit_threshold_series = wavelet_series.rolling(self.lookback_window).quantile(self.exit_th)
        
        # 4. 取當前值
        curr_val = wavelet_series.iloc[-1]
        curr_long_th = long_threshold_series.iloc[-1]
        curr_exit_th = exit_threshold_series.iloc[-1]
       
        # 5. 邏輯判斷
        if curr_val > curr_long_th:
             return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'QQQ_Wavelet_Strong ({curr_val:.2f} > {curr_long_th:.2f})'
            }
            
        elif curr_val < curr_exit_th:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'QQQ_Wavelet_Weak ({curr_val:.2f} < {curr_exit_th:.2f})'
            }
            
        return None