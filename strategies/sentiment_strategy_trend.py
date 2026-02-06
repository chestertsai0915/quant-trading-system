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
        
        # --- 內部狀態 (用於儲存 Google Trend 歷史) ---
        self.ratio_history = []     # 存儲 btc_ratio 的歷史數據

    def generate_signal(self):
        # 1. 數據長度檢查
        # Z-Score(100) + Rolling(1000) = 1100
        # 因為這需要很長的歷史數據，我們盡量在 main.py 抓多一點
        if len(self.kline_data) < 1000:
            return None

        # 2. 獲取 Google Trends 數據
        # 我們預期 external_data 會有 'Bitcoin' 和 'crypto' 兩個 key
        btc_vol = self.external_data.get('BTC', 0)
        crypto_vol = self.external_data.get('crypto', 1) # 避免分母為 0
        
        # 若抓不到數據 (0)，先跳過
        if crypto_vol == 0: crypto_vol = 1 
        
        # ==========================================
        # 因子計算
        # ==========================================

        # A. 計算 BTC Ratio (當前值)
        # btc_ratio = BTC / crypto
        current_ratio = btc_vol / crypto_vol
        
        # 將數據存入歷史緩衝區，並保持長度不超過 1000
        self.ratio_history.append(current_ratio)
        if len(self.ratio_history) > self.rolling_window:
            self.ratio_history.pop(0)

        # B. 計算 Price Z-Score (歷史序列)
        close = self.kline_data['close'].values
        # data['price_z_score'] = (close - mean(100)) / std(100)
        z_score_series = ind.AlphaLibrary.calc_z_score(close, self.z_window)
        
        # ==========================================
        #  計算滾動分位數 (Thresholds)
        # ==========================================
        
        # 1. BTC Ratio 的 80% 分位數
        # 注意：剛開始跑的時候，歷史數據不足 1000 筆，分位數會基於現有數據計算
        if len(self.ratio_history) < 20: # 數據太少先不判斷
            return None
            
        ratio_quantile_val = pd.Series(self.ratio_history).quantile(self.ratio_th)
        
        # 2. Z-Score 的 70% 分位數
        # 使用 rolling(1000).quantile(0.7)
        # 這裡直接用 indicators 算好的工具
        z_score_th_series = ind.AlphaLibrary.calc_rolling_quantile(z_score_series, self.rolling_window, self.z_score_th)
        
        # ==========================================
        #  獲取當前數值
        # ==========================================
        
        curr_z_score = z_score_series[-1]
        curr_z_th = z_score_th_series[-1]
        
        # Debug Log
        # print(f"[{self.name}] Ratio:{current_ratio:.2f}(>{ratio_quantile_val:.2f}) | Z:{curr_z_score:.2f}(>{curr_z_th:.2f})")

        # ==========================================
        #  進出場邏輯
        # ==========================================

        # 進場: Ratio > 80% Quantile AND Z-Score > 70% Quantile
        long_condition = (current_ratio > ratio_quantile_val) and (curr_z_score > curr_z_th)
        
        # 出場: Ratio < 80% Quantile AND Z-Score < 70% Quantile
        # 依照你的邏輯: 兩者都轉弱才出場
        exit_condition = (current_ratio < ratio_quantile_val) and (curr_z_score < curr_z_th)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'High_Trend_Ratio & High_Z_Score'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'Trend_Ratio_Drop & Z_Score_Drop'
            }
            
        return None