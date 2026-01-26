from .base_strategy import BaseStrategy
import indicators as ind
import numpy as np

class PriceVolume8(BaseStrategy):
    def __init__(self):
        super().__init__(name="Strategy8_Vol_BuyPressure")
        
        # --- 策略參數 ---
        self.window = 30       # 滾動視窗
        self.th1 = 0.7         # MAD 閾值 (波動率中高)
        self.th2 = 0.9         # BS Ratio 閾值 (買壓極強)
        
        # 基礎指標參數
        self.mad_period = 10   # MAD 計算週期

    def generate_signal(self):
        # 1. 數據長度檢查
        # MAD(10) + Rolling(30) = 40 根
        if len(self.kline_data) < 60:
            return None

        # 2. 準備數據
        close = self.kline_data['close'].values
        high = self.kline_data['high'].values
        low = self.kline_data['low'].values
        
        # ==========================================
        # 👇 因子計算
        # ==========================================

        # A. 計算 MAD (價格偏離度)
        mad = ind.AlphaLibrary.calc_mad(close, window=self.mad_period)

        # B. 計算 BS Ratio (買賣壓比)
        bs_ratio = ind.AlphaLibrary.calc_bs_ratio(high, low, close)

        # C. 計算滾動分位數閾值
        # MAD.rolling(30).quantile(0.7)
        mad_th = ind.AlphaLibrary.calc_rolling_quantile(mad, self.window, self.th1)
        
        # BS_Ratio.rolling(30).quantile(0.9)
        bs_th = ind.AlphaLibrary.calc_rolling_quantile(bs_ratio, self.window, self.th2)

        # ==========================================
        # 👇 獲取當前數值
        # ==========================================
        
        curr_mad = mad[-1]
        curr_bs = bs_ratio[-1]
        
        curr_mad_th = mad_th[-1]
        curr_bs_th = bs_th[-1]

        # Debug Log
        # print(f"[{self.name}] MAD:{curr_mad:.4f}(>{curr_mad_th:.4f}) | BS:{curr_bs:.2f}(>{curr_bs_th:.2f})")

        # ==========================================
        # 👇 進出場邏輯
        # ==========================================

        # 進場: MAD > 70% AND BS_Ratio > 90%
        # 意義：波動率放大，且買盤呈現壓倒性優勢
        long_condition = (curr_mad > curr_mad_th) and (curr_bs > curr_bs_th)
        
        # 出場: MAD < 70% AND BS_Ratio < 90%
        # 注意：使用 AND，必須等到「波動率冷卻」且「買盤也退潮」才出場
        # 如果買盤退了但波動率還很大（例如開始暴跌），這個邏輯可能不會出場（風險點）
        exit_condition = (curr_mad < curr_mad_th) and (curr_bs < curr_bs_th)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'HighVol & Extreme_Buy'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'Vol_Cool & Buy_Weak'
            }
            
        return None