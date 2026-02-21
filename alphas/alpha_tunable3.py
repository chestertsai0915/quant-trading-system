import numpy as np
from alphas.base import BaseAlpha
import alphas.alpha_tools as tls

# 只要定義一個 Strategy 類別並繼承 BaseAlpha 即可！
class Strategy(BaseAlpha):
    requirements = BaseAlpha.requirements + [
        "bs_ratio_v1","close"
    ]
    # 1. 只需要定義這個策略專屬的參數
    default_params = {
        "mad_ma_window": 25,
        "quanti_window":150,
        "weiht1":0.2,

    }

    # 2. 呼叫廚具算指標
    def prepare_features(self, df):
        df = tls.add_mad(df, window=self.params["mad_ma_window"], out_name='mad_close_10')
        df = tls.add_zscore(df, column='mad_close_10', window=self.params["quanti_window"],out_name='mad_z')
        df = tls.add_zscore(df, column='bs_ratio_v1', window=self.params["quanti_window"],out_name='bs_z')
        return df

    # 3. 專注寫交易邏輯就好
    def generate_target_position(self, row, account):
        #row['column']沒有這個欄位，程式直接崩潰報錯。row.get沒有這個欄位，程式不會報錯
        fid_mad_z = row.get('mad_z', 0)
        fid_bs_z = row.get('bs_z', 0)
        trade_time = row['is_us_trade_time_v1']

        # 防呆
        if np.isnan(fid_bs_z): 
            return 0.0

        raw_signal = 0.0
        # 你的核心邏輯
        
        raw_signal = self.params["weiht1"]*np.clip(fid_mad_z+0.05*trade_time, -1, 1)+(1-self.params["weiht1"])*np.clip(fid_bs_z+0.05*trade_time, -1, 1)
       

        # 轉成階梯倉位
        return tls.get_tiered_position(raw_signal)
