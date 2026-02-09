from .base_strategy import BaseStrategy
import indicators as ind
import numpy as np
import pandas as pd

class QQQ_price(BaseStrategy):
    def __init__(self):
        super().__init__(name="Strategy13_QQQ_Wavelet_Trend")
        
        # --- 策略參數 ---
        
        self.lookback_window = 400  # 歷史分位數視窗
        
        
        self.long_th = 0.7          # 進場分位數 (0.7)
        self.exit_th = 0.1          # 出場分位數 (0.1)
        
        

    def generate_signal(self):
        # 1. 檢查特徵是否存在 (防呆)
        if 'QQQ_Wavelet' not in self.kline_data.columns:
            return None
            
        # 2. 取出特徵序列
        # 這已經是 DataManager 幫你 merge 好的 (小時線上的特徵)
        wavelet_series = self.kline_data['QQQ_Wavelet']
       
        # 3. 計算動態閾值 (Rolling Quantile)
        # 直接對 Series 操作，超快
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