from .base_strategy import BaseStrategy
import indicators as ind
import numpy as np

class PriceVolume3(BaseStrategy):
    def __init__(self):
        super().__init__(name="Strategy3_MAD_OBV_Quantile")
        
        # --- 策略參數 (依照你的設定) ---
        self.window = 90       # 滾動視窗
        self.th1 = 0.9         # MAD 閾值 (前 10% 高)
        self.th2 = 0.3         # OBV 閾值 (高於後 30%)
        
        # 基礎指標參數
        self.mad_period = 10   # MAD 計算本身需要的週期
        self.obv_smooth = 20   # OBV 平滑週期 (沿用 PriceVolume2 的設定)

    def generate_signal(self):
        # 1. 數據長度檢查
        # 需要: MA(10) + Rolling(90) = 100 根以上
        if len(self.kline_data) < 120:
            return None

        # 2. 準備數據
        close = self.kline_data['close'].values
        volume = self.kline_data['vol'].values
        
        # ==========================================
        # 👇 因子計算
        # ==========================================

        # A. 計算 MAD
        mad = ind.AlphaLibrary.calc_mad(close, window=self.mad_period)

        # B. 計算 OBV (使用平滑版，避免雜訊)
        obv = ind.AlphaLibrary.calc_smooth_obv(close, volume, window=self.obv_smooth)

        # C. 計算滾動分位數閾值 (Quantile Thresholds)
        # data['mad'].rolling(90).quantile(0.9)
        mad_high_th = ind.AlphaLibrary.calc_rolling_quantile(mad, self.window, self.th1)
        
        # data['OBV'].rolling(90).quantile(0.3)
        obv_low_th = ind.AlphaLibrary.calc_rolling_quantile(obv, self.window, self.th2)

        # ==========================================
        # 👇 獲取當前數值 (Current Step)
        # ==========================================
        
        curr_mad = mad[-1]
        curr_obv = obv[-1]
        
        curr_mad_th = mad_high_th[-1]
        curr_obv_th = obv_low_th[-1]

        # Debug Log
        # print(f"[{self.name}] MAD:{curr_mad:.4f}(>{curr_mad_th:.4f}) | OBV:{curr_obv:.0f}(>{curr_obv_th:.0f})")

        # ==========================================
        # 👇 進出場邏輯 (Logic)
        # ==========================================

        # 進場: (MAD > 90% Quantile) & (OBV > 30% Quantile)
        long_condition = (curr_mad > curr_mad_th) and (curr_obv > curr_obv_th)
        
        # 出場: (MAD < 90% Quantile) | (OBV < 30% Quantile)
        # 也就是：波動率冷卻，或者量價轉弱，就跑
        exit_condition = (curr_mad < curr_mad_th) or (curr_obv < curr_obv_th)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'MAD_Breakout & OBV_Healthy'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'MAD_CoolDown or OBV_Weak'
            }
            
        return None