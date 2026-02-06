from .base_strategy import BaseStrategy
import indicators as ind
import numpy as np

class PriceVolume7(BaseStrategy):
    def __init__(self):
        super().__init__(name="Strategy7_Mom_LowVolFilter")
        
        # --- 策略參數 ---
        self.window = 25       # 滾動視窗
        self.th1 = 0.7         # Momentum 閾值 (強勢動能)
        self.th2 = 0.1         # MAD 閾值 (排除極致死魚盤即可)
        
        # 基礎指標參數
        self.mom_period = 10   # Momentum 週期
        self.mom_smooth = 5    # Momentum 平滑週期
        self.mad_period = 10   # MAD 計算週期

    def generate_signal(self):
        # 1. 數據長度檢查
        # Momentum(15) + Rolling(25) = 40
        if len(self.kline_data) < 60:
            return None

        # 2. 準備數據
        close = self.kline_data['close'].values
        
        # ==========================================
        #  因子計算
        # ==========================================

        # A. 計算 Momentum (平滑版)
        momentum = ind.AlphaLibrary.calc_smooth_momentum(
            close, mom_period=self.mom_period, smooth_period=self.mom_smooth
        )

        # B. 計算 MAD (價格偏離度)
        mad = ind.AlphaLibrary.calc_mad(close, window=self.mad_period)

        # C. 計算滾動分位數閾值
        # Momentum.rolling(25).quantile(0.7)
        mom_th = ind.AlphaLibrary.calc_rolling_quantile(momentum, self.window, self.th1)
        
        # MAD.rolling(25).quantile(0.1)
        mad_low_th = ind.AlphaLibrary.calc_rolling_quantile(mad, self.window, self.th2)

        # ==========================================
        #  獲取當前數值
        # ==========================================
        
        curr_mom = momentum[-1]
        curr_mad = mad[-1]
        
        curr_mom_th = mom_th[-1]
        curr_mad_th = mad_low_th[-1]

        # Debug Log
        # print(f"[{self.name}] MOM:{curr_mom:.2f}(>{curr_mom_th:.2f}) | MAD:{curr_mad:.4f}(>{curr_mad_th:.4f})")

        # ==========================================
        #  進出場邏輯
        # ==========================================

        # 進場: Momentum > 70% AND MAD > 10%
        # 意義：動能強，且波動率只要不是在最低 10% 都可以進場
        long_condition = (curr_mom > curr_mom_th) and (curr_mad > curr_mad_th)
        
        # 出場: Momentum < 70% AND MAD < 10%
        # 意義：必須等到動能轉弱，且市場進入死魚盤狀態 (MAD < 10%) 才平倉
        # 這是一個非常寬鬆的出場條件，可能會抱過很多回調
        exit_condition = (curr_mom < curr_mom_th) and (curr_mad < curr_mad_th)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'Mom_Strong & Not_Dead_Fish'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'Mom_Weak & Vol_Dead'
            }
            
        return None