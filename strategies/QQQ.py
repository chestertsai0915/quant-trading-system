from .base_strategy import BaseStrategy
import pandas as pd
import numpy as np

class QQQ_price(BaseStrategy):
    def __init__(self):
        super().__init__()
        
        # --- 策略參數 ---
        self.target_source = 'us_stock_qqq'
        self.wavelet_window = 120   # 小波計算視窗 (日線)
        self.output_col = 'A_mean'  # 取出的特徵
        
        # 【關鍵差異】
        # 這裡的 window = 400 是 "400 小時" (約 16.6 天)
        # 我們的目標是：在小時線上，對著 "已經廣播(ffill)過來的日線數據" 做滾動統計
        self.lookback_window = 400  
        
        self.long_th = 0.7          # 進場分位數
        self.exit_th = 0.1          # 出場分位數

    def generate_signal(self):
        # ==========================================
        # 1. 定義需要的特徵 ID
        # ==========================================
        
        # 只請求 "原始小波數值" (WaveletFeature_V1)
        # Feature Store 會算出 QQQ 日線的小波值，並自動對齊(ffill)到我們的小時線
        # ID: wavelet_{source}_{wav_win}_{col}_v1
        fid_val = f"wavelet_{self.target_source}_{self.wavelet_window}_{self.output_col}_v1"
        
        # ==========================================
        # 2. 向 Feature Store 請求數據
        # ==========================================
        df = self.load_features([fid_val])
        
        # 安全檢查
        # 注意：雖然我們只滾動 400 小時，但因為原始特徵是 wavelet(120日)，
        # 所以數據源頭需要很長的歷史資料。
        if df.empty or len(df) < self.lookback_window + 50:
            return None

        if fid_val not in df.columns:
            return None

        # ==========================================
        # 3. 策略層計算 (Strategy-Side Calculation)
        # ==========================================
        # 這裡我們 "犯規" 了：不使用預定義的 Wavelet_Quantile 特徵，
        # 而是直接在策略裡算，為了復刻 "小時線滾動日線數據" 的特殊 Alpha。
        
        wavelet_series = df[fid_val] # 這是一條已經被廣播成小時線的序列 (每24根數值一樣)
        
        # 計算動態閾值 (Rolling Quantile on Hourly Broadcasted Data)
        long_threshold_series = wavelet_series.rolling(window=self.lookback_window).quantile(self.long_th)
        exit_threshold_series = wavelet_series.rolling(window=self.lookback_window).quantile(self.exit_th)
        
        # ==========================================
        # 4. 交易邏輯
        # ==========================================
        
        curr_val = wavelet_series.iloc[-1]
        curr_long_th = long_threshold_series.iloc[-1]
        curr_exit_th = exit_threshold_series.iloc[-1]
        
        # 檢查 NaN (剛開始滾動時會是空值)
        if np.isnan(curr_long_th) or np.isnan(curr_exit_th):
            return None

        # 邏輯判斷
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