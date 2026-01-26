from .base_strategy import BaseStrategy
import indicators as ind
import numpy as np

class PriceVolume5(BaseStrategy):
    def __init__(self):
        super().__init__(name="Strategy5_HighVol_Momentum")
        
        # --- 策略參數 ---
        self.window = 25       # 滾動視窗 (短期統計)
        self.th1 = 0.9         # ATR 閾值 (波動率極高)
        self.th2 = 0.7         # Momentum 閾值 (動能強勢)
        
        # 基礎指標參數 (依照你之前的定義)
        self.atr_window = 16   # ATR 計算週期
        self.mom_period = 10   # Momentum 週期
        self.mom_smooth = 5    # Momentum 平滑週期

    def generate_signal(self):
        # 1. 數據長度檢查
        # 需要: ATR(16) + Rolling(25) = 41 根
        # Momentum(10+5) + Rolling(25) = 40 根
        # 安全邊際設 60
        if len(self.kline_data) < 60:
            return None

        # 2. 準備數據
        close = self.kline_data['close'].values
        high = self.kline_data['high'].values
        low = self.kline_data['low'].values
        
        # ==========================================
        # 👇 因子計算
        # ==========================================

        # A. 計算 ATR (自定義版: TR -> SMA)
        atr = ind.AlphaLibrary.calc_custom_atr(high, low, close, window=self.atr_window)

        # B. 計算 Momentum (平滑版: MOM -> SMA)
        momentum = ind.AlphaLibrary.calc_smooth_momentum(close, mom_period=self.mom_period, smooth_period=self.mom_smooth)

        # C. 計算滾動分位數閾值
        # data['ATR'].rolling(25).quantile(0.9)
        atr_th = ind.AlphaLibrary.calc_rolling_quantile(atr, self.window, self.th1)
        
        # data['momentum'].rolling(25).quantile(0.7)
        mom_th = ind.AlphaLibrary.calc_rolling_quantile(momentum, self.window, self.th2)

        # ==========================================
        # 👇 獲取當前數值
        # ==========================================
        
        curr_atr = atr[-1]
        curr_mom = momentum[-1]
        
        curr_atr_th = atr_th[-1]
        curr_mom_th = mom_th[-1]

        # Debug Log
        # print(f"[{self.name}] ATR:{curr_atr:.2f}(>{curr_atr_th:.2f}) | MOM:{curr_mom:.2f}(>{curr_mom_th:.2f})")

        # ==========================================
        # 👇 進出場邏輯
        # ==========================================

        # 進場: ATR > 90% Quantile AND Momentum > 70% Quantile
        # 意義：波動率放大且動能強勁 -> 追漲
        long_condition = (curr_atr > curr_atr_th) and (curr_mom > curr_mom_th)
        
        # 出場: ATR < 90% Quantile AND Momentum < 70% Quantile
        # 注意：使用 & (AND)，代表兩者都必須轉弱才跑，這會比 OR 更能抱住單子
        exit_condition = (curr_atr < curr_atr_th) and (curr_mom < curr_mom_th)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'Vol_Explosion & Mom_Strong'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'Vol_Drop & Mom_Weak'
            }
            
        return None