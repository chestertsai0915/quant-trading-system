import pandas as pd
import numpy as np
import indicators as ind  # 假設您的指標庫在這裡
import logging

class FeatureEngineer:
    def __init__(self):
        pass

    def add_qqq_wavelet_feature(self, qqq_df, window=120, level=3):
        """
        專門為 QQQ 日線數據計算小波特徵
        input: qqq_df (日線資料)
        output: qqq_df (新增了 'QQQ_Wavelet_A' 欄位)
        """
        if qqq_df.empty or len(qqq_df) < window:
            return qqq_df

        # 為了效能，我們不需要對整個歷史重算幾千次小波
        # 但為了 Stateless，我們每次進來還是得算一下最新的
        # 這裡有兩種做法：
        # 1. (簡單版) 用 rolling apply (慢，但程式碼乾淨)
        # 2. (優化版) 只算最後一筆 (快，適合實盤)
        
        # 這裡示範「全量計算」的寫法 (適合 Backtest & Live)，
        # 如果實盤覺得慢，可以改成只算 tail
        
        # 定義一個內部函數來處理單一視窗
        def calc_wavelet(series):
            try:
                # 呼叫您的 AlphaLibrary
                feats = ind.AlphaLibrary.calc_wavelet_features(
                    series, wavelet='db4', level=level
                )
                return feats.get('A_mean', 0)
            except Exception:
                return 0

        # 使用 Pandas Rolling Apply
        # 注意：這步運算量較大，如果 qqq_df 有幾千筆，建議只取最後 500 筆來算
        calc_df = qqq_df.copy()
        
        # 創造特徵欄位
        # raw=True 傳入 numpy array 加速
        calc_df['QQQ_Wavelet'] = calc_df['close'].rolling(window=window).apply(calc_wavelet, raw=True)
        
        return calc_df

    def merge_features(self, main_df, feature_df, feature_cols, on='open_time'):
        """
        將算好的特徵 (feature_df, 如 QQQ) 合併回主頻率數據 (main_df, 如 BTC)
        使用 merge_asof 解決頻率不一致問題
        """
        if feature_df.empty or main_df.empty:
            return main_df

        # 只取需要的欄位 (時間 + 特徵)
        cols_to_merge = [on] + feature_cols
        right_df = feature_df[cols_to_merge].dropna().sort_values(on)
        
        main_df = main_df.sort_values(on)

        # 核心：向後查找 (Backward)
        # 這會幫 BTC 找到「最近收盤」的那一根 QQQ 的特徵
        merged_df = pd.merge_asof(
            main_df,
            right_df,
            on=on,
            direction='backward'
        )
        
        # 填補空值 (如果是剛開盤還沒產生新指標，沿用舊的)
        merged_df[feature_cols] = merged_df[feature_cols].ffill().fillna(0)
        
        return merged_df