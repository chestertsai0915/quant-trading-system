from .base_strategy import BaseStrategy
import pandas as pd

class PriceVolume5(BaseStrategy):
    def __init__(self):
        super().__init__(name="Strategy5_HighVol_Momentum")
        
        # --- 參數映射 ---
        self.atr_window = 16   # ATR 計算週期
        self.mom_period = 10   # Momentum 週期
        self.mom_smooth = 5    # Momentum 平滑週期
        
        self.window = 25       # 滾動視窗 (短期統計)
        self.th1 = 0.9         # ATR 閾值 (90%)
        self.th2 = 0.7         # Momentum 閾值 (70%)

    def generate_signal(self):
        # ==========================================
        # 1. 定義需要的特徵 ID
        # ==========================================
        
        # A. 基礎指標數值
        fid_atr = f"custom_atr_{self.atr_window}_v1"
        fid_mom = f"smooth_mom_{self.mom_period}_{self.mom_smooth}_v1"
        
        # B. 動態閾值線 (Rolling Quantile)
        # ATR 閾值
        fid_atr_th = f"custom_atr_quantile_{self.atr_window}_{self.window}_{self.th1}_v1"
        
        # Momentum 閾值
        fid_mom_th = f"smooth_mom_quantile_{self.mom_period}_{self.mom_smooth}_{self.window}_{self.th2}_v1"

        # ==========================================
        # 2. 向 Feature Store 請求數據
        # ==========================================
        df = self.load_features([fid_atr, fid_mom, fid_atr_th, fid_mom_th])
        
        # 安全檢查
        if df.empty or len(df) < self.window + 20:
            return None

        required_cols = [fid_atr, fid_mom, fid_atr_th, fid_mom_th]
        if not all(col in df.columns for col in required_cols):
            return None

        # ==========================================
        # 3. 交易邏輯
        # ==========================================
        
        curr = df.iloc[-1]
        
        # 取值
        curr_atr    = curr[fid_atr]
        curr_mom    = curr[fid_mom]
        curr_atr_th = curr[fid_atr_th]
        curr_mom_th = curr[fid_mom_th]

        # 進場: 波動率放大 (ATR > 90%) 且 動能強勁 (Mom > 70%)
        long_condition = (curr_atr > curr_atr_th) and (curr_mom > curr_mom_th)
        
        # 出場: 波動率冷卻 (ATR < 90%) 且 動能轉弱 (Mom < 70%)
        # 使用 AND 邏輯，容忍度較高 (抱單)
        exit_condition = (curr_atr < curr_atr_th) and (curr_mom < curr_mom_th)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'Vol_Explosion({curr_atr:.2f}) & Mom_Strong({curr_mom:.2f})'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'Vol_Drop & Mom_Weak'
            }
            
        return None