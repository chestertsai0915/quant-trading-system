
import pandas as pd
import numpy as np
import talib

# 1. 倉位與訊號轉換工具

def get_tiered_position(raw_signal, th_weak=0.5, pos_weak=0.5, th_strong=0.8, pos_strong=1.0):
    """將連續訊號轉換為階梯式的目標倉位"""
    if raw_signal >= th_strong: return pos_strong
    elif raw_signal >= th_weak: return pos_weak
    elif raw_signal <= -th_strong: return -pos_strong
    elif raw_signal <= -th_weak: return -pos_weak
    else: return 0.0

def get_tiered_position_long_only(raw_signal, th_weak=0.5, pos_weak=0.5, th_strong=0.8, pos_strong=1.0):
    """將連續訊號轉換為階梯式的目標倉位"""
    if raw_signal >= th_strong: return pos_strong
    elif raw_signal >= th_weak: return pos_weak
    elif raw_signal <= -th_strong: return 0
    elif raw_signal <= -th_weak: return 0
    else: return 0.0

def get_tiered_position_2(raw_signal, th_weak=0.5, pos_weak=0.5, th_strong=0.55, pos_strong=1.0):
    """將連續訊號轉換為階梯式的目標倉位"""
    if raw_signal >= th_strong: return 0.99
    elif raw_signal >= th_weak: return 0
    elif raw_signal <= -th_strong: return -0.99
    elif raw_signal <= -th_weak: return 0
    else: return 0.0
# 2. 時間序列指標加工 (Vectorized)

def add_sma(df, column='close', window=20, out_name='dyn_sma'):
    """計算簡單移動平均線"""
    df[out_name] = df[column].rolling(window=window).mean()
    return df

def add_zscore(df, column='close', window=100, out_name='dyn_zscore'):
    """計算 Z-Score (乖離率)"""
    roll_mean = df[column].rolling(window=window).mean()
    roll_std = df[column].rolling(window=window).std()+0.000001
    # 避免除以 0
    df[out_name] = (df[column] - roll_mean) / roll_std
    return df

def add_atr_like(df, column='close', window=14, out_name='dyn_atr'):
    """簡單版 ATR 替代 (真實波幅的移動平均)，若需要正規 ATR 可改用 ta-lib"""
    if 'high' in df.columns and 'low' in df.columns:
        tr = df['high'] - df['low'] # 簡化版真實波幅
        df[out_name] = tr.rolling(window=window).mean()
    else:
        # 如果只有收盤價，就用收盤價的絕對變化量代替
        df[out_name] = df[column].diff().abs().rolling(window=window).mean()
    return df

def add_mad(df, column='close', window=10, out_name='dyn_mad'):
    """
    計算均線乖離率 (MAD - Moving Average Deviation)
    公式: (價格 - 移動平均) / 移動平均
    
    :param df: 傳入的歷史數據 DataFrame
    :param column: 要計算的欄位 (預設為 'close')
    :param window: 均線週期 (預設為 10)
    :param out_name: 算出來的新欄位名稱
    """
    # 確保資料格式為 float
    data = df[column].values.astype(float)
    
    # 計算移動平均線
    ma = talib.SMA(data, timeperiod=window)
    
    # 計算乖離率並忽略除以 0 的警告
    with np.errstate(divide='ignore', invalid='ignore'):
        mad = (data - ma) / ma
        
    # 將 inf 或 nan 替換為 0，並存入 DataFrame
    df[out_name] = np.nan_to_num(mad, nan=0.0)
    
    return df
def add_quantile(df, column='close', window=25, quantile=0.8, out_name='dyn_quantile'):
    """
    計算滾動分位數 (Rolling Quantile)
    """
    # 確保傳進來的欄位存在 (防呆)
    if column not in df.columns:
        raise ValueError(f"找不到欄位 '{column}'，請確認是否有先執行前置特徵計算！")

    # 計算滾動分位數
    df[out_name] = df[column].rolling(window=window, min_periods=window).quantile(quantile).fillna(0)
    
    return df