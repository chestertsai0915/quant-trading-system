requirements = [
    "sma_20_close_v1", 
    "zscore_close_101_v1", 
    "is_us_trade_time_v1"
]

def run(row, account):
    ma20 = row.get('sma_20_close_v1', 0)
    zscore = row.get('zscore_close_101_v1', 0)
    close = row['close']
    
    # === 訊號定義 ===
    # 1. 做多訊號
    long_signal = (close> ma20) and (zscore < -1.5)
    
    # 2. 做空訊號 (價格跌破均線 且 Z-Score 過高)
    short_signal = (close < ma20) and (zscore > 1.5)
    
    # 3. 平倉訊號 (回歸中值)
    exit_signal = 0

    # === 執行邏輯 (狀態機) ===
    
   # === 4. 執行 ===
    pos = account.position

    # ===== 開多 =====
    if long_signal and pos <= 0:
        if pos < 0:
            return 'BUY_TO_COVER', 1.0   # 先平空
        else:
            return 'BUY', 0.98           # 開多


    # ===== 開空 =====
    elif short_signal and pos >= 0:
        if pos > 0:
            return 'SELL', 1.0           # 先平多
        else:
            return 'SHORT', 0.98         # 開空


    # ===== 平多 =====
    elif exit_signal and pos > 0:
        return 'SELL', 1.0


    # ===== 平空 =====
    elif exit_signal and pos < 0:
        return 'BUY_TO_COVER', 1.0


    return 'HOLD', 0