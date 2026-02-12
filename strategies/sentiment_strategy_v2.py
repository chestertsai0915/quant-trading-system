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
        # 1. 確保 DataBoard 存在
        if self.data_board is None:
            return None

        # 2. 準備基礎 K 線 (High Freq)
        # BaseStrategy 已經把 main_kline 放在 self.kline_data
        df = self.kline_data.copy()

        # ==========================================
        # 3. 【特徵工程】混合外部數據
        # ==========================================

        # A. 混合 Fear & Greed (單一指標，直接用 Helper)
        df = self.enrich_data_with_external(
            source_name='fear_greed',
            feature_cols=['value'],
            rename_map={'value': 'fear_greed'}
        )

        # B. 混合 US Yield 10Y (多指標數據，需手動處理)
        # 從 DataBoard 取得 FRED 原始數據
        fred_df = self.data_board.external_data.get('fred_macro')
        
        if fred_df is not None and not fred_df.empty:
            print('----------------------------------------------------------------',fred_df['metric'].unique())  # 印出有哪些指標，幫助調試
            # [關鍵步驟] 先篩選出我們要的 'yield_10y'
            # 因為 fred_macro 裡面混雜了 yield_2y, fed_assets 等
            yield_source = fred_df[fred_df['metric'] == 'yield_10y']
            
            # 手動呼叫 FeatureEngineer 進行縫合
            df = self.feature_engineer.attach_low_freq_feature(
                high_freq_df=df,
                low_freq_df=yield_source,
                feature_cols=['value'],
                rename_map={'value': 'yield_10y'}
            )

        print(df)
        # ==========================================
        # 4. 數據檢查與計算 (邏輯保留)
        # ==========================================
        
        # 檢查 Fear Greed 是否存在
        if 'fear_greed' not in df.columns:
            return None
            
        # 檢查數據長度
        if len(df) < max(self.gnf_window, self.yield_window):
            return None

        # A. 計算 GnF Ratio 序列
        # GnF = FearGreed / Volume
        # 使用 replace 避免除以 0
        gnf_ratio_series = df['fear_greed'] / np.log(df['volume'].replace(0, 1))
        
        # B. 計算 GnF 的動態閾值
        gnf_entry_th_series = gnf_ratio_series.rolling(window=self.gnf_window).quantile(self.gnf_entry_q)
        gnf_exit_th_series = gnf_ratio_series.rolling(window=self.gnf_window).quantile(self.gnf_exit_q)

        # C. 處理 Yield (Fallback 機制)
        # 如果 yield_10y 成功抓到且有值，就用它；否則退而求其次用 funding_rate
        target_yield_col = 'yield_10y' if 'yield_10y' in df.columns else 'funding_rate'
        
        # 如果連 funding_rate 都沒有，那就真的沒戲唱了
        if target_yield_col not in df.columns:
            return None
            
        yield_series = df[target_yield_col]
        
        # D. 計算 Yield 的動態閾值
        yield_entry_th_series = yield_series.rolling(window=self.yield_window).quantile(self.yield_entry_q)
        yield_exit_th_series = yield_series.rolling(window=self.yield_window).quantile(self.yield_exit_q)

        # ==========================================
        # 5. 取出「當下」數值 & 產生訊號
        # ==========================================
        
        # 當前值
        curr_gnf = gnf_ratio_series.iloc[-1]
        curr_yield = yield_series.iloc[-1]
        
        # 當前閾值
        curr_gnf_entry_th = gnf_entry_th_series.iloc[-1]
        curr_gnf_exit_th = gnf_exit_th_series.iloc[-1]
        
        curr_yield_entry_th = yield_entry_th_series.iloc[-1]
        curr_yield_exit_th = yield_exit_th_series.iloc[-1]

        # 檢查是否為 NaN
        if np.isnan(curr_gnf_entry_th) or np.isnan(curr_yield_entry_th):
            return None

        # 進出場判斷
        long_condition = (curr_gnf > curr_gnf_entry_th) and (curr_yield > curr_yield_entry_th)
        exit_condition = (curr_gnf < curr_gnf_exit_th) or (curr_yield < curr_yield_exit_th)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'High_GnF({curr_gnf:.2e}) & High_Yield({curr_yield:.2f}) [{target_yield_col}]'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'GnF_Drop or Yield_Drop'
            }
            
        return None