from .base_strategy import BaseStrategy
import indicators as ind
import numpy as np
import pandas as pd

class SentimentStrategyV3(BaseStrategy):
    def __init__(self):
        super().__init__(name="Strategy11_Trend_ZScore")
        
        # --- 策略參數 ---
        self.rolling_window = 1000  # 滾動視窗 (1000小時)
        self.z_window = 100         # Z-Score 的均線週期 (你的代碼寫 rolling(100).mean)
        
        self.ratio_th = 0.8         # BTC Ratio 分位數閾值
        self.z_score_th = 0.7       # Z-Score 分位數閾值
        
        

    def generate_signal(self):
        # 1. 安全檢查：確保 DataManager 給我的資料夠長
        # 如果資料少於 1000 筆，rolling(1000) 會算出 NaN，所以直接不交易
        if len(self.kline_data) < self.rolling_window:
            return None

        # 2. 複製資料 (避免汙染原始資料)
        df = self.kline_data.copy()

        # 3. 確保外部數據欄位存在 (防呆)
        if 'google_trends_BTC' not in df.columns or 'google_trends_crypto' not in df.columns:
            return None

        # ==========================================
        # 向量化計算 (Vectorization) - 整欄一起算
        # ==========================================

        # A. 計算 Sentiment Ratio 序列
        # 用 replace(0, 1) 防止分母為 0
        ratio_series = df['google_trends_BTC'] / df['google_trends_crypto'].replace(0, 1)
        
        # B. 計算 Ratio 的動態閾值 (Rolling Quantile)
        # 這行會算出「過去 1000 小時的 80% 分位數」
        ratio_quantile = ratio_series.rolling(window=self.rolling_window).quantile(self.ratio_th)
        
        # C. 計算價格 Z-Score 序列
        close = df['close']
        # Z = (價格 - 均線) / 標準差
        z_score_series = (close - close.rolling(self.z_window).mean()) / close.rolling(self.z_window).std()
        
        # D. 計算 Z-Score 的動態閾值 (Rolling Quantile)
        z_score_quantile = z_score_series.rolling(window=self.rolling_window).quantile(self.z_score_th)

        # ==========================================
        #  取出「當下」數值 (最後一筆)
        # ==========================================
        
        current_ratio = ratio_series.iloc[-1]
        current_ratio_th = ratio_quantile.iloc[-1]
        
        curr_z_score = z_score_series.iloc[-1]
        curr_z_th = z_score_quantile.iloc[-1]

        # 檢查是否為 NaN (剛啟動資料不足時可能會發生)
        if np.isnan(current_ratio_th) or np.isnan(curr_z_th):
            return None

        # ==========================================
        #  進出場判斷
        # ==========================================
        
        # 進場: 兩個指標都強於歷史高標
        long_condition = (current_ratio > current_ratio_th) and (curr_z_score > curr_z_th)
        
        # 出場: 兩個指標都轉弱
        exit_condition = (current_ratio < current_ratio_th) and (curr_z_score < curr_z_th)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'Ratio({current_ratio:.2f})>Th({current_ratio_th:.2f}) & Z({curr_z_score:.2f})>Th({curr_z_th:.2f})'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'Trend_Weakened'
            }
            
        return None