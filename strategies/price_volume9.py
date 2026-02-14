from .base_strategy import BaseStrategy
import pandas as pd

class PriceVolume9(BaseStrategy):
    def __init__(self):
        super().__init__()
        
        # --- 參數映射 ---
        self.mom_period = 10   # Momentum 週期
        self.mom_smooth = 5    # Momentum 平滑週期
        self.vroc_period = 10  # VROC 計算週期
        
        self.window = 90       # 滾動視窗 (中長期統計)
        self.th1 = 0.8         # Momentum 閾值 (80% 高動能)
        self.th2 = 0.9         # VROC 閾值 (90% 極致量能)

    def generate_signal(self):
        # ==========================================
        # 1. 定義需要的特徵 ID
        # ==========================================
        
        # A. 基礎指標數值
        # SmoothMomentum_V1 -> smooth_mom_{mom}_{smooth}_v1
        fid_mom = f"smooth_mom_{self.mom_period}_{self.mom_smooth}_v1"
        
        # VROC_V1 -> vroc_{window}_v1
        fid_vroc = f"vroc_{self.vroc_period}_v1"
        
        # B. 動態閾值線 (Rolling Quantile)
        # Momentum 閾值 (SmoothMomentum_Quantile_V1)
        # ID: smooth_mom_quantile_{mom}_{smooth}_{roll}_{q}_v1
        fid_mom_th = f"smooth_mom_quantile_{self.mom_period}_{self.mom_smooth}_{self.window}_{self.th1}_v1"
        
        # VROC 閾值 (VROC_Quantile_V1)
        # ID: vroc_quantile_{vroc}_{roll}_{q}_v1
        fid_vroc_th = f"vroc_quantile_{self.vroc_period}_{self.window}_{self.th2}_v1"

        # ==========================================
        # 2. 向 Feature Store 請求數據
        # ==========================================
        df = self.load_features([fid_mom, fid_vroc, fid_mom_th, fid_vroc_th])
        
        # 安全檢查
        if df.empty or len(df) < self.window + 20:
            return None

        required_cols = [fid_mom, fid_vroc, fid_mom_th, fid_vroc_th]
        if not all(col in df.columns for col in required_cols):
            return None

        # ==========================================
        # 3. 交易邏輯
        # ==========================================
        
        curr = df.iloc[-1]
        
        # 取值
        curr_mom     = curr[fid_mom]
        curr_vroc    = curr[fid_vroc]
        curr_mom_th  = curr[fid_mom_th]
        curr_vroc_th = curr[fid_vroc_th]

        # 進場: 動能強 (Mom > 80%) 且 量能爆發 (VROC > 90%)
        # 意義：價格強勢且成交量異常放大 (突破訊號)
        long_condition = (curr_mom > curr_mom_th) and (curr_vroc > curr_vroc_th)
        
        # 出場: 動能轉弱 (Mom < 80%) 且 量能回歸 (VROC < 90%)
        # 注意：使用 AND，必須等到動能與量能同時冷卻才出場
        exit_condition = (curr_mom < curr_mom_th) and (curr_vroc < curr_vroc_th)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'Mom_Strong({curr_mom:.2f}) & Vol_Shock({curr_vroc:.2f})'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'Mom_Fade & Vol_Normal'
            }
            
        return None