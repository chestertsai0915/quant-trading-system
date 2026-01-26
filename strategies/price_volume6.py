from .base_strategy import BaseStrategy
import indicators as ind
import numpy as np

class PriceVolume6(BaseStrategy):
    def __init__(self):
        super().__init__(name="Strategy6_Climax_Momentum")
        
        # --- 策略參數 ---
        self.window = 30       # 滾動視窗
        self.th1 = 0.9         # ATR 閾值 (波動率極高)
        self.th2 = 0.9         # OBV 閾值 (量能極高)
        
        # 基礎指標參數
        self.atr_window = 16   # ATR 計算週期
        self.obv_smooth = 20   # OBV 平滑週期

    def generate_signal(self):
        # 1. 數據長度檢查
        # 需要: ATR(16) + Rolling(30) = 46 根
        # 安全邊際設 60
        if len(self.kline_data) < 60:
            return None

        # 2. 準備數據
        close = self.kline_data['close'].values
        high = self.kline_data['high'].values
        low = self.kline_data['low'].values
        volume = self.kline_data['vol'].values
        
        # ==========================================
        # 👇 因子計算
        # ==========================================

        # A. 計算 ATR (自定義版)
        atr = ind.AlphaLibrary.calc_custom_atr(high, low, close, window=self.atr_window)

        # B. 計算 OBV (平滑版)
        obv = ind.AlphaLibrary.calc_smooth_obv(close, volume, window=self.obv_smooth)

        # C. 計算滾動分位數閾值
        # ATR.rolling(30).quantile(0.9)
        atr_th = ind.AlphaLibrary.calc_rolling_quantile(atr, self.window, self.th1)
        
        # OBV.rolling(30).quantile(0.9)
        obv_th = ind.AlphaLibrary.calc_rolling_quantile(obv, self.window, self.th2)

        # ==========================================
        # 👇 獲取當前數值
        # ==========================================
        
        curr_atr = atr[-1]
        curr_obv = obv[-1]
        
        curr_atr_th = atr_th[-1]
        curr_obv_th = obv_th[-1]

        # Debug Log
        # print(f"[{self.name}] ATR:{curr_atr:.2f}(>{curr_atr_th:.2f}) | OBV:{curr_obv:.0f}(>{curr_obv_th:.0f})")

        # ==========================================
        # 👇 進出場邏輯
        # ==========================================

        # 進場: ATR > 90% AND OBV > 90%
        # 意義：市場進入瘋狂狀態，波動大且買盤強
        long_condition = (curr_atr > curr_atr_th) and (curr_obv > curr_obv_th)
        
        # 出場: ATR < 90% AND OBV < 90%
        # 注意：使用 AND，代表兩者都必須冷卻才跑
        # 如果只有波動率下降但 OBV 還在高檔（量縮價穩），會繼續持有
        exit_condition = (curr_atr < curr_atr_th) and (curr_obv < curr_obv_th)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'Extreme_Vol & High_Volume_Acc'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'Vol_CoolDown & OBV_Drop'
            }
            
        return None