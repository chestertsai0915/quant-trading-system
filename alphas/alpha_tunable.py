# alphas/alpha_tunable.py


# 1. 固定特徵清單 (寫死你需要用到的指標)

requirements = [
    "sma_10_close_v1",      # 趨勢判斷
    "mad_close_20_v1",      # 震盪指標
    "zscore_close_100_v1",  # 乖離率
    "is_us_trade_time_v1"   # 交易時間濾網
]


# 2. 預設參數 (當不跑優化時用的值)

default_params = {
    "rsi_buy_th": 30,      # RSI 買入閾值
    "z_buy_th": -1.5,      # Z-Score 買入閾值
    "z_sell_th": 0.0,      # 出場閾值
}


# 3. 策略邏輯

def run(row, account, params=None):
    # 如果沒傳參數，使用預設值
    if params is None: 
        params = default_params

    # 1. 讀取數據 (ID 都是固定的) 
    sma_val = row.get("sma_10_close_v1", 0)
    rsi_val = row.get("mad_close_20_v1", 50)
    z_val   = row.get("zscore_close_100_v1", 0)
    close   = row['close']
    is_trade = row.get("is_us_trade_time_v1", 1)

    #  2. 讀取優化參數 
    # 這裡就是優化器會一直改變的地方
    p_rsi_buy = params.get("rsi_buy_th", 30)
    p_z_buy   = params.get("z_buy_th", -1.5)
    p_z_sell  = params.get("z_sell_th", 0.0)

    # 3. 交易邏輯 
    
    long_condition = (rsi_val < p_rsi_buy) and (z_val < p_z_buy)
    long_signal = long_condition 
    
    # 出場：回歸中軸
    exit_condition = (z_val > p_z_sell)
    exit_signal = exit_condition 

    # 4. 執行動作
    if account.position == 0:
        if long_signal:
            return 'LONG', 1.0
            
    elif account.position > 0:
        if exit_signal:
            return 'LONG_EXIT', 1.0

    return 'HOLD', 0