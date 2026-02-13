from .base_strategy import BaseStrategy
import pandas as pd

class PriceVolume6(BaseStrategy):
    def __init__(self):
        super().__init__(name="Strategy6_Climax_Momentum")
        
        # --- 參數映射 ---
        self.atr_window = 16   # ATR 計算週期
        self.obv_smooth = 20   # OBV 平滑週期
        
        self.window = 30       # 滾動視窗 (短期爆發)
        self.th1 = 0.9         # ATR 閾值 (90%)
        self.th2 = 0.9         # OBV 閾值 (90%)

    def generate_signal(self):
        # ==========================================
        # 1. 定義需要的特徵 ID
        # ==========================================
        
        # A. 基礎指標數值
        
        fid_atr = f"custom_atr_{self.atr_window}_v1"
        
        
        fid_obv = f"smooth_obv_{self.obv_smooth}_v1"
        
        
        fid_atr_th = f"custom_atr_quantile_{self.atr_window}_{self.window}_{self.th1}_v1"
        
        
        fid_obv_th = f"smooth_obv_quantile_{self.obv_smooth}_{self.window}_{self.th2}_v1"

        # ==========================================
        # 2. 向 Feature Store 請求數據
        # ==========================================
        df = self.load_features([fid_atr, fid_obv, fid_atr_th, fid_obv_th])
        
        # 安全檢查
        if df.empty or len(df) < self.window + 20:
            return None

        required_cols = [fid_atr, fid_obv, fid_atr_th, fid_obv_th]
        if not all(col in df.columns for col in required_cols):
            return None

        # ==========================================
        # 3. 交易邏輯
        # ==========================================
        
        curr = df.iloc[-1]
        
        # 取值
        curr_atr    = curr[fid_atr]
        curr_obv    = curr[fid_obv]
        curr_atr_th = curr[fid_atr_th]
        curr_obv_th = curr[fid_obv_th]

        # 進場: 極度瘋狂 (ATR > 90% AND OBV > 90%)
        long_condition = (curr_atr > curr_atr_th) and (curr_obv > curr_obv_th)
        
        # 出場: 雙重冷卻 (ATR < 90% AND OBV < 90%)
        # 只有當波動率和量能同時降下來才出場 (容忍單一指標回檔)
        exit_condition = (curr_atr < curr_atr_th) and (curr_obv < curr_obv_th)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'Extreme_Vol({curr_atr:.2f}) & High_Volume({curr_obv:.0f})'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'Vol_CoolDown & OBV_Drop'
            }
            
        return None