# alphas/detailed_strategy.py
from alphas.base import BaseAlpha

class Strategy(BaseAlpha):
    # 1. 這裡放你原本的 requirements (直接覆寫 BaseAlpha 的設定)
    requirements = [
        "mad_close_10_v1", 
        "bs_ratio_v1", 
        "is_us_trade_time_v1",
        "mad_quantile_10_25_0.7_v1",  
        "bs_quantile_25_0.6_v1"
    ]

    # 因為你沒有要跑動態參數優化，所以不需要寫 default_params
    # 也不需要寫 prepare_features，系統會自動跳過。

    # 2. 專注寫交易邏輯
    def generate_target_position(self, row, account):
        # 取值
        curr_mad = row.get("mad_close_10_v1", 0)
        curr_bs  = row.get("bs_ratio_v1", 0)
        
        # 這裡的 get 字串要跟你 requirements 裡的一致！
       
        curr_mad_th = row.get("mad_quantile_10_25_0.7_v1", 0)
        curr_bs_th  = row.get("bs_quantile_25_0.6_v1", 0)

        # 防呆：如果特徵還沒出來(例如前幾筆是0或NaN)，就先空手
        if curr_mad_th == 0 or curr_bs_th == 0:
            return 0.0

        # 訊號定義 
        long_condition = (curr_mad > curr_mad_th) and (curr_bs > curr_bs_th)
        exit_condition = (curr_mad < curr_mad_th) or (curr_bs < curr_bs_th)
        
      
        # 回傳「你要的目標倉位」
        
        if account.position == 0:
            if long_condition:
                return 1.0  
                
        elif account.position > 0:
            if exit_condition:
                return 0.0  

        # 如果都沒觸發，就維持目前的倉位
        return account.position