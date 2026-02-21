
import pandas as pd
import numpy as np


# 1. 倉位與訊號轉換工具

def get_tiered_position(raw_signal, th_weak=0.5, pos_weak=0.5, th_strong=0.8, pos_strong=1.0):
    """將連續訊號轉換為階梯式的目標倉位"""
    if raw_signal >= th_strong: return pos_strong
    elif raw_signal >= th_weak: return pos_weak
    elif raw_signal <= -th_strong: return -pos_strong
    elif raw_signal <= -th_weak: return -pos_weak
    else: return 0.0

# 2. 時間序列指標加工 (Vectorized)

def add_sma(df, col='close', window=20, out_name='dyn_sma'):
    """計算簡單移動平均線"""
    df[out_name] = df[col].rolling(window=window).mean()
    return df

def add_zscore(df, col='close', window=100, out_name='dyn_zscore'):
    """計算 Z-Score (乖離率)"""
    roll_mean = df[col].rolling(window=window).mean()
    roll_std = df[col].rolling(window=window).std()
    # 避免除以 0
    df[out_name] = np.where(roll_std == 0, 0, (df[col] - roll_mean) / roll_std)
    return df

def add_atr_like(df, col='close', window=14, out_name='dyn_atr'):
    """簡單版 ATR 替代 (真實波幅的移動平均)，若需要正規 ATR 可改用 ta-lib"""
    if 'high' in df.columns and 'low' in df.columns:
        tr = df['high'] - df['low'] # 簡化版真實波幅
        df[out_name] = tr.rolling(window=window).mean()
    else:
        # 如果只有收盤價，就用收盤價的絕對變化量代替
        df[out_name] = df[col].diff().abs().rolling(window=window).mean()
    return df