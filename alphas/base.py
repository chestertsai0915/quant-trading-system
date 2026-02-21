
import numpy as np

class BaseAlpha:
    """
    量化策略的基底類別 (Base Class)。
    所有新策略都繼承此類別，可以省去大量重複代碼。
    """
    # 1.
    requirements = [ "is_us_trade_time_v1"]
    
    # 2. 預設參數 (由子類別覆寫)
    default_params = {}

    def __init__(self, params=None):
        # 自動處理參數
        self.params = params if params is not None else self.default_params

    def prepare_features(self, df):
        """
        [子類覆寫] 在這裡加入你要算的均線等。
        """
        return df

    def generate_target_position(self, row, account):
        """
        [子類覆寫] 交易邏輯：根據 row 判斷，回傳目標持倉比例 (-1.0 ~ 1.0)
        """
        raise NotImplementedError("請實作 generate_target_position 方法")

    def run(self, row, account, params=None):
        """
        回測引擎會呼叫的函數。
        """
        # 動態更新參數 (相容舊寫法)
        if params is not None:
            self.params = params

        
       
        # 執行你寫的交易邏輯
        try:
            target_pos = self.generate_target_position(row, account)
            return float(target_pos)
        except Exception:
            return 0.0