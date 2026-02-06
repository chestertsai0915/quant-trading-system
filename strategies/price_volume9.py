from .base_strategy import BaseStrategy
import indicators as ind
import numpy as np

class PriceVolume9(BaseStrategy):
    def __init__(self):
        super().__init__(name="Strategy9_Mom_VROC_Shock")
        
        # --- 策略參數 ---
        self.window = 90       # 滾動視窗 (中長期統計)
        self.th1 = 0.8         # Momentum 閾值 (高動能)
        self.th2 = 0.9         # VROC 閾值 (極致量能爆發)
        
        # 基礎指標參數
        self.mom_period = 10   # Momentum 週期
        self.mom_smooth = 5    # Momentum 平滑週期
        self.vroc_period = 10  # VROC 計算週期

    def generate_signal(self):
        # 1. 數據長度檢查
        # Momentum(15) + Rolling(90) = 105
        # 安全邊際設 120
        if len(self.kline_data) < 120:
            return None

        # 2. 準備數據
        close = self.kline_data['close'].values
        volume = self.kline_data['vol'].values
        
        # ==========================================
        #  因子計算
        # ==========================================

        # A. 計算 Momentum (平滑版)
        momentum = ind.AlphaLibrary.calc_smooth_momentum(
            close, mom_period=self.mom_period, smooth_period=self.mom_smooth
        )

        # B. 計算 VROC (成交量變化率)
        vroc = ind.AlphaLibrary.calc_vroc(volume, window=self.vroc_period)

        # C. 計算滾動分位數閾值
        # Momentum.rolling(90).quantile(0.8)
        mom_th = ind.AlphaLibrary.calc_rolling_quantile(momentum, self.window, self.th1)
        
        # VROC.rolling(90).quantile(0.9)
        vroc_th = ind.AlphaLibrary.calc_rolling_quantile(vroc, self.window, self.th2)

        # ==========================================
        #  獲取當前數值
        # ==========================================
        
        curr_mom = momentum[-1]
        curr_vroc = vroc[-1]
        
        curr_mom_th = mom_th[-1]
        curr_vroc_th = vroc_th[-1]

        # Debug Log
        # print(f"[{self.name}] MOM:{curr_mom:.2f}(>{curr_mom_th:.2f}) | VROC:{curr_vroc:.2f}(>{curr_vroc_th:.2f})")

        # ==========================================
        #  進出場邏輯
        # ==========================================

        # 進場: Momentum > 80% AND VROC > 90%
        # 意義：價格強勢且成交量異常放大 (突破訊號)
        long_condition = (curr_mom > curr_mom_th) and (curr_vroc > curr_vroc_th)
        
        # 出場: Momentum < 80% AND VROC < 90%
        # 注意：使用 AND，必須等到動能與量能同時冷卻
        exit_condition = (curr_mom < curr_mom_th) and (curr_vroc < curr_vroc_th)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'Mom_Strong & Vol_Shock'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'Mom_Fade & Vol_Normal'
            }
            
        return None