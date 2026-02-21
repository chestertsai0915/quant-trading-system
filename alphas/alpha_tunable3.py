import numpy as np
from alphas.base import BaseAlpha
from alphas.alpha_tools import add_sma, add_zscore, get_tiered_position

# 只要定義一個 Strategy 類別並繼承 BaseAlpha 即可！
class Strategy(BaseAlpha):
    
    # 1. 只需要定義這個策略專屬的參數
    default_params = {
        "ma_window": 20,
        "z_window": 100,
        "z_entry_th": -1.5,
    }

    # 2. 呼叫廚具算指標
    def prepare_features(self, df):
        df = add_sma(df, window=self.params['ma_window'], out_name='dyn_ma')
        df = add_zscore(df, window=self.params['z_window'], out_name='dyn_zscore')
        return df

    # 3. 專注寫交易邏輯就好
    def generate_target_position(self, row, account):
        ma_val = row.get('dyn_ma', 0)
        z_val = row.get('dyn_zscore', 0)
        close = row['close']

        # 防呆
        if np.isnan(ma_val): return 0.0

        raw_signal = 0.0
        # 你的核心邏輯
        if close > ma_val:
            raw_signal = np.tanh(self.params['z_entry_th'] - z_val)

        # 轉成階梯倉位 (直接 return，也不用管 is_trade，因為 base 處理掉了)
        return get_tiered_position(raw_signal)