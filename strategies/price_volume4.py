from .base_strategy import BaseStrategy
import pandas as pd

class PriceVolume4(BaseStrategy):
    def __init__(self):
        super().__init__()
        
        # --- 參數映射 ---
        self.obv_smooth = 20   # OBV 平滑週期
        self.vroc_period = 10  # VROC 計算週期
        
        self.window = 250      # 滾動視窗 (長期統計)
        self.th1 = 0.8         # OBV 分位數閾值
        self.th2 = 0.8         # VROC 分位數閾值

    def generate_signal(self):
        # ==========================================
        # 1. 定義需要的特徵 ID
        # ==========================================
        
        # A. 基礎指標數值
        # 假設 VROC 基礎特徵 ID 是 vroc_{window}_v1 (需確認 feature_definitions 是否有 VROC_V1)
        fid_vroc = f"vroc_{self.vroc_period}_v1" 
        fid_obv = f"smooth_obv_{self.obv_smooth}_v1"
        
        # B. 動態閾值線 (Rolling Quantile)
        # OBV 閾值 (重複利用 PriceVolume3 的定義，參數不同會自動產生新 ID)
        fid_obv_th = f"smooth_obv_quantile_{self.obv_smooth}_{self.window}_{self.th1}_v1"
        
        # VROC 閾值 (剛剛新增的)
        fid_vroc_th = f"vroc_quantile_{self.vroc_period}_{self.window}_{self.th2}_v1"

        # ==========================================
        # 2. 向 Feature Store 請求數據
        # ==========================================
        df = self.load_features([fid_vroc, fid_obv, fid_obv_th, fid_vroc_th])
        
        # 安全檢查
        if df.empty or len(df) < self.window + 20:
            return None

        required_cols = [fid_vroc, fid_obv, fid_obv_th, fid_vroc_th]
        if not all(col in df.columns for col in required_cols):
            return None

        # ==========================================
        # 3. 交易邏輯
        # ==========================================
        
        curr = df.iloc[-1]
        
        # 取值
        curr_obv     = curr[fid_obv]
        curr_vroc    = curr[fid_vroc]
        curr_obv_th  = curr[fid_obv_th]
        curr_vroc_th = curr[fid_vroc_th]

        # 決策邏輯: 雙強進場
        # 長期量能趨勢強 (OBV > 80%) 且 短期成交量爆發 (VROC > 80%)
        long_condition = (curr_obv > curr_obv_th) and (curr_vroc > curr_vroc_th)
        
        # 出場: 雙弱離場
        # 注意：這裡保留原本的 AND 邏輯 (只有兩者都轉弱才跑)
        exit_condition = (curr_obv < curr_obv_th) and (curr_vroc < curr_vroc_th)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'High_OBV({curr_obv:.0f}) & High_VROC({curr_vroc:.2f})'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'Momentum_Collapsed'
            }
            
        return None