requirements = [
    "mad_close_10_v1", 
    "bs_ratio_v1", 
    "is_us_trade_time_v1",
    "mad_quantile_10_25_0.7_v1",
    "bs_quantile_25_0.6_v1",

]

def run(row, account):
    curr_mad = row.get("mad_close_10_v1",0)
    curr_bs= row.get('bs_ratio_v1', 0)
    curr_mad_th=row.get("mad_quantile_10_25_0.6_v1", 0)
    curr_bs_th=row.get("bs_quantile_25_0.7_v1",0)
    is_trade =row.get("is_us_trade_time_v1",1)

    # === 訊號定義 ===
    # 1. 做多訊號
    long_condition = (curr_mad > curr_mad_th) and (curr_bs > curr_bs_th)
    long_signal = long_condition and is_trade
    
    # Pandas: ((mad < th) | (bs < th)) & (is_trade)
    # [修正重點] 必須加括號！先判斷 (MAD低 或 BS低)，結果出來後再 AND 交易時間
    exit_condition = (curr_mad < curr_mad_th) or (curr_bs < curr_bs_th)
    exit_signal = exit_condition and is_trade
    
    # ==========================================
    # 3. 執行邏輯 (對齊 Pandas shift(1) 的行為)
    # ==========================================
    # Pandas 邏輯回顧:
    # if long_signal[i-1] is True and pos == 0: pos = 1
    # if exit_signal[i-1] is True and pos == 1: pos = 0
    
    # 在這裡我們只要回傳訊號，Engine 設定為 next_open 就會自動模擬 shift(1)
    
    if account.position == 0:
        if long_signal:
            return 'LONG', 1.0
            
    # 情境 2: 目前持倉 (Position > 0) -> 只檢查出場
    # 這樣寫才能確保 long_signal 不會「遮蔽」exit_signal
    elif account.position > 0:
        if exit_signal:
            return 'LONG_EXIT', 1.0

    return 'HOLD', 0
'''
    if long_signal and pos <= 0:
        if pos < 0:
            return 'BUY_TO_COVER', 1.0   # 先平空
        else:
            return 'BUY', 1.0           # 開多


    # ===== 開空 =====
    elif short_signal and pos >= 0:
        if pos > 0:
            return 'SELL', 1.0           # 先平多
        else:
            return 'SHORT', 1.0        # 開空


    # ===== 平多 =====
    elif exit_long_signal and pos > 0:
        return 'SELL', 1.0


    # ===== 平空 =====
    elif exit_short_signal and pos < 0:
        return 'BUY_TO_COVER', 1.0


    return 'HOLD', 0
'''