import numpy as np
from alphas.base import BaseAlpha
import alphas.alpha_tools as tls

# 只要定義一個 Strategy 類別並繼承 BaseAlpha 即可！
class Strategy(BaseAlpha):
    # 1. 把所有「可能被選到」的特徵都寫進來！
    # 這樣 DataFactory 才會在回測前把資料都準備好
    requirements = BaseAlpha.requirements + [
        "close",
        "bs_ratio_v1", 
        "custom_atr_7_v1",
        "custom_atr_10_v1",
        "custom_atr_14_v1",
        "custom_atr_20_v1",
        "custom_atr_30_v1",
        "custom_atr_50_v1",
        "smooth_obv_10_v1",
        "vroc_20_v1",
    ]
    
    default_params = {
        "mad_ma_window": 25,
        "quanti_window": 150,
        "weiht1": 0.2,
        
        # 2. 把特徵變成參數！(這裡寫預設值)
        "factor_x": "bs_ratio_v1"  
    }

    def prepare_features(self, df):
        # 算 MAD 的 Z-score
        df = tls.add_mad(df, window=self.params["mad_ma_window"], out_name='dyn_mad')
        df = tls.add_zscore(df, column='dyn_mad', window=self.params["quanti_window"], out_name='mad_z')
        
        # 3. 動態讀取選中的特徵來算 Z-score
        selected_factor = self.params["factor_x"]
        
        # 不管優化器選了 bs_ratio 還是 funding_rate，我們都對它做 Z-score 標準化！
        df = tls.add_zscore(df, column=selected_factor, window=self.params["quanti_window"], out_name='factor_x_z')
        return df

    def generate_target_position(self, row, account):
        fid_mad_z = row.get('mad_z', 0)
        
        # 4. 讀取動態算出來的 Z-score
        fid_x_z = row.get('factor_x_z', 0) 
        trade_time = row['is_us_trade_time_v1']

        if np.isnan(fid_x_z) or np.isnan(fid_mad_z): 
            return 0.0

        w1 = self.params["weiht1"]
        
        # 核心邏輯 (稍微幫你整理了一下數學式，讓權重更對稱乾淨)
        signal_mad = np.clip(fid_mad_z, -1, 1) * 0.9
        signal_x = np.tanh(fid_x_z) * 0.9
        
        raw_signal = (w1 * signal_mad) + ((1 - w1) * signal_x)
        
        # 加上交易時間濾網
        if trade_time:
            raw_signal += 0.1 
            
        return tls.get_tiered_position_2(raw_signal)