import numpy as np
# 1. 定義所有可能用到的特徵
# (優化時通常會把所有可能用到的特徵都先載入)
def get_tiered_position(raw_signal, th_weak=0.5, pos_weak=0.5, th_strong=0.8, pos_strong=1.0):
    """
    將連續訊號 (通常介於 -1.0 到 1.0 之間) 轉換為階梯式的目標倉位。
    支援多空對稱邏輯。
    
    :param raw_signal: 原始連續訊號 (正為多，負為空)
    :param th_weak: 弱訊號的門檻值 (預設 0.5)
    :param pos_weak: 弱訊號的對應倉位 (預設 0.5 = 半倉)
    :param th_strong: 強訊號的門檻值 (預設 0.8)
    :param pos_strong: 強訊號的對應倉位 (預設 1.0 = 滿倉)
    :return: 目標持倉比例 (float)
    """
    # === 處理多單 (Long) ===
    if raw_signal >= th_strong:
        return pos_strong
    elif raw_signal >= th_weak:
        return pos_weak
        
    # === 處理空單 (Short) ===
    elif raw_signal <= -th_strong:
        return -pos_strong
    elif raw_signal <= -th_weak:
        return -pos_weak
        
    # === 訊號太弱：空手 (Neutral) ===
    else:
        return 0.0
    
requirements = [
    "sma_20_close_v1", 
    "sma_60_close_v1",
    "custom_atr_ma_16_30_v1 ",
    "zscore_close_100_v1",
    "is_us_trade_time"
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
    
   
    raw_signal =np.tanh(rsi_val - p_rsi_low) 
    print(rsi_val - p_rsi_low)
    

    # === 4. 執行 ===
    target_pos = get_tiered_position(
        raw_signal, 
        th_weak=0.5, pos_weak=0.5,   # 訊號達到 0.5 就開半倉 (多空皆適用)
        th_strong=0.8, pos_strong=1.0 # 訊號達到 0.8 就開滿倉 (多空皆適用)
    )

    # 5. 時間濾網
    

    return float(target_pos)