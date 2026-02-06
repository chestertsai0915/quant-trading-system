from .base_strategy import BaseStrategy
import indicators as ind
import numpy as np

class PriceVolume4(BaseStrategy):
    def __init__(self):
        super().__init__(name="Strategy4_High_Momentum")
        
        # --- 策略參數 (依照你的設定) ---
        self.window = 250      # 滾動視窗 (長期統計)
        self.th1 = 0.8         # OBV 分位數閾值
        self.th2 = 0.8         # VROC 分位數閾值
        
        # 基礎指標參數
        self.obv_smooth = 20   # OBV 平滑週期
        self.vroc_period = 10  # VROC 計算週期 (Volume Rate of Change)

    def generate_signal(self):
        # 1. 數據長度檢查
        # 因為 window=250，加上 VROC(10)，至少需要 260 根
        # 我們設定安全邊際為 300
        if len(self.kline_data) < 300:
            return None

        # 2. 準備數據
        close = self.kline_data['close'].values
        volume = self.kline_data['vol'].values
        
        # ==========================================
        #  因子計算
        # ==========================================

        # A. 計算 OBV (使用平滑版)
        obv = ind.AlphaLibrary.calc_smooth_obv(close, volume, window=self.obv_smooth)

        # B. 計算 VROC (成交量變化率)
        vroc = ind.AlphaLibrary.calc_vroc(volume, window=self.vroc_period)

        # C. 計算滾動分位數閾值 (Rolling Quantile)
        # data['OBV'].rolling(250).quantile(0.8)
        obv_th = ind.AlphaLibrary.calc_rolling_quantile(obv, self.window, self.th1)
        
        # data['vroc'].rolling(250).quantile(0.8)
        vroc_th = ind.AlphaLibrary.calc_rolling_quantile(vroc, self.window, self.th2)

        # ==========================================
        #  獲取當前數值
        # ==========================================
        
        curr_obv = obv[-1]
        curr_vroc = vroc[-1]
        
        curr_obv_th = obv_th[-1]
        curr_vroc_th = vroc_th[-1]

        # Debug Log (你可以打開來看數值)
        # print(f"[{self.name}] OBV:{curr_obv:.0f}(>{curr_obv_th:.0f}) | VROC:{curr_vroc:.2f}(>{curr_vroc_th:.2f})")

        # ==========================================
        #  進出場邏輯 (Logic)
        # ==========================================

        # 進場: (OBV > 80% Quantile) & (VROC > 80% Quantile)
        # 意義：長期量能趨勢強，且短期成交量爆發
        long_condition = (curr_obv > curr_obv_th) and (curr_vroc > curr_vroc_th)
        
        # 出場: (OBV < 80% Quantile) & (VROC < 80% Quantile)
        # 注意：你的代碼是用 & (AND)，這比 | (OR) 更難觸發。
        # 意義：必須等到「量能趨勢轉弱」且「爆發力也消失」才平倉，容忍度較高。
        exit_condition = (curr_obv < curr_obv_th) and (curr_vroc < curr_vroc_th)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'High_OBV & High_VROC'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'Momentum_Collapsed'
            }
            
        return None