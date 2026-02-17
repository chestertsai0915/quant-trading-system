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
    
    # 如果目前持有 多單 (Position > 0)
    if account.position > 0:
        if exit_signal or short_signal:
            return 'SELL', 1.0  # 平多 (若 short_signal 觸發，這裡只會平倉，下一根 K 線才會開空，或者你可以寫複雜點直接反手)
            
    # 如果目前持有 空單 (Position < 0)
    elif account.position < 0:
        if exit_signal or long_signal:
            return 'BUY', 1.0   # 平空 (Cover)

    # 如果目前 空手 (Position == 0)
    else:
        if long_signal:
            return 'BUY', 0.98  # 開多
        elif short_signal:
            return 'SELL', 0.98 # 開空 (Short)

    return 'HOLD', 0