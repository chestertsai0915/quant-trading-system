from .base_strategy import BaseStrategy
import pandas as pd
import numpy as np

class SentimentStrategyV2(BaseStrategy):
    def __init__(self):
        super().__init__(name="Strategy12_GnF_Yield_Ratio")
        
        # --- 策略參數 ---
        self.gnf_window = 100       # GnF Ratio 滾動視窗 (小時)
        self.yield_window = 168     # 殖利率滾動視窗 (168小時 = 1週)
        
        # 閾值
        self.gnf_entry_q = 0.7      # 進場分位數
        self.yield_entry_q = 0.7    # 進場分位數
        
        self.gnf_exit_q = 0.5       # 出場分位數
        self.yield_exit_q = 0.3     # 出場分位數
        
    def generate_signal(self):
        # ==========================================
        # 1. 定義需要的特徵 ID
        # ==========================================
        
        # A. Fear & Greed Raw
        fid_fg = "fear_greed_raw_v1"
        
        # B. Macro Raw (Yield 10Y)
        fid_yield = "macro_raw_yield_10y_v1"
        
        # C. Funding Rate (作為 Fallback)
        # 假設我們也有一個 funding_rate_raw_{symbol}_v1
        # 但為了簡單，這裡假設如果 yield 沒抓到，策略直接返回 None，或你可以新增 FundingRateRaw
        # 這裡示範只用 Yield
        
        # ==========================================
        # 2. 向 Feature Store 請求數據
        # ==========================================
        # Feature Store 會自動將 F&G (日) 和 Yield (日) ffill 到小時線
        df = self.load_features([fid_fg, fid_yield])
        
        # 安全檢查
        if df.empty or len(df) < max(self.gnf_window, self.yield_window):
            return None

        # 如果關鍵特徵缺失，直接不交易
        if fid_fg not in df.columns or fid_yield not in df.columns:
            return None

        # ==========================================
        # 3. 策略層計算 (Strategy-Side Calculation)
        # ==========================================
        
        # A. 取得已經廣播好的序列 (Hourly Series)
        fg_series = df[fid_fg]
        yield_series = df[fid_yield]
        
        # B. 計算 GnF Ratio
        # 公式: FearGreed / log(Volume)
        # 這裡混合了日線特徵 (fg_series) 和小時線特徵 (df['volume'])
        # 這就是所謂的 "廣播後計算"
        # 注意：load_features 回傳的 df 包含了原始 K 線數據 (close, volume...)
        log_volume = np.log(self.kline_data['volume'].replace(0, 1))
        
        # 為了對齊長度，我們只取 load_features 回傳的部分
        # 因為 df 已經是與 kline 對齊的結果
        # 但保險起見，我們直接操作 df 裡的 volume (如果 feature store 有保留 raw kline columns)
        # 根據我們之前的實作，load_features 回傳的是 merge 後的 df，
        # 但它只保留了 open_time 和 features。
        # [修正]: 我們需要把 volume 併進來，或者直接用 kline_data 的 volume (需確保 index 對齊)
        
        # 最佳解：利用 merge_asof 對齊時間索引
        # 這裡簡單假設 df 的長度跟 self.kline_data 一樣且對齊
        # (通常是的，因為 FeatureStore 也是用 main_kline 作為骨架)
        
        # 為了安全，我們重新用時間對齊 volume
        vol_series = self.kline_data.set_index('open_time')['volume']
        # 確保 df 的 index 是 open_time (如果不是，請 set_index)
        if 'open_time' in df.columns:
             df = df.set_index('open_time')
        
        # 對齊 volume 到 df
        aligned_vol = vol_series.reindex(df.index).ffill()
        
        # 計算 GnF
        gnf_ratio_series = fg_series / np.log(aligned_vol.replace(0, 1))
        
        # C. 計算 GnF 的動態閾值 (Rolling on Hourly Data)
        gnf_entry_th = gnf_ratio_series.rolling(window=self.gnf_window).quantile(self.gnf_entry_q)
        gnf_exit_th = gnf_ratio_series.rolling(window=self.gnf_window).quantile(self.gnf_exit_q)
        
        # D. 計算 Yield 的動態閾值 (Rolling on Hourly Broadcasted Data)
        yield_entry_th = yield_series.rolling(window=self.yield_window).quantile(self.yield_entry_q)
        yield_exit_th = yield_series.rolling(window=self.yield_window).quantile(self.yield_exit_q)

        # ==========================================
        # 4. 交易邏輯
        # ==========================================
        
        curr_gnf = gnf_ratio_series.iloc[-1]
        curr_yield = yield_series.iloc[-1]
        
        curr_gnf_entry = gnf_entry_th.iloc[-1]
        curr_gnf_exit = gnf_exit_th.iloc[-1]
        
        curr_yield_entry = yield_entry_th.iloc[-1]
        curr_yield_exit = yield_exit_th.iloc[-1]

        # 檢查 NaN
        if np.isnan(curr_gnf_entry) or np.isnan(curr_yield_entry):
            return None

        # 進場
        long_condition = (curr_gnf > curr_gnf_entry) and (curr_yield > curr_yield_entry)
        
        # 出場
        exit_condition = (curr_gnf < curr_gnf_exit) or (curr_yield < curr_yield_exit)

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