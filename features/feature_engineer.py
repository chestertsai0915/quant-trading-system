import pandas as pd
import numpy as np
import logging

class FeatureEngineer:
    def __init__(self):
        pass

    def attach_low_freq_feature(self, high_freq_df, low_freq_df, feature_cols, rename_map=None, time_col='open_time'):
        """
        修正版：增加 None 檢查與欄位存在性檢查
        """
        # [Fix 1] 增加 is None 檢查，防止 'NoneType' object has no attribute 'empty'
        if high_freq_df is None or high_freq_df.empty:
            return high_freq_df
            
        if low_freq_df is None or low_freq_df.empty:
            return high_freq_df

        # 1. 準備數據
        left = high_freq_df.sort_values(time_col)
        
        cols_to_use = [time_col] + feature_cols
        # 篩選存在的欄位 (避免請求不存在的欄位)
        available_cols = [c for c in cols_to_use if c in low_freq_df.columns]
        
        # 如果連 time_col 都不在，或者沒有任何特徵欄位，直接返回
        if time_col not in available_cols or len(available_cols) <= 1:
            return high_freq_df

        right = low_freq_df[available_cols].dropna().sort_values(time_col)

        if right.empty:
            return high_freq_df

        # [Fix 2] 在 merge 前處理改名 (Pre-rename)
        # 這樣可以確保 available_cols 裡面的欄位都被正確改名，不會跟左邊衝突
        final_feature_cols = []
        if rename_map:
            right = right.rename(columns=rename_map)
            # 更新我們 "期望" 存在的特徵欄位名稱
            for col in feature_cols:
                if col in available_cols: # 只處理真正存在的
                    new_name = rename_map.get(col, col)
                    final_feature_cols.append(new_name)
        else:
            final_feature_cols = [c for c in feature_cols if c in available_cols]

        try:
            # 2. 核心：merge_asof
            merged_df = pd.merge_asof(
                left,
                right,
                on=time_col,
                direction='backward',
                suffixes=('', '_conflict') 
            )
            
            # 3. 處理空值 (ffill)
            # [Fix 3] 只對 "成功合併進來且存在於表內" 的欄位做 ffill
            # 這樣如果 QQQ_Wavelet 一開始就不在 available_cols，這裡就不會報錯
            valid_cols_to_fill = [c for c in final_feature_cols if c in merged_df.columns]
            
            if valid_cols_to_fill:
                merged_df[valid_cols_to_fill] = merged_df[valid_cols_to_fill].ffill().fillna(0)
            
            return merged_df
            
        except Exception as e:
            logging.error(f"跨尺度特徵合併失敗: {e}")
            return high_freq_df