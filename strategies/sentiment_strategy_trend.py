from .base_strategy import BaseStrategy
import pandas as pd
import numpy as np

class SentimentStrategyV3(BaseStrategy):
    def __init__(self):
        super().__init__()
        
        # --- 策略參數 ---
        self.rolling_window = 1000  # 滾動視窗 (1000小時)
        self.z_window = 100         # Z-Score 的均線週期
        
        self.ratio_th = 0.8         # BTC Ratio 分位數閾值
        self.z_score_th = 0.7       # Z-Score 分位數閾值

    def generate_signal(self):
        # ==========================================
        # 1. 定義需要的特徵 ID
        # ==========================================
        
        # A. Google Trends 原始數據 (只拿 Raw Data)
        # ID: google_trends_raw_{metric}_v1
        fid_btc = "google_trends_raw_google_trends_BTC_v1"
        fid_crypto = "google_trends_raw_google_trends_crypto_v1"
        
        # B. Z-Score 部分 (這部分是標準高頻計算，可以直接用 Feature Store 算好的)
        # 1. Z-Score 數值
        fid_z = f"zscore_close_{self.z_window}_v1"
        # 2. Z-Score 閾值 (Rolling Quantile)
        fid_z_th = f"zscore_quantile_{self.z_window}_{self.rolling_window}_{self.z_score_th}_v1"

        # ==========================================
        # 2. 向 Feature Store 請求數據
        # ==========================================
        # 這裡拿到的 df，BTC 和 Crypto 已經被 ffill 到小時線了
        df = self.load_features([fid_btc, fid_crypto, fid_z, fid_z_th])
        
        # 安全檢查
        if df.empty or len(df) < self.rolling_window + 50:
            return None

        required_cols = [fid_btc, fid_crypto, fid_z, fid_z_th]
        if not all(col in df.columns for col in required_cols):
            return None

        # ==========================================
        # 3. 策略層計算 (Strategy-Side Calculation)
        # ==========================================
        # 為了復刻 "先廣播 -> 再計算" 的邏輯，我們在這裡算 Ratio
        
        # A. 計算 Ratio (Hourly Series)
        # 這兩條 series 其實是階梯狀的 (每24小時變一次)，
        # 但我們在小時頻率上相除，得到的 ratio 也是階梯狀的。
        btc_series = df[fid_btc]
        crypto_series = df[fid_crypto]
        
        # replace(0, 1) 避免除以零
        ratio_series = btc_series / crypto_series.replace(0, 1)
        
        # B. 計算 Ratio 的動態閾值 (Rolling on Hourly Data)
        # 這一步就是你要的關鍵：對著 "小時級別的階梯狀 Ratio" 做 1000 小時的 rolling
        ratio_quantile_series = ratio_series.rolling(window=self.rolling_window).quantile(self.ratio_th)
        
        # ==========================================
        # 4. 交易邏輯
        # ==========================================
        
        # 取當前值
        curr_ratio = ratio_series.iloc[-1]
        curr_ratio_th = ratio_quantile_series.iloc[-1] # 手算的閾值
        
        curr_z = df[fid_z].iloc[-1]       # Store 算的 Z
        curr_z_th = df[fid_z_th].iloc[-1] # Store 算的 Z 閾值

        # 檢查 NaN
        if np.isnan(curr_ratio_th) or np.isnan(curr_z_th):
            return None

        # 進場: Ratio 與 Z-Score 都強於歷史高標
        long_condition = (curr_ratio > curr_ratio_th) and (curr_z > curr_z_th)
        
        # 出場: 兩個指標都轉弱
        exit_condition = (curr_ratio < curr_ratio_th) and (curr_z < curr_z_th)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'Ratio({curr_ratio:.2f})>Th({curr_ratio_th:.2f}) & Z({curr_z:.2f})>Th({curr_z_th:.2f})'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'Trend_Weakened'
            }
            
        return None