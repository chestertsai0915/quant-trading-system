# alphas/alpha_tunable.py

# 1. 定義所有可能用到的特徵
# (優化時通常會把所有可能用到的特徵都先載入)
requirements = [
    "sma_20_close_v1", 
    "sma_60_close_v1",
    "custom_atr_ma_16_30_v1 ",
    "zscore_close_100_v1"
]

# 2. 定義預設參數 (Default Hyperparameters)
default_params = {
    "ma_period": 20,       # 雖然 ID 寫死 sma_20，但邏輯上我們可以選用哪個特徵
    "atr_lower": 30,       # 買入閾值
    "atr_upper": 70,       # 賣出閾值
    "zscore_entry": -1.5,  # 進場 Z 分數
    "stop_loss": 0.05      # 止損百分比
}

def run(row, account, params=None):
    """
    注意：這裡多了一個 params 參數
    """
    # 如果沒傳參數，就用預設的
    if params is None:
        params = default_params

    # === 1. 取出參數 ===
    p_rsi_low = params.get('atr_lower', 30)
    p_rsi_high = params.get('atr_upper', 70)
    p_z_entry = params.get('zscore_entry', -1.5)
    
    # === 2. 提取特徵 ===
    # 這裡演示如何根據參數選擇特徵 (簡單版)
    # 實務上 ID 通常是固定的，我們調的是閾值
    ma_val = row.get('sma_20_close_v1', 0) 
    rsi_val = row.get('custom_atr_ma_16_30_v1', 50)
    z_val = row.get('zscore_close_100_v1', 0)
    close = row['close']

    # === 3. 交易邏輯 ===
    
    # 進場條件：RSI 低於參數 AND Z-Score 低於參數
    long_condition = (rsi_val < p_rsi_low) and (z_val < p_z_entry)
    
    # 出場條件：RSI 高於參數
    exit_condition = (rsi_val > p_rsi_high)

    # === 4. 執行 ===
    if long_condition:
        if account.position == 0:
            return 'BUY', 0.98
            
    elif exit_condition:
        if account.position > 0:
            return 'SELL', 1.0

    return 'HOLD', 0