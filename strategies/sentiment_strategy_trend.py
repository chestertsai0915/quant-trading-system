from .base_strategy import BaseStrategy
import indicators as ind
import numpy as np
import pandas as pd

class SentimentStrategyV3(BaseStrategy):
    def __init__(self):
        super().__init__(name="Strategy11_Trend_ZScore")
        
        # --- 策略參數 ---
        self.rolling_window = 1000  # 滾動視窗 (1000小時)
        self.z_window = 100         # Z-Score 的均線週期
        
        self.ratio_th = 0.8         # BTC Ratio 分位數閾值
        self.z_score_th = 0.7       # Z-Score 分位數閾值

    def generate_signal(self):
        # 1. 安全檢查：確保 DataBoard 存在
        if self.data_board is None:
            return None

        # ==========================================
        # 2. 【關鍵修改】手動串接多個外部數據
        # ==========================================
        
        # A. 取得初始的 K 線數據 (High Freq)
        # 注意：BaseStrategy 已經幫你把 main_kline 放在 self.kline_data 了
        df = self.kline_data.copy()

        # B. 混合第一份數據: Google Trends BTC
        # 外部數據源 registry key 為 'google_trends_BTC'
        # 1. 從 DataBoard 取得 "Google Trends" 總表
        # 注意：這裡用的 Key 必須跟 registry.py 裡的一樣 (即 Fetcher.name)
        gt_all_df = self.data_board.external_data.get('google_trends')

        if gt_all_df is None or gt_all_df.empty:
            print("[WARNING] Google Trends 數據缺失，無法生成訊號")
            return None

        # 2. 從總表中篩選出 "google_trends_BTC"
        # 根據 metric 欄位進行過濾
        btc_source = gt_all_df[gt_all_df['metric'] == 'google_trends_BTC']

        # 3. 從總表中篩選出 "google_trends_crypto"
        crypto_source = gt_all_df[gt_all_df['metric'] == 'google_trends_crypto']

        # 4. 進行特徵混合 (Feature Engineering)
        
        # A. 混合 BTC Trends
        df = self.feature_engineer.attach_low_freq_feature(
            high_freq_df=df, 
            low_freq_df=btc_source, # 傳入篩選後的 DataFrame
            feature_cols=['value'], 
            rename_map={'value': 'google_trends_BTC'}
        )

        # B. 混合 Crypto Trends
        df = self.feature_engineer.attach_low_freq_feature(
            high_freq_df=df, 
            low_freq_df=crypto_source, # 傳入篩選後的 DataFrame
            feature_cols=['value'],
            rename_map={'value': 'google_trends_crypto'}
        )
        
        
        # 3. 欄位檢查 (防呆)
        # 確認兩個外部欄位都成功合併進來了
        if 'google_trends_BTC' not in df.columns or 'google_trends_crypto' not in df.columns:
            return None

        # 4. 資料長度檢查
        # 如果資料少於 1000 筆，rolling(1000) 會算出 NaN
        if len(df) < self.rolling_window:
            return None
        
        # ==========================================
        # 5. 以下邏輯與原本完全相同 (只改變數來源為 df)
        # ==========================================

        # A. 計算 Sentiment Ratio 序列
        # 用 replace(0, 1) 防止分母為 0
        ratio_series = df['google_trends_BTC'] / df['google_trends_crypto'].replace(0, 1)
        
        # B. 計算 Ratio 的動態閾值
        ratio_quantile = ratio_series.rolling(window=self.rolling_window).quantile(self.ratio_th)
        
        # C. 計算價格 Z-Score 序列
        close = df['close']
        z_score_series = (close - close.rolling(self.z_window).mean()) / close.rolling(self.z_window).std()
        
        # D. 計算 Z-Score 的動態閾值
        z_score_quantile = z_score_series.rolling(window=self.rolling_window).quantile(self.z_score_th)

        # ==========================================
        #  取出「當下」數值
        # ==========================================
        
        current_ratio = ratio_series.iloc[-1]
        current_ratio_th = ratio_quantile.iloc[-1]
        
        curr_z_score = z_score_series.iloc[-1]
        curr_z_th = z_score_quantile.iloc[-1]

        # 檢查是否為 NaN
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