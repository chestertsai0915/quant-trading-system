from .base_strategy import BaseStrategy
import numpy as np
import pandas as pd

class SentimentStrategyV2(BaseStrategy):
    def __init__(self):
        super().__init__(name="Strategy12_GnF_Yield_Ratio")
        
        # --- 策略參數 ---
        self.gnf_window = 100       # GnF Ratio 滾動視窗
        self.yield_window = 168     # 殖利率滾動視窗 (168小時 = 1週)
        
        # 閾值
        self.gnf_entry_q = 0.7      # 進場分位數
        self.yield_entry_q = 0.7    # 進場分位數
        
        self.gnf_exit_q = 0.5       # 出場分位數
        self.yield_exit_q = 0.3     # 出場分位數
        
    def generate_signal(self):
        # 1. 確保數據長度足夠 (至少要比最長的視窗大)
        if len(self.kline_data) < max(self.gnf_window, self.yield_window):
            return None

        # 2. 複製數據 (避免汙染原始資料)
        df = self.kline_data.copy()

        # 3. 確保外部數據欄位存在 (防呆)
        # 檢查您 DataManager 存的名稱，假設是 'fear_greed' 和 'funding_rate' (或是 'GS10' 若有爬蟲)
        # 根據您的舊代碼，您用的是 'fng_value' 和 'GS10'
        required_cols = ['fear_greed', 'volume'] 
        # 注意: 如果 GS10 (美債) 還沒實作爬蟲，這裡會報錯，建議先確認欄位名稱
        # 假設您的 DataManager 已經把 fear_greed 合併進來了
        
        for col in required_cols:
            if col not in df.columns:
                return None

        # ==========================================
        #  向量化計算 (Vectorization)
        # ==========================================

        # A. 計算 GnF Ratio 序列 (整欄計算)
        # GnF = FearGreed / Volume
        # 使用 replace 避免除以 0
        gnf_ratio_series = df['fear_greed'] / np.log(df['volume'].replace(0, 1))
        
        # B. 計算 GnF 的動態閾值 (Rolling Quantile)
        gnf_entry_th_series = gnf_ratio_series.rolling(window=self.gnf_window).quantile(self.gnf_entry_q)
        gnf_exit_th_series = gnf_ratio_series.rolling(window=self.gnf_window).quantile(self.gnf_exit_q)

        # C. 處理 Yield (假設 'GS10' 或 'funding_rate' 在 df 裡)
        # 如果您還沒實作美債爬蟲，這裡暫時用 funding_rate 代替演示，或者您確認有 'GS10'
        target_yield_col = 'yield_10y' if 'yield_10y' in df.columns else 'funding_rate' # 自動切換
        
        if target_yield_col not in df.columns:
            return None
            
        yield_series = df[target_yield_col]
        
        # D. 計算 Yield 的動態閾值
        yield_entry_th_series = yield_series.rolling(window=self.yield_window).quantile(self.yield_entry_q)
        yield_exit_th_series = yield_series.rolling(window=self.yield_window).quantile(self.yield_exit_q)

        # ==========================================
        #  取出「當下」數值 (最後一筆)
        # ==========================================
        
        # 當前值
        curr_gnf = gnf_ratio_series.iloc[-1]
        curr_yield = yield_series.iloc[-1]
        
        # 當前閾值
        curr_gnf_entry_th = gnf_entry_th_series.iloc[-1]
        curr_gnf_exit_th = gnf_exit_th_series.iloc[-1]
        
        curr_yield_entry_th = yield_entry_th_series.iloc[-1]
        curr_yield_exit_th = yield_exit_th_series.iloc[-1]

        # 檢查是否為 NaN (剛啟動資料不足時)
        if np.isnan(curr_gnf_entry_th) or np.isnan(curr_yield_entry_th):
            return None

        # ==========================================
        #  進出場判斷
        # ==========================================
       
        # 進場: GnF > Entry_TH (0.7) AND Yield > Entry_TH (0.7)
        long_condition = (curr_gnf > curr_gnf_entry_th) and (curr_yield > curr_yield_entry_th)
        
        # 出場: GnF < Exit_TH (0.5) OR Yield < Exit_TH (0.3)
        exit_condition = (curr_gnf < curr_gnf_exit_th) or (curr_yield < curr_yield_exit_th)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'High_GnF({curr_gnf:.2e}) & High_Yield({curr_yield:.2f})'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'GnF_Drop or Yield_Drop'
            }
            
        return None