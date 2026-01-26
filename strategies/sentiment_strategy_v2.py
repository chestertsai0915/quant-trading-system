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
        
        # --- 歷史數據緩衝區 ---
        # 因為這些數據來自 external_data (單點)，我們需要自己存成列表來算 quantile
        self.gnf_ratio_history = []
        self.yield_history = []

    def generate_signal(self):
        # 1. 確保有足夠的 K 線數據來獲取 Volume
        if len(self.kline_data) < 1:
            return None

        # 2. 從 external_data 獲取數據
        # F&G Index (0-100)
        fng_val = self.external_data.get('fng_value', 0)
        
        # 10Y Yield (例如 4.5) - 從 get_macro_data() 來的 Key 是 'GS10'
        yield_10y = self.external_data.get('GS10', 0)
        
        # 成交量 (取最新一根收盤的 Volume)
        current_volume = self.kline_data['vol'].iloc[-1]

        # 簡單的防呆 (避免數據還沒抓到)
        if current_volume == 0 or yield_10y == 0:
            return None

        # ==========================================
        # 👇 因子計算
        # ==========================================

        # A. 計算 GnF Ratio = Fear&Greed / Volume
        # 注意：Volume 通常很大，這個數值會極小，但不影響分位數計算
        current_gnf_ratio = fng_val / current_volume
        
        # 存入歷史
        self.gnf_ratio_history.append(current_gnf_ratio)
        if len(self.gnf_ratio_history) > self.gnf_window:
            self.gnf_ratio_history.pop(0)

        # B. 處理 Yield History
        self.yield_history.append(yield_10y)
        if len(self.yield_history) > self.yield_window:
            self.yield_history.pop(0)

        # ==========================================
        # 👇 計算滾動分位數 (Thresholds)
        # ==========================================
        
        # 暖機檢查：如果歷史數據太少，先不計算 (避免分位數失真)
        # 實盤建議至少累積 24 小時的數據再開始
        if len(self.yield_history) < 24:
            return None

        # 計算 GnF Ratio 的閾值
        gnf_series = pd.Series(self.gnf_ratio_history)
        gnf_entry_th = gnf_series.quantile(self.gnf_entry_q) # 0.7
        gnf_exit_th = gnf_series.quantile(self.gnf_exit_q)   # 0.5
        
        # 計算 Yield 的閾值
        yield_series = pd.Series(self.yield_history)
        yield_entry_th = yield_series.quantile(self.yield_entry_q) # 0.7
        yield_exit_th = yield_series.quantile(self.yield_exit_q)   # 0.3

        # ==========================================
        # 👇 獲取當前數值與邏輯
        # ==========================================

        # Debug Log
        # print(f"[{self.name}] GnF:{current_gnf_ratio:.2e}(>{gnf_entry_th:.2e}) | Yield:{yield_10y}(>{yield_entry_th})")

        # 進場: GnF_Ratio > 70% AND Yield > 70%
        long_condition = (current_gnf_ratio > gnf_entry_th) and (yield_10y > yield_entry_th)
        
        # 出場: GnF_Ratio < 50% OR Yield < 30%
        # 注意：這裡使用 OR (|)，代表任一條件轉弱就跑
        exit_condition = (current_gnf_ratio < gnf_exit_th) or (yield_10y < yield_exit_th)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'High_GnF_Ratio & High_Yield'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'GnF_Drop or Yield_Drop'
            }
            
        return None