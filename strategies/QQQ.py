from .base_strategy import BaseStrategy
import indicators as ind
import numpy as np
import pandas as pd

class QQQ_price(BaseStrategy):
    def __init__(self):
        super().__init__(name="Strategy13_QQQ_Wavelet_Trend")
        
        # --- 策略參數 ---
        self.wavelet_window = 120   # 小波轉換的滑動視窗
        self.quantile_window = 400  # 歷史分位數視窗
        self.wavelet_level = 3      # 小波層數
        
        self.long_th = 0.7          # 進場分位數 (0.7)
        self.exit_th = 0.1          # 出場分位數 (0.1)
        
        # 快取 (避免每次 loop 都重複算幾千次小波)
        self.last_qqq_time = None
        self.cached_signal = None

    def generate_signal(self):
        # 1. 取得 QQQ 數據
        qqq_df = self.external_data.get('QQQ_Data')
        
        if qqq_df is None or qqq_df.empty:
            return None

        # 2. 檢查數據是否更新 (優化效能)
        # 如果 QQQ 的最新時間跟上次一樣，就直接回傳上次算的訊號
        latest_time = qqq_df.index[-1]
        if self.last_qqq_time == latest_time and self.cached_signal is not None:
            return self.cached_signal

        # 3. 數據長度檢查
        # 我們需要至少 quantile_window + wavelet_window 的數據
        min_len = self.quantile_window + self.wavelet_window
        close_prices = qqq_df['close'].values
        
        if len(close_prices) < min_len:
            # print(f"[{self.name}] QQQ 數據不足: {len(close_prices)} < {min_len}")
            return None

        # ==========================================
        # 👇 因子計算 (重建特徵歷史)
        # ==========================================
        
        # 我們需要算出過去 400 天，每天的 "Wavelet A_mean" 值
        # 這是一個比較重的運算，所以只取最近所需的這一段來算
        
        feature_history = []
        
        # 迴圈範圍：從 "倒數第400天" 到 "今天"
        # range 的終點是 len(close_prices)，起點是 len - 400
        start_idx = len(close_prices) - self.quantile_window
        
        # 注意：每次計算特徵需要往前取 wavelet_window (120)
        # 所以確保 start_idx - 120 >= 0
        if start_idx - self.wavelet_window < 0:
            return None

        for i in range(start_idx, len(close_prices) + 1):
            # 取出該時間點的一段視窗 [i-120 : i]
            # 注意: python slice 是前閉後開，所以要到 i
            window_data = close_prices[i - self.wavelet_window : i]
            
            # 計算小波特徵
            feats = ind.AlphaLibrary.calc_wavelet_features(
                window_data, wavelet='db4', level=self.wavelet_level
            )
            
            # 取出 A_mean (低頻趨勢) 作為 QQQ_feature
            # 如果你想改用 D1_energy (噪音)，改這裡即可
            if 'A_mean' in feats:
                feature_history.append(feats['A_mean'])
            else:
                feature_history.append(0)

        # 轉成 Series 以便計算 quantile
        feat_series = pd.Series(feature_history)
        
        # ==========================================
        # 👇 計算閾值與當前值
        # ==========================================
        
        # 當前最新的特徵值 (Series 的最後一個)
        curr_feature = feat_series.iloc[-1]
        
        # 歷史分位數 (不包含當前這一個，避免未來函數，雖然這裡是即時算沒差)
        # rolling(400) 的 quantile
        # 既然我們這個 feat_series 長度剛好就是 400 (或 401)，我們直接算整體的 quantile
        # 嚴謹一點：用過去 400 筆 (排除最新一筆) 來建立標準
        history_reference = feat_series.iloc[:-1] 
        
        if len(history_reference) < 100: 
            return None

        long_threshold = history_reference.quantile(self.long_th)
        exit_threshold = history_reference.quantile(self.exit_th)

        # Debug Log
        # print(f"[{self.name}] QQQ_Feat(A_mean): {curr_feature:.2f} | Long_Th: {long_threshold:.2f} | Exit_Th: {exit_threshold:.2f}")

        # ==========================================
        # 👇 進出場邏輯
        # ==========================================
        
        signal = None
        
        # 進場: Feature > 70% Quantile
        if curr_feature > long_threshold:
            signal = {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'QQQ_Trend_Strong ({curr_feature:.1f} > {long_threshold:.1f})'
            }
        
        # 出場: Feature < 10% Quantile
        elif curr_feature < exit_threshold:
            signal = {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'QQQ_Trend_Crash ({curr_feature:.1f} < {exit_threshold:.1f})'
            }
            
        # 更新快取
        self.last_qqq_time = latest_time
        self.cached_signal = signal
        
        return signal